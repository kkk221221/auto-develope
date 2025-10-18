"""Baseline shortest path solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

import heapq
from typing import Dict, Iterable, List, Sequence, Tuple


# EVOLVE-BLOCK-START: baseline implementation

def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        distance = _dijkstra(sample)
        total += distance
        count += 1
    if count == 0:
        return 0.0
    return total / count


def _dijkstra(sample: Dict[str, object]) -> float:
    nodes = int(sample.get("nodes", 0))
    edges = sample.get("edges", [])
    source = int(sample.get("source", 0))
    target = int(sample.get("target", nodes - 1))
    adjacency: List[List[Tuple[int, float]]] = [[] for _ in range(nodes)]
    for edge in edges:
        try:
            u, v, w = edge
        except (TypeError, ValueError):
            continue
        if not isinstance(u, int) or not isinstance(v, int):
            u, v = int(u), int(v)
        weight = float(w) if isinstance(w, (int, float)) else 1.0
        if 0 <= u < nodes and 0 <= v < nodes:
            adjacency[u].append((v, max(weight, 0.0)))
    return _dijkstra_from_adj(adjacency, source, target)


def _dijkstra_from_adj(graph: Sequence[Sequence[Tuple[int, float]]], source: int, target: int) -> float:
    distances = [float("inf")] * len(graph)
    distances[source] = 0.0
    queue: List[Tuple[float, int]] = [(0.0, source)]
    while queue:
        current, node = heapq.heappop(queue)
        if current > distances[node]:
            continue
        if node == target:
            return current
        for neighbour, weight in graph[node]:
            candidate = current + float(weight)
            if candidate < distances[neighbour]:
                distances[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
    return float("inf")


# EVOLVE-BLOCK-END
