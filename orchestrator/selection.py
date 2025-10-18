"""Candidate selection and archive maintenance utilities."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from .models import ArchiveState, ProgramCandidate
from .generation import ProgramGenerator


@dataclass
class ArchiveManager:
    state: ArchiveState

    def update(self, candidate: ProgramCandidate) -> None:
        self.state.pareto_front.append(candidate.id)


@dataclass
class SelectionStrategy:
    """Maintains a rolling buffer of candidates and samples new ones."""

    population_size: int
    default_prompt_arm: str = "mutate.perf_first"
    buffer: List[ProgramCandidate] = field(default_factory=list)

    def observe_candidate(self, candidate: ProgramCandidate) -> None:
        self.buffer.append(candidate)
        self.buffer.sort(key=lambda c: (c.metrics.accuracy, -c.metrics.runtime_ms), reverse=True)
        if len(self.buffer) > self.population_size:
            self.buffer = self.buffer[: self.population_size]

    def select_next(self) -> Optional[ProgramCandidate]:
        if not self.buffer:
            return None
        top_k = max(1, len(self.buffer) // 2)
        return random.choice(self.buffer[:top_k])

    def bootstrap_population(self, generator: ProgramGenerator) -> List[ProgramCandidate]:
        seeds: List[ProgramCandidate] = []
        for _ in range(self.population_size):
            seeds.append(generator.spawn_candidate(self.default_prompt_arm, backend="flash"))
        return seeds

