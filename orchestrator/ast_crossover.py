"""Placeholder AST crossover utilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .models import ProgramCandidate


@dataclass
class CrossoverPlan:
    parents: Tuple[str, str]
    strategy: str


def perform_ast_crossover(parent_a: ProgramCandidate, parent_b: ProgramCandidate) -> ProgramCandidate:
    """Produces a placeholder child candidate by combining parent identifiers."""

    child_id = f"{parent_a.id[:4]}-{parent_b.id[:4]}"
    return ProgramCandidate(
        id=child_id,
        parents=(parent_a.id, parent_b.id),
        generation=max(parent_a.generation, parent_b.generation) + 1,
        prompt_arm="crossover",
        llm_backend=parent_a.llm_backend,
        patch_payload={"diff_type": "unified", "payload": ""},
    )

