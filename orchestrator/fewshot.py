"""Utilities for managing few-shot prompt examples per problem domain."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence


FEWSHOT_ROOT = Path(".artifacts/fewshot")
MAX_FEWSHOT_PER_PROBLEM = 200


@dataclass
class FewShotExample:
    """Represents a stored few-shot example for prompt augmentation."""

    search: str
    replace: str
    tags: Sequence[str]
    intent: str
    success: bool

    def to_payload(self) -> Mapping[str, object]:
        return {
            "search": self.search,
            "replace": self.replace,
            "tags": list(self.tags),
            "intent": self.intent,
            "success": self.success,
        }


def _fewshot_path(problem_id: str) -> Path:
    FEWSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    return FEWSHOT_ROOT / f"{problem_id}.jsonl"


def append_example(problem_id: str, example: FewShotExample) -> None:
    """Appends a few-shot example for the given problem id."""

    path = _fewshot_path(problem_id)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(example.to_payload(), ensure_ascii=False) + "\n")
    _prune_file(path)


def _tokenise(text: str) -> set[str]:
    return {token for token in text.replace("\n", " ").split() if token}


def retrieve_examples(
    problem_id: str,
    current_block: str,
    failure_tags: Iterable[str],
    *,
    max_examples: int = 2,
) -> List[Mapping[str, object]]:
    """Retrieves at most ``max_examples`` few-shot samples ranked by similarity."""

    path = _fewshot_path(problem_id)
    if not path.exists():
        return []
    current_tokens = _tokenise(current_block)
    requested_tags = {tag for tag in failure_tags if tag}
    scored: List[tuple[float, Mapping[str, object]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            search = str(payload.get("search", ""))
            search_tokens = _tokenise(search)
            if not search_tokens:
                continue
            intersection = len(current_tokens & search_tokens)
            union = len(current_tokens | search_tokens) or 1
            jaccard = intersection / union
            example_tags = {str(tag) for tag in payload.get("tags", []) if tag}
            tag_overlap = len(example_tags & requested_tags)
            score = jaccard + 0.15 * tag_overlap
            # Slight boost for successful examples
            if bool(payload.get("success", False)):
                score += 0.05
            scored.append((score, payload))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [payload for _, payload in scored[: max_examples]]


def _prune_file(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:  # pragma: no cover - defensive
        return
    if len(lines) <= MAX_FEWSHOT_PER_PROBLEM:
        return
    retained = lines[-MAX_FEWSHOT_PER_PROBLEM :]
    path.write_text("\n".join(retained) + "\n", encoding="utf-8")
