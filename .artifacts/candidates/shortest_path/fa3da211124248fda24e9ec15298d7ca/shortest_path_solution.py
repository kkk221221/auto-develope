"""Baseline shortest path solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

import heapq
from typing import Dict, Iterable, List, Sequence, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def _dijkstra_from_adj(graph: Sequence[Sequence[Tuple[int, float]]], source: int, target: int) -> float:
    if not (0 <= source < len(graph)):
        raise ValueError(f"Source {source} out of bounds for graph of size {len(graph)}")
    if not (0 <= target < len(graph)):
        raise ValueError(f"Target {target} out of bounds for graph of size {len(graph)}")
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
            if not (0 <= neighbour < len(graph)):
                continue
            candidate = current + float(weight)
            if candidate < distances[neighbour]:
                distances[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
    if distances[target] == float("inf"):
        raise ValueError(f"Target not reachable from source")
    return distances[target]

# EVOLVE-BLOCK-END
