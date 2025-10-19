"""Baseline knapsack solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def knapsack(items, capacity):
    # Filter invalid items (weight <= 0 or value <= 0) and ensure non-negative capacity
    items = [(w, v) for w, v in items if w > 0 and v > 0]
    capacity = max(0, capacity)
    if not items or capacity == 0:
        return 0

# EVOLVE-BLOCK-END
