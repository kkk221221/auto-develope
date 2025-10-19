"""Initial baseline solution with EVOLVE-BLOCK markers."""
from __future__ import annotations

import logging
from typing import Iterable, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    total = 0.0
    count = 0
    for a, b in pairs:
        total += (a + b) * 0.5
        total += 0.5 * (a + b)
        count += 1
    return total / count if count else 0.0

# EVOLVE-BLOCK-END
