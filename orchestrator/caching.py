"""Content-addressed cache manager for evaluation artifacts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .models import CacheEntry, EvaluationResult, ProgramCandidate


@dataclass
class CacheManager:
    """Maintains cache entries keyed by candidate signature and tier."""

    entries: Dict[str, CacheEntry] = field(default_factory=dict)

    def _signature(self, candidate: ProgramCandidate) -> str:
        hasher = hashlib.sha256()
        hasher.update(candidate.problem_id.encode("utf-8"))
        hasher.update(candidate.llm_backend.encode("utf-8"))
        payload = json.dumps(candidate.patch_payload, sort_keys=True).encode("utf-8")
        hasher.update(payload)
        source = Path(candidate.source_path)
        if source.exists():
            hasher.update(source.read_bytes())
        return hasher.hexdigest()

    def _make_key(self, candidate: ProgramCandidate, tier: str) -> str:
        return f"{self._signature(candidate)}:{tier}"

    def record(self, candidate: ProgramCandidate, result: EvaluationResult) -> None:
        cache_key = self._signature(candidate)
        entry = CacheEntry(cache_key=cache_key, tier=result.tier, metrics=result.metrics)
        self.entries[f"{cache_key}:{result.tier}"] = entry

    def lookup(self, candidate: ProgramCandidate, tier: str) -> Optional[CacheEntry]:
        return self.entries.get(self._make_key(candidate, tier))

    def invalidate(self, candidate: ProgramCandidate) -> None:
        signature = self._signature(candidate)
        prefixes = [f"{signature}:{tier}" for tier in ["L0", "L1", "L2", "L3"]]
        for key in list(self.entries):
            if any(key.startswith(prefix) for prefix in prefixes):
                self.entries.pop(key, None)

