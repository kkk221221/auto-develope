"""Baseline shortest path solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

import heapq
from typing import Dict, Iterable, List, Sequence, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def _dijkstra_from_adj(graph: Sequence[Sequence[Tuple[int, float]]], source: int, target: int) -> float:
    distances = [float("inf")] * len(graph)
    distances[source] = 0.0
    queue: List[Tuple[float, int]] = [(0.0, source)]
    relax_count = 0
    while queue:
        current, node = heapq.heappop(queue)
        if current > distances[node]:
            continue
        if node == target:
            telemetry_tags.append(f"relax_count:{relax_count}")
            return current
        for neighbour, weight in graph[node]:
            candidate = current + float(weight)
            if candidate < distances[neighbour]:
                distances[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
                relax_count += 1
    if distances[target] == float("inf"):
        raise ValueError(f"Target not reachable from source")
    telemetry_tags.append(f"relax_count:{relax_count}")
    return distances[target]

# EVOLVE-BLOCK-END
