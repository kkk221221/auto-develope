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
    if "nodes" not in sample:
        raise ValueError("Missing 'nodes' in sample")
    nodes = int(sample["nodes"])
    if "source" not in sample:
        raise ValueError("Missing 'source' in sample")
    source = int(sample["source"])
    if "target" not in sample:
        raise ValueError("Missing 'target' in sample")
    target = int(sample["target"])
    if not 0 <= source < nodes:
        raise ValueError(f"Source node {source} is out of bounds")
    if not 0 <= target < nodes:
        raise ValueError(f"Target node {target} is out of bounds")
    edges = sample.get("edges", [])
    adjacency: List[List[Tuple[int, float]]] = [[] for _ in range(nodes)]
    for edge in edges:
        if not isinstance(edge, (list, tuple)) or len(edge) != 3:
            raise ValueError(f"Malformed edge: {edge!r}")
        u, v, w = edge
        try:
            u, v = int(u), int(v)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid node identifiers: {u!r}, {v!r}") from e
        if not isinstance(w, (int, float)):
            raise ValueError(f"Invalid weight: {w!r}")
        weight = float(w)
        if weight < 0:
            raise ValueError(f"Negative weight: {w!r}")
        if 0 <= u < nodes and 0 <= v < nodes:
            adjacency[u].append((v, weight))
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
    if distances[target] == float("inf"):
        raise ValueError(f"Target not reachable from source")
    return distances[target]


# EVOLVE-BLOCK-END
