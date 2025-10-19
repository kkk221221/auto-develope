"""Baseline knapsack solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def _dynamic_programming(capacity: int, items: List[Tuple[int, int]]) -> int:
    dp = [0] * (capacity + 1)
    for value, weight in items:
        if weight <= capacity:
            for current in range(capacity, weight - 1, -1):
                candidate = dp[current - weight] + value
                if candidate > dp[current]:
                    dp[current] = candidate
    return dp[capacity]

# EVOLVE-BLOCK-END
