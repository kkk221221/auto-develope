"""Initial baseline solution with EVOLVE-BLOCK markers."""
from __future__ import annotations

import logging
from typing import Iterable, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    if pairs is None:
        logging.error("Input pairs is None")
        return 0.0
    if not isinstance(pairs, (list, tuple, set)) and not hasattr(pairs, '__iter__'):
        logging.error(f"Input pairs is not iterable: {type(pairs)}")
        return 0.0
    total = 0
    count = 0
    malformed_pairs = 0
    non_integer_values = 0
    for i, pair in enumerate(pairs):

# EVOLVE-BLOCK-END
