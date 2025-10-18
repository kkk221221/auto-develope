"""Simple in-memory cache manager for evaluation artifacts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .models import CacheEntry, ProgramCandidate


@dataclass
class CacheManager:
    """Maintains cache entries keyed by candidate signature and tier."""

    entries: Dict[str, CacheEntry] = field(default_factory=dict)

    def _make_key(self, candidate: ProgramCandidate, tier: str) -> str:
        return f"{candidate.id}:{tier}"

    def record(self, entry: CacheEntry) -> None:
        self.entries[f"{entry.cache_key}:{entry.tier}"] = entry

    def lookup(self, candidate: ProgramCandidate, tier: str) -> Optional[CacheEntry]:
        return self.entries.get(self._make_key(candidate, tier))

    def invalidate(self, candidate: ProgramCandidate) -> None:
        prefixes = [f"{candidate.id}:{tier}" for tier in ["L0", "L1", "L2", "L3"]]
        for key in list(self.entries):
            if any(key.startswith(prefix) for prefix in prefixes):
                self.entries.pop(key, None)

