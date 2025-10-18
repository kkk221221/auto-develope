"""Benchmark runner producing JSON metrics for the sample problem."""
from __future__ import annotations

import json
from time import perf_counter

from .data_gen import generate_samples
from .oracle import evaluate_solution


def run_benchmark() -> None:
    samples = generate_samples()
    start = perf_counter()
    score = evaluate_solution(samples)
    duration_ms = (perf_counter() - start) * 1000
    result = {
        "score": score,
        "runtime_ms": duration_ms,
        "samples": len(samples),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    run_benchmark()
