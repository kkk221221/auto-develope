"""Baseline shortest path solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

import heapq
from typing import Dict, Iterable, List, Sequence, Tuple


# EVOLVE-BLOCK-START: baseline implementation
# EVOLVE
    # Implement Dijkstra's algorithm using adjacency list and priority queue for performance
    distances = {node: float('inf') for node in graph.nodes}
    previous = {node: None for node in graph.nodes}
    distances[start] = 0
    pq = [(0, start)]  # priority queue (min-heap)
    import heapq
    relaxation_count = 0  # telemetry: count of relaxations

    while pq:
        current_dist, current = heapq.heappop(pq)
        if current_dist > distances[current]:
            continue  # Skip outdated entries

        for neighbor, weight in graph.adjacency[current]:
            new_distance = distances[current] + weight
            if new_distance < distances[neighbor]:
                distances[neighbor] = new_distance
                previous[neighbor] = current
                heapq.heappush(pq, (new_distance, neighbor))
                relaxation_count += 1  # increment on relaxation

# EVOLVE-BLOCK-END
