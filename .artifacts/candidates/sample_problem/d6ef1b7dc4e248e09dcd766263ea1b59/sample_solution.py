"""Initial baseline solution with EVOLVE-BLOCK markers."""
from __future__ import annotations

import logging
from typing import Iterable, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    total = 0
    count = 0
    malformed_pairs = 0
    non_integer_values = 0
    for i, pair in enumerate(pairs):
        if not isinstance(pair, tuple) or len(pair) != 2:
            logging.warning(f"Item at index {i} is not a tuple of 2 elements: {pair}")
            malformed_pairs += 1
            continue
        a, b = pair
        if not isinstance(a, int) or not isinstance(b, int):
            logging.warning(f"Item at index {i} contains non-integer values: {pair}")
            non_integer_values += 1
            continue
        total += a + b
        count += 1
    if malformed_pairs > 0:
        logging.info(f"Found {malformed_pairs} malformed pairs.")
    if non_integer_values > 0:
        logging.info(f"Found {non_integer_values} pairs with non-integer values.")
    metrics = {
        "malformed_pairs": malformed_pairs,
        "non_integer_values": non_integer_values,
        "valid_pairs_processed": count
    }
    logging.info(f"Metrics: {metrics}")
    if count == 0:
        return 0.0
    return total / count

# EVOLVE-BLOCK-END
