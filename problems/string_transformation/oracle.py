"""Reference implementation used for scoring string transformation solutions."""
from __future__ import annotations

from typing import Iterable

from solutions.workdir import string_transformation_solution


def oracle(s: str) -> str:
    return s.upper()[::-1]


def evaluate_solution(inputs: Iterable[str]) -> float:
    data = list(inputs)
    if not data:
        return 0.0

    correct = 0
    for s in data:
        if string_transformation_solution.transform_string(s) == oracle(s):
            correct += 1

    return float(correct) / len(data)
