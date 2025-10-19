"""Baseline shortest path solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

import heapq
from typing import Dict, Iterable, List, Sequence, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def _dijkstra_from_adj(graph: Sequence[Sequence[Tuple[int, float]]], source: int, target: int) -> float:
    distances = [float('inf')] * len(graph)
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
    return float('inf')

def _dijkstra_guarded(graph: Dict[int, List[Tuple[int, float]]], source: int, target: int) -> float:
    distances = {node: float('inf') for node in graph}
    distances[source] = 0.0
    queue: List[Tuple[float, int]] = [(0.0, source)]
    while queue:
        current, node = heapq.heappop(queue)
        if current > distances[node]:
            continue
        if node == target:
            return current
        for neighbour, weight in graph.get(node, []):
            candidate = current + weight
            if candidate < distances.get(neighbour, float('inf')):
                distances[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
    return float('inf')

def _heap_shortest(sample: Dict[str, object]) -> float:
    nodes = int(sample.get('nodes', 0))
    graph: List[List[Tuple[int, float]]] = [[] for _ in range(nodes)]
    for edge in sample.get('edges', []):
        try:
            u, v, w = edge
        except (TypeError, ValueError):
            continue
        u, v = (int(u), int(v))
        if 0 <= u < nodes and 0 <= v < nodes:
            graph[u].append((v, max(1.0, float(w))))
    return _dijkstra_from_adj(graph, int(sample.get('source', 0)), int(sample.get('target', nodes - 1)))

def _safe_shortest(sample: Dict[str, object]) -> float:
    nodes = int(sample.get('nodes', 0))
    adjacency = {i: [] for i in range(nodes)}
    for edge in sample.get('edges', []):
        try:
            u, v, w = edge
        except (TypeError, ValueError):
            continue
        u, v = (int(u), int(v))
        if u not in adjacency or v not in adjacency:
            continue
        adjacency[u].append((v, max(1.0, float(w))))
    source = int(sample.get('source', 0))
    target = int(sample.get('target', nodes - 1))
    return _dijkstra_guarded(adjacency, source, target)

def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        distance = _safe_shortest(sample)
        total += distance
        count += 1
    return total / count if count else 0.0

# EVOLVE-BLOCK-END
