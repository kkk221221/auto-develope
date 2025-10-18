"""Candidate selection and archive maintenance utilities."""
from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from typing import List, Optional

from .models import ArchiveState, ProgramCandidate


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
        if len(self.buffer) > self.population_size:
            self.buffer.pop(0)

    def select_next(self) -> Optional[ProgramCandidate]:
        if not self.buffer:
            return None
        return random.choice(self.buffer)

    def bootstrap_population(self) -> List[ProgramCandidate]:
        seeds: List[ProgramCandidate] = []
        for _ in range(self.population_size):
            seed = ProgramCandidate(
                id=str(random.randint(0, 999999)),
                parents=tuple(),
                generation=0,
                prompt_arm=self.default_prompt_arm,
                llm_backend="flash",
                patch_payload={},
            )
            seeds.append(seed)
        return seeds

