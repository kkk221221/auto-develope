from __future__ import annotations

from solutions.workdir.shortest_path_solution import solve


def test_shortest_path_baseline_handles_simple_graph() -> None:
    sample = [
        {
            "nodes": 4,
            "edges": [
                (0, 1, 2),
                (1, 2, 2),
                (2, 3, 1),
                (0, 3, 20),
            ],
            "source": 0,
            "target": 3,
        }
    ]
    result = solve(sample)
    assert abs(result - 5.0) < 1e-6


def test_shortest_path_baseline_filters_invalid_edges() -> None:
    sample = [
        {
            "nodes": 3,
            "edges": [
                (0, 1, 5),
                (1, 2, 1),
                (2, 2, 1),
                (5, 1, 3),
            ],
            "source": 0,
            "target": 2,
        }
    ]
    assert solve(sample) == 6.0
