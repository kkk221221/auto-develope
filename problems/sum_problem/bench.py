"""Benchmark runner producing JSON metrics for the sample problem."""
from __future__ import annotations

import json
from pathlib import Path

from orchestrator.evaluation import ProblemEvaluator
from orchestrator.models import ProgramCandidate


def run_benchmark(candidate_path: str | None = None) -> None:
    source = Path(candidate_path or "solutions/workdir/sample_solution.py").resolve()
    candidate = ProgramCandidate(
        id="benchmark",
        parents=tuple(),
        generation=0,
        prompt_arm="benchmark",
        llm_backend="flash",
        patch_payload={},
        source_path=str(source),
        problem_id="sample_problem",
    )
    evaluator = ProblemEvaluator({"sample_problem": "problems.sample_problem"})
    metrics, _ = evaluator.evaluate(
        candidate,
        dataset_size=32,
        repeats=3,
        stress=True,
        percentiles=[0.5, 0.9],
        stress_suites=["adversarial", "noisy"],
    )
    result = {
        "accuracy": metrics.accuracy,
        "runtime_ms": metrics.runtime_ms,
        "memory_peak_mb": metrics.memory_peak_mb,
        "robustness": metrics.robustness,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    run_benchmark()
