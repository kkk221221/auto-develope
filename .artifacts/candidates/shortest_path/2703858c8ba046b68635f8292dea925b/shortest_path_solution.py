"""Baseline shortest path solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

import heapq
from typing import Dict, Iterable, List, Sequence, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += _heap_shortest(sample)
        count += 1
    return total / count if count else 0.0


def _heap_shortest(sample: Dict[str, object]) -> float:
    nodes = int(sample.get("nodes", 0))
    graph: List[List[Tuple[int, float]]] = [[] for _ in range(nodes)]
    for edge in sample.get("edges", []):
        try:
            u, v, w = edge
        except (TypeError, ValueError):
            continue
        u, v = int(u), int(v)
        if 0 <= u < nodes and 0 <= v < nodes:
            graph[u].append((v, max(1.0, float(w))))
    return _dijkstra_from_adj(graph, int(sample.get("source", 0)), int(sample.get("target", nodes - 1)))


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
