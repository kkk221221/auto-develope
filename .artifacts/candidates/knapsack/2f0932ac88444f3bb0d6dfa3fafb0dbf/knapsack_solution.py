"""Baseline knapsack solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += float(_robust_knapsack(sample))
        count += 1
    return total / count if count else 0.0


def _robust_knapsack(sample: Dict[str, object]) -> int:
    capacity = max(0, int(sample.get("capacity", 0)))
    items = _filter_items(sample.get("items", []))
    dp = [0] * (capacity + 1)
    for value, weight in items:
        for current in range(capacity, weight - 1, -1):
            candidate = dp[current - weight] + value
            if candidate > dp[current]:
                dp[current] = candidate
    return max(dp) if dp else 0


def _filter_items(raw_items: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    filtered: List[Tuple[int, int]] = []
    for item in raw_items:
        try:
            value, weight = item
        except (TypeError, ValueError):
            continue
        value = int(value)
        weight = int(weight)
        if value <= 0 or weight <= 0:
            continue
        filtered.append((value, weight))
    return filtered

# EVOLVE-BLOCK-END
