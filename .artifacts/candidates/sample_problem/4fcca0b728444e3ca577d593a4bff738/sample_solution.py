"""Initial baseline solution with EVOLVE-BLOCK markers."""
from __future__ import annotations

import logging
from typing import Iterable, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    total = 0.0
    count = 0
    for item in pairs:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            continue
        a, b = item
        try:
            total += a + b
            count += 1
        except (TypeError, ValueError):
            continue

    return total / count if count else 0.0

# EVOLVE-BLOCK-END
