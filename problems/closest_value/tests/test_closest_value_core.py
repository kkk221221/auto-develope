"""Integration tests for the sample problem evaluator pipeline."""
from __future__ import annotations

import asyncio
from pathlib import Path

from orchestrator.evaluation import ProblemEvaluator, TierExecutor, load_tier_specs
from orchestrator.generation import ProgramGenerator
from orchestrator.problem_specs import load_problem_specs
from orchestrator.prompt_policy import PromptMaterialization

PROBLEM_SPECS = load_problem_specs(Path("configs/problems.json"))


def test_problem_evaluator_scores_candidate() -> None:
    generator = ProgramGenerator(problem_specs=PROBLEM_SPECS, output_root=Path(".artifacts/tests"))
    prompt = PromptMaterialization(
        name="mutate.perf_first",
        backend="flash",
        content="",
        generation=0,
        checklist=[],
    )
    candidate = generator.spawn_candidate("mutate.perf_first", prompt, problem_id="sample_problem")
    evaluator = ProblemEvaluator({"sample_problem": "problems.sample_problem"})
    metrics, behavior = evaluator.evaluate(candidate, dataset_size=16, repeats=2)
    assert metrics.accuracy >= 0.95
    assert metrics.runtime_ms > 0
    assert behavior.hotspots["runtime_mean"] == metrics.runtime_ms


def test_tier_executor_runs_checks(tmp_path: Path) -> None:
    generator = ProgramGenerator(problem_specs=PROBLEM_SPECS, output_root=tmp_path)
    prompt = PromptMaterialization(
        name="mutate.robust_first",
        backend="flash",
        content="",
        generation=0,
        checklist=[],
    )
    candidate = generator.spawn_candidate("mutate.robust_first", prompt, problem_id="sample_problem")
    specs = load_tier_specs(Path("configs/tiers.yaml"))
    evaluator = ProblemEvaluator({"sample_problem": "problems.sample_problem"})
    executor = TierExecutor(tier_specs=specs, evaluator=evaluator)
    tier_result = asyncio.run(executor.run(candidate, "L0"))
    assert tier_result.passed
    assert tier_result.metrics.accuracy >= 0.8
    assert tier_result.behavior is not None
