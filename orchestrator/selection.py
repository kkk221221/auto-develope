"""Candidate selection and archive maintenance utilities."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, TYPE_CHECKING

from .models import ArchiveState, ProgramCandidate

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .generation import ProgramGenerator
    from .prompt_policy import PromptBandit


OBJECTIVES: Sequence[Tuple[str, bool]] = (
    ("accuracy", True),
    ("runtime_ms", False),
    ("robustness", True),
    ("memory_peak_mb", False),
)


def _dominates(lhs: ProgramCandidate, rhs: ProgramCandidate, eps: float = 1e-9) -> bool:
    """Returns True if lhs Pareto dominates rhs under the configured objectives."""

    better_or_equal = True
    strictly_better = False
    for attr, maximize in OBJECTIVES:
        left_val = getattr(lhs.metrics, attr)
        right_val = getattr(rhs.metrics, attr)
        if maximize:
            if left_val + eps < right_val:
                return False
            if left_val > right_val + eps:
                strictly_better = True
        else:
            if left_val - eps > right_val:
                return False
            if left_val + eps < right_val:
                strictly_better = True
    return better_or_equal and strictly_better


def _non_dominated_sort(candidates: Iterable[ProgramCandidate]) -> List[List[ProgramCandidate]]:
    population = list(candidates)
    domination_counts: Dict[str, int] = {c.id: 0 for c in population}
    dominates: Dict[str, List[str]] = {c.id: [] for c in population}
    fronts: List[List[ProgramCandidate]] = []

    for i, candidate in enumerate(population):
        for other in population[i + 1 :]:
            if _dominates(candidate, other):
                dominates[candidate.id].append(other.id)
                domination_counts[other.id] += 1
            elif _dominates(other, candidate):
                dominates[other.id].append(candidate.id)
                domination_counts[candidate.id] += 1

    first_front = [c for c in population if domination_counts[c.id] == 0]
    for c in first_front:
        c.pareto_rank = 0
    fronts.append(first_front)

    current_front = first_front
    rank = 1
    while current_front:
        next_front: List[ProgramCandidate] = []
        for candidate in current_front:
            for dominated_id in dominates[candidate.id]:
                domination_counts[dominated_id] -= 1
                if domination_counts[dominated_id] == 0:
                    dominated_candidate = next(c for c in population if c.id == dominated_id)
                    dominated_candidate.pareto_rank = rank
                    next_front.append(dominated_candidate)
        if next_front:
            fronts.append(next_front)
        current_front = next_front
        rank += 1
    return fronts


def _crowding_distance(front: Sequence[ProgramCandidate]) -> Dict[str, float]:
    if not front:
        return {}
    distances: Dict[str, float] = {candidate.id: 0.0 for candidate in front}
    for attr, maximize in OBJECTIVES:
        sorted_front = sorted(front, key=lambda c: getattr(c.metrics, attr), reverse=maximize)
        distances[sorted_front[0].id] = math.inf
        distances[sorted_front[-1].id] = math.inf
        values = [getattr(c.metrics, attr) for c in sorted_front]
        min_val, max_val = min(values), max(values)
        span = max(max_val - min_val, 1e-9)
        for idx in range(1, len(sorted_front) - 1):
            prev_val = getattr(sorted_front[idx - 1].metrics, attr)
            next_val = getattr(sorted_front[idx + 1].metrics, attr)
            distances[sorted_front[idx].id] += (next_val - prev_val) / span
    for candidate in front:
        candidate.crowding_distance = distances[candidate.id]
    return distances


@dataclass
class ArchiveManager:
    state: ArchiveState
    complexity_bins: int = 8
    robustness_bins: int = 8
    candidates: Dict[str, ProgramCandidate] = field(default_factory=dict)
    _front_cache: List[List[str]] = field(default_factory=list)

    def update(self, candidate: ProgramCandidate) -> None:
        self.candidates[candidate.id] = candidate
        candidate.novelty_score = self._compute_novelty(candidate)
        self._update_map_elites(candidate)
        fronts = _non_dominated_sort(self.candidates.values())
        self._front_cache = [[c.id for c in front] for front in fronts]
        self.state.pareto_front = self._front_cache[0] if self._front_cache else []

    def get_fronts(self) -> List[List[ProgramCandidate]]:
        return [
            [self.candidates[candidate_id] for candidate_id in front if candidate_id in self.candidates]
            for front in self._front_cache
        ]

    def sample_diverse_candidate(self) -> Optional[ProgramCandidate]:
        if not self.candidates:
            return None
        if self.state.map_elites_cells:
            occupants = [cid for cid in self.state.map_elites_cells.values() if cid in self.candidates]
            if occupants:
                return self.candidates[random.choice(occupants)]
        if self.state.pareto_front:
            candidates = [cid for cid in self.state.pareto_front if cid in self.candidates]
            if candidates:
                return self.candidates[random.choice(candidates)]
        return random.choice(list(self.candidates.values()))

    def _compute_novelty(self, candidate: ProgramCandidate, k: int = 5) -> float:
        if len(self.candidates) <= 1 or not candidate.behavior:
            return 1.0
        distances: List[float] = []
        for other in self.candidates.values():
            if other.id == candidate.id or not other.behavior:
                continue
            distances.append(self._behavior_distance(candidate, other))
        if not distances:
            return 1.0
        distances.sort()
        window = distances[: min(k, len(distances))]
        return sum(window) / len(window)

    def _behavior_distance(self, lhs: ProgramCandidate, rhs: ProgramCandidate) -> float:
        lhs_cov = set(lhs.behavior.coverage_bits)
        rhs_cov = set(rhs.behavior.coverage_bits)
        union = lhs_cov | rhs_cov
        intersection = lhs_cov & rhs_cov
        coverage_distance = 1.0 if not union else 1.0 - len(intersection) / len(union)
        runtime_norm = abs(lhs.metrics.runtime_ms - rhs.metrics.runtime_ms) / max(
            lhs.metrics.runtime_ms, rhs.metrics.runtime_ms, 1.0
        )
        accuracy_delta = abs(lhs.metrics.accuracy - rhs.metrics.accuracy)
        robustness_delta = abs(lhs.metrics.robustness - rhs.metrics.robustness)
        return coverage_distance + runtime_norm + accuracy_delta + robustness_delta

    def _update_map_elites(self, candidate: ProgramCandidate) -> None:
        key = self._map_key(candidate)
        if key is None:
            return
        incumbent_id = self.state.map_elites_cells.get(key)
        if incumbent_id is None:
            self.state.map_elites_cells[key] = candidate.id
            return
        incumbent = self.candidates.get(incumbent_id)
        if incumbent is None or candidate.metrics.accuracy > incumbent.metrics.accuracy:
            self.state.map_elites_cells[key] = candidate.id

    def _map_key(self, candidate: ProgramCandidate) -> Optional[Tuple[int, int]]:
        if self.complexity_bins <= 0 or self.robustness_bins <= 0:
            return None
        loc = max(candidate.metrics.loc, 0)
        robustness = max(0.0, min(1.0, candidate.metrics.robustness))
        step = max(1, math.ceil(100 / max(self.complexity_bins, 1)))
        complexity_bin = min(self.complexity_bins - 1, loc // step)
        robustness_bin = min(self.robustness_bins - 1, int(robustness * self.robustness_bins))
        return (int(complexity_bin), int(robustness_bin))


@dataclass
class SelectionStrategy:
    """Maintains a rolling population using NSGA-II inspired ranking."""

    population_size: int
    archive: ArchiveManager
    default_prompt_arm: str = "mutate.perf_first"
    novelty_alpha: float = 1.0
    novelty_tau: int = 8
    _population: Dict[str, ProgramCandidate] = field(default_factory=dict)

    def observe_candidate(self, candidate: ProgramCandidate) -> None:
        self._population[candidate.id] = candidate
        self._truncate_population()

    def _truncate_population(self) -> None:
        if len(self._population) <= self.population_size * 3:
            return
        ranked = self._ranked_candidates()
        survivors = {candidate.id for candidate in ranked[: self.population_size * 2]}
        self._population = {cid: self._population[cid] for cid in survivors}

    def _ranked_candidates(self) -> List[ProgramCandidate]:
        fronts = self.archive.get_fronts()
        ranked: List[ProgramCandidate] = []
        for rank, front in enumerate(fronts):
            if not front:
                continue
            distances = _crowding_distance(front)
            sorted_front = sorted(
                front,
                key=lambda cand: (
                    rank,
                    -cand.novelty_score,
                    -distances.get(cand.id, 0.0),
                ),
            )
            ranked.extend(sorted_front)
        leftovers = [cand for cid, cand in self._population.items() if cand not in ranked]
        ranked.extend(leftovers)
        return ranked

    def select_next(
        self,
        generator: "ProgramGenerator",
        prompt_bandit: "PromptBandit",
    ) -> Optional[ProgramCandidate]:
        if not self._population:
            return None
        parent = self._sample_parent()
        if not parent:
            return None
        arm = parent.prompt_arm if parent.prompt_arm in prompt_bandit.templates else self.default_prompt_arm
        backend = prompt_bandit.backend_for_arm(arm)
        return generator.spawn_candidate(
            arm,
            backend,
            parents=(*parent.parents, parent.id),
            generation=parent.generation + 1,
        )

    def _sample_parent(self) -> Optional[ProgramCandidate]:
        fronts = self.archive.get_fronts()
        if not fronts:
            return random.choice(list(self._population.values()))
        weighted: List[Tuple[float, ProgramCandidate]] = []
        for rank, front in enumerate(fronts):
            if not front:
                continue
            distances = _crowding_distance(front)
            for candidate in front:
                if candidate.id not in self._population:
                    continue
                novelty_factor = math.exp(
                    min(candidate.novelty_score, 5.0) * self.novelty_alpha / max(self.novelty_tau, 1)
                )
                distance = distances.get(candidate.id, 0.0)
                rank_weight = 1.0 / (1.0 + rank)
                weight = rank_weight * (1.0 + distance) * novelty_factor
                weighted.append((weight, candidate))
        if not weighted:
            return random.choice(list(self._population.values()))
        total = sum(weight for weight, _ in weighted)
        pick = random.random() * total
        cumulative = 0.0
        for weight, candidate in weighted:
            cumulative += weight
            if cumulative >= pick:
                return candidate
        return weighted[-1][1]

    def bootstrap_population(self, generator: "ProgramGenerator") -> List[ProgramCandidate]:
        seeds: List[ProgramCandidate] = []
        for _ in range(self.population_size):
            seeds.append(generator.spawn_candidate(self.default_prompt_arm, backend="flash"))
        return seeds

