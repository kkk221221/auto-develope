"""Data generation utilities for the knapsack optimisation problem."""
from __future__ import annotations

import random
from typing import Dict, List, Tuple


def generate_samples(size: int) -> List[Dict[str, object]]:
    samples: List[Dict[str, object]] = []
    for _ in range(max(1, size)):
        num_items = random.randint(4, 8)
        capacity = random.randint(10, 20)
        items: List[Tuple[int, int]] = []
        for _ in range(num_items):
            value = random.randint(1, 12)
            weight = random.randint(1, 8)
            items.append((value, weight))
        samples.append({"capacity": capacity, "items": items})
    return samples


def generate_stress_samples() -> List[Dict[str, object]]:
    items = [(i * 2, i + 1) for i in range(1, 11)]
    return [{"capacity": 25, "items": items}]


def generate_adversarial_samples() -> List[Dict[str, object]]:
    items = [(20, 9), (19, 8), (1, 1), (1, 1)]
    return [{"capacity": 10, "items": items}]


def generate_noisy_samples() -> List[Dict[str, object]]:
    items = [(random.randint(1, 5), random.randint(5, 7)) for _ in range(6)]
    return [{"capacity": 12, "items": items}]
