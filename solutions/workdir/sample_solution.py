"""Initial baseline solution with EVOLVE-BLOCK markers."""
from __future__ import annotations

from typing import Iterable, Tuple


# EVOLVE-BLOCK-START: baseline implementation

def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    total = 0
    count = 0
    for a, b in pairs:
        total += a + b
        count += 1
    if count == 0:
        return 0.0
    return total / count


# EVOLVE-BLOCK-END
