from __future__ import annotations

from solutions.workdir.knapsack_solution import solve


def test_knapsack_baseline_matches_known_instance() -> None:
    sample = [
        {
            "capacity": 7,
            "items": [(16, 6), (7, 4), (5, 3), (15, 5)],
        }
    ]
    assert solve(sample) == 16.0


def test_knapsack_baseline_ignores_invalid_items() -> None:
    sample = [
        {
            "capacity": 4,
            "items": [(5, 0), (3, 5), (4, 2)],
        }
    ]
    assert solve(sample) == 4.0
