"""Persistence helpers for orchestrator state snapshots."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol, Sequence

from .models import ProgramCandidate, candidate_from_payload


@dataclass
class RunState:
    """Serialisable snapshot capturing orchestrator runtime state."""

    archive_snapshot: Mapping[str, Any]
    selection_snapshot: Mapping[str, Any]
    prompt_snapshot: Mapping[str, Any]
    cache_snapshot: Mapping[str, Any]
    pending_candidates: Sequence[Mapping[str, Any]]
    version: int = 1
    saved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "saved_at": self.saved_at.isoformat(),
            "archive": dict(self.archive_snapshot),
            "selection": dict(self.selection_snapshot),
            "prompt": dict(self.prompt_snapshot),
            "cache": dict(self.cache_snapshot),
            "pending_candidates": [dict(candidate) for candidate in self.pending_candidates],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RunState":
        version = int(payload.get("version", 1))
        saved_at_raw = payload.get("saved_at")
        saved_at = (
            datetime.fromisoformat(str(saved_at_raw))
            if saved_at_raw
            else datetime.now(timezone.utc)
        )
        archive = payload.get("archive", {})
        selection = payload.get("selection", {})
        prompt = payload.get("prompt", {})
        cache = payload.get("cache", {})
        pending_raw = payload.get("pending_candidates", [])
        pending_candidates: Sequence[Mapping[str, Any]]
        if isinstance(pending_raw, list):
            pending_candidates = [
                candidate if isinstance(candidate, Mapping) else {}
                for candidate in pending_raw
            ]
        else:
            pending_candidates = []
        return cls(
            archive_snapshot=archive if isinstance(archive, Mapping) else {},
            selection_snapshot=selection if isinstance(selection, Mapping) else {},
            prompt_snapshot=prompt if isinstance(prompt, Mapping) else {},
            cache_snapshot=cache if isinstance(cache, Mapping) else {},
            pending_candidates=pending_candidates,
            version=version,
            saved_at=saved_at,
        )

    def iter_pending(self) -> Iterable[ProgramCandidate]:
        for payload in self.pending_candidates:
            if isinstance(payload, Mapping):
                yield candidate_from_payload(payload)


class PersistenceGateway(Protocol):
    """Persistence backend abstraction for orchestrator checkpoints."""

    def load(self) -> Optional[RunState]: ...

    def save(self, state: RunState) -> None: ...


@dataclass
class FilesystemPersistence:
    """JSON-based persistence backend writing to disk."""

    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Optional[RunState]:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):  # pragma: no cover - defensive
            return None
        return RunState.from_payload(payload)

    def save(self, state: RunState) -> None:
        payload = state.to_payload()
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.path)

    def clear(self) -> None:
        """Removes any persisted checkpoint."""

        self.path.unlink(missing_ok=True)
