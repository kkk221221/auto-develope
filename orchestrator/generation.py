"""Candidate generation utilities for the self-evolving system."""
from __future__ import annotations

import logging
import re
import textwrap
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple, cast

from .agents import AgentGeneration, GeminiAgentAdapter, GeminiAgentError
from .ast_crossover import perform_ast_crossover
from .models import BehaviorFeatures, ProgramCandidate
from .prompt_policy import PromptMaterialization

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


def _baseline_variant() -> str:
    return """
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    pairs = list(pairs)
    if not pairs:
        return 0.0
    return sum(a + b for a, b in pairs) / len(pairs)
"""


def _perf_variant() -> str:
    return """
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    iterator = tuple(pairs)
    if not iterator:
        return 0.0
    total = sum(sum(pair) for pair in iterator)
    return total / len(iterator)
"""


def _robust_variant() -> str:
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
    total = sum(a + b for a, b in cleaned)
    return total / len(cleaned)
"""


def _simplicity_variant() -> str:
    return """
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    iterator = tuple(pairs)
    length = len(iterator)
    if length == 0:
        return 0.0
    return (sum(pair[0] for pair in iterator) + sum(pair[1] for pair in iterator)) / length
"""


def _exploration_variant() -> str:
    return """
def solve(pairs: Iterable[Tuple[int, int]]) -> float:
    iterator = list(pairs)
    if not iterator:
        return 0.0
    weighted = [0.6 * a + 0.4 * b for a, b in iterator]
    baseline = sum(a + b for a, b in iterator) / len(iterator)
    return (baseline + sum(weighted) / len(weighted)) / 2.0
"""


MUTATION_SNIPPETS: Dict[str, Callable[[], str]] = {
    "perf_first": _perf_variant,
    "robust_first": _robust_variant,
    "simplicity_first": _simplicity_variant,
    "exploration": _exploration_variant,
}


@dataclass
class ProgramGenerator:
    """Applies mutations or agent-supplied patches to seed candidates."""

    baseline_path: Path
    output_root: Path
    agent: Optional[GeminiAgentAdapter] = None

    def __post_init__(self) -> None:
        self.baseline_source = self.baseline_path.read_text(encoding="utf-8")
        self.output_root.mkdir(parents=True, exist_ok=True)

    def spawn_candidate(
        self,
        arm: str,
        prompt: PromptMaterialization,
        *,
        parents: Tuple[str, ...] | None = None,
        generation: int = 0,
    ) -> ProgramCandidate:
        arm_key = arm.split(".", 1)[-1]
        snippet, metadata = self._materialise_snippet(arm_key, prompt)
        mutated_source = _replace_evolve_block(self.baseline_source, snippet)
        candidate_id = uuid.uuid4().hex
        candidate_dir = self.output_root / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=False)
        candidate_path = candidate_dir / self.baseline_path.name
        candidate_path.write_text(mutated_source, encoding="utf-8")
        patch_payload: Dict[str, object] = {
            "diff_type": "sr",
            "payload": textwrap.dedent(snippet).strip(),
            "metadata": metadata,
        }
        parent_ids = tuple(parents or ())
        return ProgramCandidate(
            id=candidate_id,
            parents=parent_ids,
            generation=generation,
            prompt_arm=arm,
            llm_backend=prompt.backend,
            patch_payload=patch_payload,
            source_path=str(candidate_path),
        )

    def spawn_crossover_candidate(
        self,
        parent_a: ProgramCandidate,
        parent_b: ProgramCandidate,
    ) -> ProgramCandidate:
        """Produces a child candidate via AST-guided crossover."""

        result = perform_ast_crossover(
            parent_a,
            parent_b,
            base_source=self.baseline_source,
        )
        candidate_id = uuid.uuid4().hex
        candidate_dir = self.output_root / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=False)
        candidate_path = candidate_dir / self.baseline_path.name
        candidate_path.write_text(result.merged_source, encoding="utf-8")

        return ProgramCandidate(
            id=candidate_id,
            parents=(parent_a.id, parent_b.id),
            generation=max(parent_a.generation, parent_b.generation) + 1,
            prompt_arm="crossover.ast_mix",
            llm_backend=parent_a.llm_backend,
            patch_payload=result.patch_payload,
            source_path=str(candidate_path),
            behavior=result.behavior or BehaviorFeatures(),
        )

    def _materialise_snippet(
        self, arm_key: str, prompt: PromptMaterialization
    ) -> Tuple[str, Dict[str, object]]:
        """Obtain a snippet from the CLI adapter or the built-in templates."""

        if self.agent:
            try:
                agent_result: AgentGeneration = self.agent.generate(prompt)
                snippet = agent_result.snippet
                metadata: Dict[str, object] = cast(
                    Dict[str, object],
                    {
                        "arm": arm_key,
                        "strategy": "gemini_cli",
                        "telemetry": list(agent_result.telemetry_tags),
                        **dict(agent_result.metadata),
                    },
                )
                return snippet, metadata
            except GeminiAgentError as error:
                LOGGER.warning("Gemini CLI fallback: %s", error)
        snippet_factory = MUTATION_SNIPPETS.get(arm_key, _baseline_variant)
        snippet = snippet_factory()
        metadata = cast(
            Dict[str, object],
            {
                "arm": arm_key,
                "strategy": "template_mutation",
                "prompt_generation": prompt.generation,
            },
        )
        return snippet, metadata

