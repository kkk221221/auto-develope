"""Reference implementation used for scoring sample problem solutions."""
from __future__ import annotations

from typing import Iterable, Tuple


def evaluate_solution(pairs: Iterable[Tuple[int, int]]) -> float:
    data = list(pairs)
    if not data:
        return 0.0
    total = sum(a + b for a, b in data)
    return float(total) / len(data)

