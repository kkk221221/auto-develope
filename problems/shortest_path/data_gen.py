"""Data generation utilities for the shortest path problem."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class GraphSample:
    nodes: int
    edges: Tuple[Tuple[int, int, int], ...]
    source: int
    target: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "nodes": self.nodes,
            "edges": [list(edge) for edge in self.edges],
            "source": self.source,
            "target": self.target,
        }


def _ensure_backbone(nodes: int) -> List[Tuple[int, int, int]]:
    edges: List[Tuple[int, int, int]] = []
    for vertex in range(nodes - 1):
        weight = random.randint(1, 6)
        edges.append((vertex, vertex + 1, weight))
    return edges


def _random_edges(nodes: int, density: float) -> List[Tuple[int, int, int]]:
    edges: List[Tuple[int, int, int]] = []
    attempts = int(density * nodes * (nodes - 1))
    for _ in range(attempts):
        source = random.randint(0, nodes - 1)
        target = random.randint(0, nodes - 1)
        if source == target:
            continue
        weight = random.randint(1, 12)
        edges.append((source, target, weight))
    return edges


def generate_samples(size: int) -> List[Dict[str, object]]:
    samples: List[Dict[str, object]] = []
    for _ in range(max(1, size)):
        nodes = random.randint(5, 10)
        density = random.uniform(0.3, 0.7)
        edges = _ensure_backbone(nodes)
        edges.extend(_random_edges(nodes, density))
        sample = GraphSample(
            nodes=nodes,
            edges=tuple(edges),
            source=0,
            target=nodes - 1,
        )
        samples.append(sample.to_dict())
    return samples


def generate_stress_samples() -> List[Dict[str, object]]:
    samples: List[Dict[str, object]] = []
    for nodes in (12, 16):
        edges = _ensure_backbone(nodes)
        edges.extend((0, nodes // 2, 1) for _ in range(nodes // 2))
        edges.extend((nodes // 2, nodes - 1, 2) for _ in range(nodes // 2))
        sample = GraphSample(
            nodes=nodes,
            edges=tuple(edges),
            source=0,
            target=nodes - 1,
        )
        samples.append(sample.to_dict())
    return samples


def generate_adversarial_samples() -> List[Dict[str, object]]:
    nodes = 8
    edges = _ensure_backbone(nodes)
    # Adversarial: heavy shortcut that should be avoided
    edges.append((0, nodes - 1, 1000))
    edges.extend(
        (
            random.randint(0, nodes - 2),
            random.randint(1, nodes - 1),
            random.randint(5, 50),
        )
        for _ in range(10)
    )
    sample = GraphSample(nodes=nodes, edges=tuple(edges), source=0, target=nodes - 1)
    return [sample.to_dict()]


def generate_noisy_samples() -> List[Dict[str, object]]:
    nodes = 10
    edges = _ensure_backbone(nodes)
    edges.extend((i, (i + 2) % nodes, random.randint(1, 15)) for i in range(nodes))
    sample = GraphSample(nodes=nodes, edges=tuple(edges), source=0, target=nodes - 1)
    return [sample.to_dict()]
