"""Reference solver for the knapsack problem."""
from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple


def evaluate_solution(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        best = _solve_single(sample)
        total += best
        count += 1
    if count == 0:
        return 0.0
    return total / count


def _solve_single(sample: Dict[str, object]) -> float:
    capacity = int(sample.get("capacity", 0))
    items_raw = sample.get("items", [])
    items: List[Tuple[int, int]] = []
    for item in items_raw:
        try:
            value, weight = item
        except (TypeError, ValueError):
            continue
        value = max(0, int(value))
        weight = max(1, int(weight))
        items.append((value, weight))
    return float(_dynamic_programming(capacity, items))


def _dynamic_programming(capacity: int, items: Sequence[Tuple[int, int]]) -> int:
    dp = [0] * (capacity + 1)
    for value, weight in items:
        for current in range(capacity, weight - 1, -1):
            candidate = dp[current - weight] + value
            if candidate > dp[current]:
                dp[current] = candidate
    return max(dp)
