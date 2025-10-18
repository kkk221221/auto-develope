"""Reference implementation for the shortest path problem."""
from __future__ import annotations

import heapq
from typing import Dict, Iterable, List, Tuple


def evaluate_solution(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        distance = _solve_single(sample)
        total += distance
        count += 1
    if count == 0:
        return 0.0
    return total / count


def _solve_single(sample: Dict[str, object]) -> float:
    nodes = int(sample.get("nodes", 0))
    edges_raw = sample.get("edges", [])
    source = int(sample.get("source", 0))
    target = int(sample.get("target", nodes - 1))
    adjacency: List[List[Tuple[int, int]]] = [[] for _ in range(nodes)]
    for edge in edges_raw:
        try:
            u, v, w = edge
        except (TypeError, ValueError):
            continue
        u = int(u)
        v = int(v)
        weight = max(1, int(w))
        if 0 <= u < nodes and 0 <= v < nodes:
            adjacency[u].append((v, weight))
    return _dijkstra(adjacency, source, target)


def _dijkstra(graph: List[List[Tuple[int, int]]], source: int, target: int) -> float:
    distances = [float("inf")] * len(graph)
    distances[source] = 0.0
    queue: List[Tuple[float, int]] = [(0.0, source)]
    while queue:
        current_dist, node = heapq.heappop(queue)
        if current_dist > distances[node]:
            continue
        if node == target:
            return current_dist
        for neighbour, weight in graph[node]:
            next_dist = current_dist + float(weight)
            if next_dist < distances[neighbour]:
                distances[neighbour] = next_dist
                heapq.heappush(queue, (next_dist, neighbour))
    return float("inf")
