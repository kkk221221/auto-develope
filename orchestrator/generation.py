"""Candidate generation utilities for the self-evolving system."""
from __future__ import annotations

import logging
import re
import textwrap
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Tuple, cast

from .agents import AgentGeneration, GeminiAgentAdapter, GeminiAgentError
from .ast_crossover import perform_ast_crossover
from .git_lineage import GitLineageError, GitLineageTracker
from .models import BehaviorFeatures, ProgramCandidate
from .prompt_policy import PromptMaterialization
from .problem_specs import ProblemSpec

LOGGER = logging.getLogger(__name__)


def _replace_evolve_block(source: str, new_block: str) -> str:
    pattern = re.compile(
        r"(# EVOLVE-BLOCK-START.*?\n)(.*?)(\n# EVOLVE-BLOCK-END)",
        flags=re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        raise ValueError("Could not locate EVOLVE-BLOCK markers in source")
    prefix, _, suffix = match.groups()
    before = source[: match.start()]
    after = source[match.end() :]
    replacement = f"{prefix}{textwrap.dedent(new_block).strip()}\n{suffix}"
    return f"{before}{replacement}{after}"


def _extract_evolve_block(source: str) -> str:
    pattern = re.compile(
        r"# EVOLVE-BLOCK-START.*?\n(.*?)\n# EVOLVE-BLOCK-END",
        flags=re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        raise ValueError("Baseline source missing EVOLVE block")
    return textwrap.dedent(match.group(1)).strip()


# --- Sample problem snippets -------------------------------------------------


def _sample_baseline() -> str:
    return """
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    total = 0
    count = 0
    for a, b in pairs:
        total += a + b
        count += 1
    if count == 0:
        return 0.0
    return total / count
"""


def _sample_perf_variant() -> str:
    return """
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    total = 0.0
    count = 0
    for a, b in pairs:
        total += (a + b) * 0.5
        total += 0.5 * (a + b)
        count += 1
    return total / count if count else 0.0
"""


def _sample_robust_variant() -> str:
    return """
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    cleaned = []
    for item in pairs:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            continue
        a, b = item
        try:
            cleaned.append((float(a), float(b)))
        except (TypeError, ValueError):
            continue
    if not cleaned:
        return 0.0
    return sum(a + b for a, b in cleaned) / len(cleaned)
"""


def _sample_simple_variant() -> str:
    return """
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    iterator = tuple(pairs)
    length = len(iterator)
    if length == 0:
        return 0.0
    total_a = sum(pair[0] for pair in iterator)
    total_b = sum(pair[1] for pair in iterator)
    return (total_a + total_b) / length
"""


def _sample_exploration_variant() -> str:
    return """
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    iterator = list(pairs)
    if not iterator:
        return 0.0
    weighted = [0.6 * a + 0.4 * b for a, b in iterator]
    baseline = sum(a + b for a, b in iterator) / len(iterator)
    return (baseline + sum(weighted) / len(weighted)) / 2.0
"""


# --- Shortest path snippets --------------------------------------------------


def _shortest_baseline() -> str:
    return """
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += _dijkstra_dense(sample)
        count += 1
    return total / count if count else 0.0


def _dijkstra_dense(sample: Dict[str, object]) -> float:
    nodes = int(sample.get("nodes", 0))
    edges = sample.get("edges", [])
    source = int(sample.get("source", 0))
    target = int(sample.get("target", nodes - 1))
    graph: List[List[Tuple[int, float]]] = [[] for _ in range(nodes)]
    for edge in edges:
        try:
            u, v, w = edge
        except (TypeError, ValueError):
            continue
        u, v = int(u), int(v)
        weight = max(0.0, float(w))
        if 0 <= u < nodes and 0 <= v < nodes:
            graph[u].append((v, weight))
    return _dijkstra_from_adj(graph, source, target)


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
"""


def _shortest_perf_variant() -> str:
    return """
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
"""


def _shortest_robust_variant() -> str:
    return """
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += _safe_shortest(sample)
        count += 1
    return total / count if count else 0.0


def _safe_shortest(sample: Dict[str, object]) -> float:
    nodes = int(sample.get("nodes", 0))
    graph: Dict[int, List[Tuple[int, float]]] = {i: [] for i in range(nodes)}
    for edge in sample.get("edges", []):
        try:
            u, v, w = edge
        except (TypeError, ValueError):
            continue
        u, v = int(u), int(v)
        if u not in graph or v not in graph:
            continue
        graph[u].append((v, max(1.0, float(w))))
    distance = _dijkstra_guarded(graph, int(sample.get("source", 0)), int(sample.get("target", nodes - 1)))
    if distance == float("inf"):
        return float(nodes * 10)
    return distance


def _dijkstra_guarded(graph: Dict[int, List[Tuple[int, float]]], source: int, target: int) -> float:
    distances = {node: float("inf") for node in graph}
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
            if candidate < distances.get(neighbour, float("inf")):
                distances[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
    return float("inf")
"""


def _shortest_simple_variant() -> str:
    return """
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += _breadth_first_weight(sample)
        count += 1
    return total / count if count else 0.0


def _breadth_first_weight(sample: Dict[str, object]) -> float:
    nodes = int(sample.get("nodes", 0))
    adjacency = {i: [] for i in range(nodes)}
    for edge in sample.get("edges", []):
        try:
            u, v, w = edge
        except (TypeError, ValueError):
            continue
        u, v = int(u), int(v)
        if 0 <= u < nodes and 0 <= v < nodes:
            adjacency[u].append((v, max(1.0, float(w))))
    source = int(sample.get("source", 0))
    target = int(sample.get("target", nodes - 1))
    frontier = [(source, 0.0)]
    best = {source: 0.0}
    while frontier:
        node, cost = frontier.pop(0)
        if node == target:
            return cost
        for neighbour, weight in adjacency.get(node, []):
            candidate = cost + weight
            if candidate < best.get(neighbour, float("inf")):
                best[neighbour] = candidate
                frontier.append((neighbour, candidate))
    return float("inf")
"""


def _shortest_exploration_variant() -> str:
    return """
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        greedy = _breadth_first_weight(sample)
        precise = _heap_shortest(sample)
        total += (greedy + precise) / 2.0
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


def _breadth_first_weight(sample: Dict[str, object]) -> float:
    nodes = int(sample.get("nodes", 0))
    adjacency = {i: [] for i in range(nodes)}
    for edge in sample.get("edges", []):
        try:
            u, v, w = edge
        except (TypeError, ValueError):
            continue
        u, v = int(u), int(v)
        if 0 <= u < nodes and 0 <= v < nodes:
            adjacency[u].append((v, max(1.0, float(w))))
    source = int(sample.get("source", 0))
    target = int(sample.get("target", nodes - 1))
    frontier = [(source, 0.0)]
    best = {source: 0.0}
    while frontier:
        node, cost = frontier.pop(0)
        if node == target:
            return cost
        for neighbour, weight in adjacency.get(node, []):
            candidate = cost + weight
            if candidate < best.get(neighbour, float("inf")):
                best[neighbour] = candidate
                frontier.append((neighbour, candidate))
    return float("inf")
"""


# --- Knapsack snippets ------------------------------------------------------


def _knapsack_baseline() -> str:
    return """
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += float(_dp_solver(sample))
        count += 1
    return total / count if count else 0.0


def _dp_solver(sample: Dict[str, object]) -> int:
    capacity = int(sample.get("capacity", 0))
    items = _normalise_items(sample.get("items", []))
    dp = [0] * (capacity + 1)
    for value, weight in items:
        for current in range(capacity, weight - 1, -1):
            candidate = dp[current - weight] + value
            if candidate > dp[current]:
                dp[current] = candidate
    return max(dp) if dp else 0


def _normalise_items(raw_items: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    cleaned: List[Tuple[int, int]] = []
    for item in raw_items:
        try:
            value, weight = item
        except (TypeError, ValueError):
            continue
        value = int(value)
        weight = int(weight)
        if weight <= 0:
            continue
        cleaned.append((max(0, value), weight))
    return cleaned
"""


def _knapsack_perf_variant() -> str:
    return """
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += float(_dense_dp(sample))
        count += 1
    return total / count if count else 0.0


def _dense_dp(sample: Dict[str, object]) -> int:
    capacity = int(sample.get("capacity", 0))
    items = _normalise_items(sample.get("items", []))
    dp = [0] * (capacity + 1)
    for value, weight in items:
        for current in range(weight, capacity + 1):
            candidate = dp[current - weight] + value
            if candidate > dp[current]:
                dp[current] = candidate
    return dp[capacity]


def _normalise_items(raw_items: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    cleaned: List[Tuple[int, int]] = []
    for item in raw_items:
        try:
            value, weight = item
        except (TypeError, ValueError):
            continue
        value = int(value)
        weight = int(weight)
        if weight <= 0:
            continue
        cleaned.append((max(0, value), weight))
    cleaned.sort(key=lambda item: (item[1], -item[0]))
    return cleaned
"""


def _knapsack_robust_variant() -> str:
    return """
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += float(_robust_knapsack(sample))
        count += 1
    return total / count if count else 0.0


def _robust_knapsack(sample: Dict[str, object]) -> int:
    capacity = max(0, int(sample.get("capacity", 0)))
    items = _filter_items(sample.get("items", []))
    dp = [0] * (capacity + 1)
    for value, weight in items:
        for current in range(capacity, weight - 1, -1):
            candidate = dp[current - weight] + value
            if candidate > dp[current]:
                dp[current] = candidate
    return max(dp) if dp else 0


def _filter_items(raw_items: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    filtered: List[Tuple[int, int]] = []
    for item in raw_items:
        try:
            value, weight = item
        except (TypeError, ValueError):
            continue
        value = int(value)
        weight = int(weight)
        if value <= 0 or weight <= 0:
            continue
        filtered.append((value, weight))
    return filtered
"""


def _knapsack_simple_variant() -> str:
    return """
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += float(_greedy_knapsack(sample))
        count += 1
    return total / count if count else 0.0


def _greedy_knapsack(sample: Dict[str, object]) -> int:
    capacity = int(sample.get("capacity", 0))
    items = _filter_items(sample.get("items", []))
    items.sort(key=lambda item: item[0] / item[1], reverse=True)
    value = 0
    weight = 0
    for v, w in items:
        if weight + w > capacity:
            continue
        weight += w
        value += v
    return value


def _filter_items(raw_items: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    filtered: List[Tuple[int, int]] = []
    for item in raw_items:
        try:
            value, weight = item
        except (TypeError, ValueError):
            continue
        value = int(value)
        weight = int(weight)
        if weight <= 0:
            continue
        filtered.append((max(0, value), weight))
    return filtered
"""


def _knapsack_exploration_variant() -> str:
    return """
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        dp_value = float(_dense_dp(sample))
        greedy_value = float(_greedy_knapsack(sample))
        total += max(dp_value, 0.6 * dp_value + 0.4 * greedy_value)
        count += 1
    return total / count if count else 0.0


def _dense_dp(sample: Dict[str, object]) -> int:
    capacity = int(sample.get("capacity", 0))
    items = _filter_items(sample.get("items", []))
    dp = [0] * (capacity + 1)
    for value, weight in items:
        for current in range(capacity, weight - 1, -1):
            candidate = dp[current - weight] + value
            if candidate > dp[current]:
                dp[current] = candidate
    return max(dp) if dp else 0


def _greedy_knapsack(sample: Dict[str, object]) -> int:
    capacity = int(sample.get("capacity", 0))
    items = _filter_items(sample.get("items", []))
    items.sort(key=lambda item: item[0] / item[1], reverse=True)
    value = 0
    weight = 0
    for v, w in items:
        if weight + w > capacity:
            continue
        weight += w
        value += v
    return value


def _filter_items(raw_items: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    filtered: List[Tuple[int, int]] = []
    for item in raw_items:
        try:
            value, weight = item
        except (TypeError, ValueError):
            continue
        value = max(0, int(value))
        weight = max(1, int(weight))
        filtered.append((value, weight))
    return filtered
"""


PROBLEM_SNIPPETS: Dict[str, Dict[str, Callable[[], str]]] = {
    "sample_problem": {
        "baseline": _sample_baseline,
        "perf_first": _sample_perf_variant,
        "robust_first": _sample_robust_variant,
        "simplicity_first": _sample_simple_variant,
        "exploration": _sample_exploration_variant,
    },
    "shortest_path": {
        "baseline": _shortest_baseline,
        "perf_first": _shortest_perf_variant,
        "robust_first": _shortest_robust_variant,
        "simplicity_first": _shortest_simple_variant,
        "exploration": _shortest_exploration_variant,
    },
    "knapsack": {
        "baseline": _knapsack_baseline,
        "perf_first": _knapsack_perf_variant,
        "robust_first": _knapsack_robust_variant,
        "simplicity_first": _knapsack_simple_variant,
        "exploration": _knapsack_exploration_variant,
    },
}


def _parse_failure_signals(failure_context: Optional[str]) -> Dict[str, bool]:
    text = (failure_context or "").lower()
    return {
        "timeout": any(keyword in text for keyword in ["timeout", "time limit", "deadline"]),
        "memory": "memory" in text or "oom" in text,
        "type": "typeerror" in text or "attributeerror" in text,
        "inf": "inf" in text or "nan" in text,
        "negative": "negative" in text or "underflow" in text,
    }


def _repair_snippet(problem_id: str, failure_context: Optional[str]) -> str:
    signals = _parse_failure_signals(failure_context)
    if problem_id == "shortest_path":
        guard_negative = ""
        if signals["negative"]:
            guard_negative = "            if weight < 0:\n                continue\n"
        throttling = ""
        if signals["timeout"]:
            throttling = "        if len(queue) > nodes * 4:\n            heapq.heapify(queue)\n"
        safe_return = (
            "    return float('inf')  # unreachable when guarded"
            if signals["inf"]
            else "    return float('inf')"
        )
        return f"""
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        distance = _safe_shortest(sample)
        total += distance
        count += 1
    return total / count if count else 0.0


def _safe_shortest(sample: Dict[str, object]) -> float:
    nodes = int(sample.get("nodes", 0))
    adjacency = {{i: [] for i in range(nodes)}}
    for edge in sample.get("edges", []):
        try:
            u, v, w = edge
        except (TypeError, ValueError):
            continue
        u, v = int(u), int(v)
        if u not in adjacency or v not in adjacency:
            continue
        adjacency[u].append((v, max(1.0, float(w))))
    source = int(sample.get("source", 0))
    target = int(sample.get("target", nodes - 1))
    return _dijkstra_guarded(adjacency, source, target)


def _dijkstra_guarded(graph: Dict[int, List[Tuple[int, float]]], source: int, target: int) -> float:
    distances = {{node: float("inf") for node in graph}}
    distances[source] = 0.0
    queue: List[Tuple[float, int]] = [(0.0, source)]
    while queue:
        current, node = heapq.heappop(queue)
        if current > distances[node]:
            continue
        if node == target:
            return current
        for neighbour, weight in graph.get(node, []):
{guard_negative}
            candidate = current + weight
            if candidate < distances.get(neighbour, float("inf")):
                distances[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
{throttling}
{safe_return}
"""
    if problem_id == "knapsack":
        normaliser = "    items = sample.get(\"items\", [])\n"
        if signals["type"]:
            normaliser = "    items = _normalise_items(sample.get(\"items\", []))\n"
        early_stop = ""
        if signals["timeout"]:
            early_stop = "            if dp[current] >= capacity:\n                break\n"
        return f"""
def solve(samples: Iterable[Dict[str, object]]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += float(_repair_knapsack(sample))
        count += 1
    return total / count if count else 0.0


def _repair_knapsack(sample: Dict[str, object]) -> int:
    capacity = max(0, int(sample.get("capacity", 0)))
{normaliser}
    dp = [0] * (capacity + 1)
    for value, weight in items:
        for current in range(capacity, weight - 1, -1):
            candidate = dp[current - weight] + value
            if candidate > dp[current]:
                dp[current] = candidate
{early_stop}
    return max(dp) if dp else 0


def _normalise_items(raw_items: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    cleaned: List[Tuple[int, int]] = []
    for item in raw_items:
        try:
            value, weight = item
        except (TypeError, ValueError):
            continue
        weight = int(weight)
        value = int(value)
        if weight <= 0:
            continue
        cleaned.append((max(0, value), weight))
    cleaned.sort(key=lambda item: item[0] / item[1], reverse=True)
    return cleaned
"""
    # Default repair focuses on robustness for the sample problem.
    left = "float(a)" if signals["type"] else "a"
    right = "float(b)" if signals["type"] else "b"
    guard_line = (
        "        if total == float('inf') or total != total:\n            total = 0.0"
        if signals["inf"]
        else ""
    )
    return f"""
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    total = 0.0
    count = 0
    for item in pairs:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            continue
        a, b = item
        try:
            total += {left} + {right}
            count += 1
        except (TypeError, ValueError):
            continue
{guard_line}
    return total / count if count else 0.0
"""


@dataclass
class ProgramGenerator:
    """Applies mutations or agent-supplied patches to seed candidates."""

    problem_specs: Mapping[str, ProblemSpec]
    output_root: Path
    agent: Optional[GeminiAgentAdapter] = None
    lineage_tracker: Optional[GitLineageTracker] = None
    _agent_enabled: bool = field(init=False, default=True)

    def __post_init__(self) -> None:
        if not self.problem_specs:
            raise ValueError("ProgramGenerator requires at least one problem specification")
        self.baseline_sources: Dict[str, str] = {}
        self.baseline_blocks: Dict[str, str] = {}
        for problem_id, spec in self.problem_specs.items():
            source = spec.baseline_path.read_text(encoding="utf-8")
            self.baseline_sources[problem_id] = source
            self.baseline_blocks[problem_id] = _extract_evolve_block(source)
        self.default_problem = next(iter(self.problem_specs))
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._agent_enabled = self.agent is not None

    def spawn_candidate(
        self,
        arm: str,
        prompt: PromptMaterialization,
        *,
        problem_id: Optional[str] = None,
        parents: Tuple[str, ...] | None = None,
        generation: int = 0,
        intent: str = "mutate",
        failure_context: Optional[str] = None,
    ) -> ProgramCandidate:
        target_problem = problem_id or self.default_problem
        if target_problem not in self.problem_specs:
            raise KeyError(f"Unknown problem id: {target_problem}")
        arm_key = arm.rsplit(".", 1)[-1]
        snippet, metadata = self._materialise_snippet(
            target_problem,
            arm_key,
            prompt,
            intent=intent,
            failure_context=failure_context,
        )
        baseline_source = self.baseline_sources[target_problem]
        mutated_source = _replace_evolve_block(baseline_source, snippet)
        candidate_id = uuid.uuid4().hex
        candidate_path = self._prepare_candidate_path(target_problem, candidate_id)
        candidate_path.write_text(mutated_source, encoding="utf-8")
        patch_payload: Dict[str, object] = {
            "diff_type": "sr",
            "payload": textwrap.dedent(snippet).strip(),
            "metadata": metadata,
            "intent": intent,
            "problem_id": target_problem,
        }
        parent_ids = tuple(parents or ())
        candidate = ProgramCandidate(
            id=candidate_id,
            parents=parent_ids,
            generation=generation,
            prompt_arm=arm,
            llm_backend=prompt.backend,
            patch_payload=patch_payload,
            problem_id=target_problem,
            source_path=str(candidate_path),
        )
        self._record_lineage(candidate)
        return candidate

    def spawn_crossover_candidate(
        self,
        parent_a: ProgramCandidate,
        parent_b: ProgramCandidate,
    ) -> ProgramCandidate:
        """Produces a child candidate via AST-guided crossover."""

        if parent_a.problem_id != parent_b.problem_id:
            raise ValueError("Crossover requires parents from the same problem island")
        problem_id = parent_a.problem_id
        result = perform_ast_crossover(
            parent_a,
            parent_b,
            base_source=self.baseline_sources[problem_id],
        )
        candidate_id = uuid.uuid4().hex
        candidate_path = self._prepare_candidate_path(problem_id, candidate_id)
        candidate_path.write_text(result.merged_source, encoding="utf-8")

        candidate = ProgramCandidate(
            id=candidate_id,
            parents=(parent_a.id, parent_b.id),
            generation=max(parent_a.generation, parent_b.generation) + 1,
            prompt_arm="crossover.ast_mix",
            llm_backend=parent_a.llm_backend,
            patch_payload=result.patch_payload,
            source_path=str(candidate_path),
            behavior=result.behavior or BehaviorFeatures(),
            problem_id=problem_id,
        )
        metadata = candidate.patch_payload.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            candidate.patch_payload["metadata"] = metadata
        metadata["plan"] = {
            "strategy": result.plan.strategy,
            "description": result.plan.description,
            "fragments": result.plan.fragments,
            "parents": list(result.plan.parents),
            "conflicts": list(result.plan.conflicts),
        }
        self._record_lineage(candidate)
        return candidate

    def _prepare_candidate_path(self, problem_id: str, candidate_id: str) -> Path:
        candidate_dir = self.output_root / problem_id / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=False)
        baseline_name = self.problem_specs[problem_id].baseline_path.name
        return candidate_dir / baseline_name

    def _materialise_snippet(
        self,
        problem_id: str,
        arm_key: str,
        prompt: PromptMaterialization,
        *,
        intent: str,
        failure_context: Optional[str],
    ) -> Tuple[str, Dict[str, object]]:
        prompt_to_use = prompt
        if failure_context:
            prompt_to_use = prompt.with_context(failure_context)
        if self.agent and self._agent_enabled:
            try:
                agent_result: AgentGeneration = self.agent.generate(prompt_to_use)
                snippet = agent_result.snippet
                metadata: Dict[str, object] = cast(
                    Dict[str, object],
                    {
                        "arm": arm_key,
                        "strategy": "gemini_cli",
                        "telemetry": list(agent_result.telemetry_tags),
                        **dict(agent_result.metadata),
                        "problem_id": problem_id,
                        "intent": intent,
                    },
                )
                return snippet, metadata
            except GeminiAgentError as error:
                LOGGER.warning("Gemini CLI fallback for %s: %s", problem_id, error)
                self._agent_enabled = False
        if intent == "repair":
            snippet = _repair_snippet(problem_id, failure_context)
            metadata = cast(
                Dict[str, object],
                {
                    "arm": arm_key,
                    "strategy": "repair_template",
                    "problem_id": problem_id,
                    "intent": intent,
                },
            )
            return snippet, metadata
        snippet_factory = PROBLEM_SNIPPETS.get(problem_id, {}).get(arm_key)
        if snippet_factory is None:
            snippet_factory = PROBLEM_SNIPPETS.get(problem_id, {}).get("baseline")
        if snippet_factory is None:
            def baseline_factory() -> str:
                return self.baseline_blocks[problem_id]

            snippet_factory = baseline_factory
        snippet = snippet_factory()
        metadata = cast(
            Dict[str, object],
            {
                "arm": arm_key,
                "strategy": "template_mutation",
                "prompt_generation": prompt.generation,
                "problem_id": problem_id,
                "intent": intent,
            },
        )
        return snippet, metadata

    def _record_lineage(self, candidate: ProgramCandidate) -> None:
        if not self.lineage_tracker:
            return
        try:
            commit = self.lineage_tracker.record_candidate(candidate)
        except GitLineageError as error:  # pragma: no cover - best effort
            LOGGER.warning("Failed to record lineage for %s: %s", candidate.id, error)
            return
        candidate.lineage_commit = commit
        metadata_obj = candidate.patch_payload.setdefault("metadata", {})
        if not isinstance(metadata_obj, dict):
            metadata_obj = {}
            candidate.patch_payload["metadata"] = metadata_obj
        metadata_obj["git_commit"] = commit
