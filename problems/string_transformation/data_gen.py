"""Generates string transformation problem datasets for testing the orchestrator."""
from __future__ import annotations

import random
import string
from typing import List


def generate_samples(num_samples: int = 10) -> List[str]:
    random.seed(0)
    return [''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(5, 20))) for _ in range(num_samples)]


def generate_stress_samples(num_samples: int = 64) -> List[str]:
    random.seed(1)
    return [''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(100, 200))) for _ in range(num_samples)]


def generate_adversarial_samples() -> List[str]:
    return [
        "",
        "a" * 1000,
        " " * 1000,
        "\n" * 1000,
        "\t" * 1000,
        "a" * 500 + " " * 500,
    ]


def generate_noisy_samples(num_samples: int = 48) -> List[str]:
    random.seed(2)
    base = generate_samples(num_samples)
    jittered: List[str] = []
    for s in base:
        noise = ''.join(random.choices(string.punctuation, k=random.randint(1, 5)))
        pos = random.randint(0, len(s))
        jittered.append(s[:pos] + noise + s[pos:])
    return jittered


if __name__ == "__main__":
    print(generate_samples())
