"""Integration tests for the sample problem evaluator pipeline."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.evaluation import ProblemEvaluator, TierExecutor, load_tier_specs
from orchestrator.generation import ProgramGenerator


def test_problem_evaluator_scores_candidate() -> None:
    generator = ProgramGenerator(
        baseline_path=Path("solutions/workdir/sample_solution.py"),
        output_root=Path(".artifacts/tests"),
    )
    candidate = generator.spawn_candidate("mutate.perf_first", backend="flash")
    evaluator = ProblemEvaluator("problems.sample_problem")
    metrics = evaluator.evaluate(candidate, dataset_size=16, repeats=2)
    assert metrics.accuracy >= 0.95
    assert metrics.runtime_ms > 0


def test_tier_executor_runs_checks(tmp_path: Path) -> None:
    generator = ProgramGenerator(
        baseline_path=Path("solutions/workdir/sample_solution.py"),
        output_root=tmp_path,
    )
    candidate = generator.spawn_candidate("mutate.robust_first", backend="flash")
    specs = load_tier_specs(Path("configs/tiers.yaml"))
    executor = TierExecutor(tier_specs=specs, evaluator=ProblemEvaluator("problems.sample_problem"))
    tier_result = asyncio.run(executor.run(candidate, "L0"))
    assert tier_result.passed
    assert tier_result.metrics.accuracy >= 0.8
