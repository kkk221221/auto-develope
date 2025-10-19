"""Initial baseline solution with EVOLVE-BLOCK markers."""
from __future__ import annotations

import logging
from typing import Iterable, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    cleaned = []
    for item in pairs:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            continue
        a, b = item
        try:
            cleaned.append((float(a), float(b)))
        except (TypeError, ValueError):
            continue
    if not cleaned:
        return 0.0
    return sum(a + b for a, b in cleaned) / len(cleaned)

# EVOLVE-BLOCK-END
