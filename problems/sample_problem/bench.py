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
    )
    evaluator = ProblemEvaluator("problems.sample_problem")
    metrics = evaluator.evaluate(candidate, dataset_size=32, repeats=3, stress=True)
    result = {
        "accuracy": metrics.accuracy,
        "runtime_ms": metrics.runtime_ms,
        "memory_peak_mb": metrics.memory_peak_mb,
        "robustness": metrics.robustness,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    run_benchmark()
