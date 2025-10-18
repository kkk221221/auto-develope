"""Content-addressed cache manager for evaluation artifacts."""
from __future__ import annotations

import hashlib
import json
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Protocol

from .models import CacheEntry, EvaluationResult, ProgramCandidate


class CacheBackend(Protocol):
    """Protocol describing cache backends."""

    def load(self, key: str) -> Optional[CacheEntry]: ...

    def store(self, key: str, entry: CacheEntry) -> None: ...

    def delete_with_prefix(self, prefix: str) -> None: ...

    def keys(self) -> Iterable[str]: ...


@dataclass
class CacheStats:
    """Tracks cache lookup hit/miss statistics."""

    lookups: int = 0
    hits: int = 0

    def record_hit(self) -> None:
        self.lookups += 1
        self.hits += 1

    def record_miss(self) -> None:
        self.lookups += 1

    @property
    def hit_rate(self) -> float:
        if self.lookups == 0:
            return 0.0
        return self.hits / self.lookups

    def snapshot(self) -> Dict[str, float]:
        return {"lookups": float(self.lookups), "hits": float(self.hits), "hit_rate": self.hit_rate}


@dataclass
class InMemoryCacheBackend:
    """Simple dictionary-backed cache backend."""

    _entries: Dict[str, CacheEntry] = field(default_factory=dict)

    def load(self, key: str) -> Optional[CacheEntry]:
        return self._entries.get(key)

    def store(self, key: str, entry: CacheEntry) -> None:
        self._entries[key] = entry

    def delete_with_prefix(self, prefix: str) -> None:
        for existing in list(self._entries):
            if existing.startswith(prefix):
                self._entries.pop(existing, None)

    def keys(self) -> Iterable[str]:
        return list(self._entries.keys())


@dataclass
class FilesystemCacheBackend:
    """Persists cache entries on disk for reuse across processes."""

    root: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe_key = urllib.parse.quote(key, safe="")
        return self.root / f"{safe_key}.json"

    def load(self, key: str) -> Optional[CacheEntry]:
        path = self._path(key)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("storage_key") != key:
            return None
        return CacheEntry.from_payload(payload["entry"])

    def store(self, key: str, entry: CacheEntry) -> None:
        payload = {"storage_key": key, "entry": entry.to_payload()}
        self._path(key).write_text(json.dumps(payload), encoding="utf-8")

    def delete_with_prefix(self, prefix: str) -> None:
        for path in list(self.root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:  # pragma: no cover - defensive
                continue
            storage_key = payload.get("storage_key", "")
            if storage_key.startswith(prefix):
                path.unlink(missing_ok=True)

    def keys(self) -> Iterable[str]:
        keys: List[str] = []
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:  # pragma: no cover - defensive
                continue
            storage_key = payload.get("storage_key")
            if storage_key:
                keys.append(storage_key)
        return keys


@dataclass
class CacheManager:
    """Maintains cache entries keyed by candidate signature and tier."""

    environment_fingerprint: str = "local"
    backend: CacheBackend | None = None
    stats: CacheStats = field(default_factory=CacheStats)

    def __post_init__(self) -> None:
        if self.backend is None:
            self.backend = InMemoryCacheBackend()

    def _signature(self, candidate: ProgramCandidate) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.environment_fingerprint.encode("utf-8"))
        hasher.update(candidate.problem_id.encode("utf-8"))
        hasher.update(candidate.llm_backend.encode("utf-8"))
        payload = json.dumps(candidate.patch_payload, sort_keys=True).encode("utf-8")
        hasher.update(payload)
        source = Path(candidate.source_path)
        if source.exists():
            hasher.update(source.read_bytes())
        return hasher.hexdigest()

    def _make_key(self, candidate: ProgramCandidate, tier: str) -> str:
        return f"{self._signature(candidate)}:{tier}:{self.environment_fingerprint}"

    def record(self, candidate: ProgramCandidate, result: EvaluationResult) -> None:
        signature = self._signature(candidate)
        entry = CacheEntry(cache_key=signature, tier=result.tier, metrics=result.metrics)
        key = self._make_key(candidate, result.tier)
        assert self.backend is not None
        self.backend.store(key, entry)

    def lookup(self, candidate: ProgramCandidate, tier: str) -> Optional[CacheEntry]:
        key = self._make_key(candidate, tier)
        assert self.backend is not None
        entry = self.backend.load(key)
        if entry:
            self.stats.record_hit()
        else:
            self.stats.record_miss()
        return entry

    def invalidate(self, candidate: ProgramCandidate) -> None:
        signature = self._signature(candidate)
        assert self.backend is not None
        prefix = f"{signature}:"
        self.backend.delete_with_prefix(prefix)

    def report(self) -> Dict[str, float]:
        assert self.backend is not None
        payload = self.stats.snapshot()
        payload["entries"] = float(len(list(self.backend.keys())))
        return payload

