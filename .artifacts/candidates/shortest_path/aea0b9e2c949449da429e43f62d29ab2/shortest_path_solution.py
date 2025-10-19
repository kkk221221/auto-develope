"""Baseline shortest path solver with EVOLVE-BLOCK markers."""
from __future__ import annotations

import heapq
from typing import Dict, Iterable, List, Sequence, Tuple


# EVOLVE-BLOCK-START: baseline implementation
def shortest_path(graph, start, end):\n    import heapq\n    visited = set()\n    queue = [(0, start)]\n    relax_count = 0\n    while queue:\n        dist, node = heapq.heappop(queue)\n        if node in visited:\n            continue\n        visited.add(node)\n        if node == end:\n            telemetry_tags.append(f'relax_count:{relax_count}')\n            return dist\n        for neighbor, weight in graph[node]:\n            if neighbor not in visited:\n                heapq.heappush(queue, (dist + weight, neighbor))\n                relax_count += 1\n    return -1

# EVOLVE-BLOCK-END
