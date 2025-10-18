"""Generates sample problem datasets for testing the orchestrator."""
from __future__ import annotations

import random
from typing import List


def generate_samples(num_samples: int = 10) -> List[List[int]]:
    random.seed(0)
    return [
        [random.randint(0, 100) for _ in range(random.randint(2, 10))]
        for _ in range(num_samples)
    ]


if __name__ == "__main__":
    print(generate_samples())
