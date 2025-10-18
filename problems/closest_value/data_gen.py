"""Generates sample problem datasets for testing the orchestrator."""
from __future__ import annotations

import random
from typing import List, Tuple


def generate_samples(num_samples: int = 10) -> List[Tuple[int, int]]:
    random.seed(0)
    return [(random.randint(0, 100), random.randint(0, 100)) for _ in range(num_samples)]


def generate_stress_samples(num_samples: int = 64) -> List[Tuple[int, int]]:
    random.seed(1)
    return [
        (random.randint(-1000, 1000), random.randint(-1000, 1000))
        for _ in range(num_samples)
    ]


def generate_adversarial_samples() -> List[Tuple[int, int]]:
    return [
        (0, 0),
        (10**6, -10**6),
        (-10**5, 10**4),
        (1, -1),
        (999999, 1),
        (-999999, -1),
    ]


def generate_noisy_samples(num_samples: int = 48) -> List[Tuple[int, int]]:
    random.seed(2)
    base = generate_samples(num_samples)
    jittered: List[Tuple[int, int]] = []
    for a, b in base:
        noise_a = a + random.randint(-25, 25)
        noise_b = b + random.randint(-25, 25)
        jittered.append((noise_a, noise_b))
    return jittered


if __name__ == "__main__":
    print(generate_samples())
