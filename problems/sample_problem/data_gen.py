"""Generates sample problem datasets for testing the orchestrator."""
from __future__ import annotations

import random
from typing import List, Tuple


def generate_samples(num_samples: int = 10) -> List[Tuple[int, int]]:
    random.seed(0)
    return [(random.randint(0, 100), random.randint(0, 100)) for _ in range(num_samples)]


if __name__ == "__main__":
    print(generate_samples())
