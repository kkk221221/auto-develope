"""Baseline knapsack solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += float(_dense_dp(sample))
        count += 1
    return total / count if count else 0.0


def _dense_dp(sample: Dict[str, object]) -> int:
    capacity = int(sample.get("capacity", 0))
    items = _normalise_items(sample.get("items", []))
    dp = [0] * (capacity + 1)
    for value, weight in items:
        for current in range(weight, capacity + 1):
            candidate = dp[current - weight] + value
            if candidate > dp[current]:
                dp[current] = candidate
    return dp[capacity]


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
    cleaned.sort(key=lambda item: (item[1], -item[0]))
    return cleaned

# EVOLVE-BLOCK-END
