"""Baseline knapsack solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


# EVOLVE-BLOCK-START: baseline implementation

def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        capacity = int(sample.get("capacity", 0))
        items = _normalise_items(sample.get("items", []))
        total += float(_dynamic_programming(capacity, items))
        count += 1
    if count == 0:
        return 0.0
    return total / count


def _normalise_items(raw_items: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    cleaned: List[Tuple[int, int]] = []
    for item in raw_items:
        try:
            value, weight = item
        except (TypeError, ValueError):
            continue
        value = int(value)
        weight = int(weight)
        if weight <= 0:
            continue
        cleaned.append((max(0, value), weight))
    return cleaned


def _dynamic_programming(capacity: int, items: List[Tuple[int, int]]) -> int:
    dp = [0] * (capacity + 1)
    for value, weight in items:
        for current in range(capacity, weight - 1, -1):
            candidate = dp[current - weight] + value
            if candidate > dp[current]:
                dp[current] = candidate
    return max(dp) if dp else 0


# EVOLVE-BLOCK-END
