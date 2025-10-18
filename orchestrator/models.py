"""Core data models for the self-evolving system."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, cast


class EvalStatus(str, Enum):
    """Status of a program candidate within the evaluation cascade."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True)
class Metrics:
    """Evaluation metrics tracked for each program candidate."""

    accuracy: float = 0.0
    runtime_ms: float = 0.0
    memory_peak_mb: float = 0.0
    loc: int = 0
    cyclomatic: float = 0.0
    robustness: float = 0.0
    llm_style: float = 0.0


@dataclass(slots=True)
class BehaviorFeatures:
    """Behavioral descriptors used for novelty and MAP-Elites."""

    coverage_bits: Sequence[int] = ()
    hotspots: Dict[str, float] = field(default_factory=dict)
    output_signature: str = ""


@dataclass(slots=True)
class ProgramCandidate:
    """Represents a candidate program variant undergoing evolution."""

    id: str
    parents: Tuple[str, ...]
    generation: int
    prompt_arm: str
    llm_backend: str
    patch_payload: Dict[str, object]
    problem_id: str = "sample_problem"
    source_path: str = ""
    metrics: Metrics = field(default_factory=Metrics)
    behavior: BehaviorFeatures = field(default_factory=BehaviorFeatures)
    eval_passes: List[str] = field(default_factory=list)
    status: EvalStatus = EvalStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    evaluated_at: Optional[datetime] = None
    novelty_score: float = 0.0
    pareto_rank: int = 0
    crowding_distance: float = 0.0


@dataclass(slots=True)
class PromptArm:
    """Metadata maintained for a prompt template arm."""

    name: str
    template_path: str
    successes: float = 1.0
    failures: float = 1.0
    recent_reward: float = 0.0
    horizon_generations: int = 3


@dataclass(slots=True)
class EvaluationResult:
    """Normalized result returned by an evaluation tier."""

    candidate_id: str
    tier: str
    passed: bool
    metrics: Metrics
    behavior: Optional[BehaviorFeatures] = None
    logs_path: Optional[str] = None
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class SchedulerConfig:
    """Configuration for the evaluation cascade scheduler."""

    population_size: int
    retention: Dict[str, float]
    tier_budgets_s: Dict[str, int]
    novelty_alpha: float
    novelty_tau: int


@dataclass(slots=True)
class ArchiveState:
    """Quality-diversity archive state."""

    pareto_front: List[str] = field(default_factory=list)
    map_elites_cells: Dict[Tuple[int, int], str] = field(default_factory=dict)


@dataclass(slots=True)
class CacheEntry:
    """Represents a reusable evaluation artifact."""

    cache_key: str
    tier: str
    metrics: Metrics
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> Dict[str, object]:
        """Serialises the cache entry to a JSON-friendly payload."""

        return {
            "cache_key": self.cache_key,
            "tier": self.tier,
            "metrics": {
                "accuracy": self.metrics.accuracy,
                "runtime_ms": self.metrics.runtime_ms,
                "memory_peak_mb": self.metrics.memory_peak_mb,
                "loc": self.metrics.loc,
                "cyclomatic": self.metrics.cyclomatic,
                "robustness": self.metrics.robustness,
                "llm_style": self.metrics.llm_style,
            },
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "CacheEntry":
        """Rehydrates a cache entry from a stored payload."""

        def _as_float(value: object, default: float = 0.0) -> float:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return default
            return default

        def _as_int(value: object, default: int = 0) -> int:
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    return default
            return default

        metrics_payload = cast(Mapping[str, object], payload.get("metrics", {}))
        metrics = Metrics(
            accuracy=_as_float(metrics_payload.get("accuracy", 0.0)),
            runtime_ms=_as_float(metrics_payload.get("runtime_ms", 0.0)),
            memory_peak_mb=_as_float(metrics_payload.get("memory_peak_mb", 0.0)),
            loc=_as_int(metrics_payload.get("loc", 0)),
            cyclomatic=_as_float(metrics_payload.get("cyclomatic", 0.0)),
            robustness=_as_float(metrics_payload.get("robustness", 0.0)),
            llm_style=_as_float(metrics_payload.get("llm_style", 0.0)),
        )
        created_at_raw = payload.get("created_at", "")
        created_at_str = str(created_at_raw) if created_at_raw is not None else ""
        created_at = (
            datetime.fromisoformat(created_at_str)
            if created_at_str
            else datetime.now(timezone.utc)
        )
        return cls(
            cache_key=str(payload.get("cache_key", "")),
            tier=str(payload.get("tier", "")),
            metrics=metrics,
            created_at=created_at,
        )


def metrics_to_payload(metrics: Metrics) -> Dict[str, Any]:
    """Serialises a Metrics instance into JSON-friendly primitives."""

    return {
        "accuracy": metrics.accuracy,
        "runtime_ms": metrics.runtime_ms,
        "memory_peak_mb": metrics.memory_peak_mb,
        "loc": metrics.loc,
        "cyclomatic": metrics.cyclomatic,
        "robustness": metrics.robustness,
        "llm_style": metrics.llm_style,
    }


def metrics_from_payload(payload: Mapping[str, Any]) -> Metrics:
    """Rehydrates Metrics from primitive values."""

    return Metrics(
        accuracy=float(payload.get("accuracy", 0.0)),
        runtime_ms=float(payload.get("runtime_ms", 0.0)),
        memory_peak_mb=float(payload.get("memory_peak_mb", 0.0)),
        loc=int(payload.get("loc", 0)),
        cyclomatic=float(payload.get("cyclomatic", 0.0)),
        robustness=float(payload.get("robustness", 0.0)),
        llm_style=float(payload.get("llm_style", 0.0)),
    )


def behavior_to_payload(behavior: BehaviorFeatures) -> Dict[str, Any]:
    """Converts behaviour descriptors to a portable payload."""

    return {
        "coverage_bits": list(behavior.coverage_bits),
        "hotspots": dict(behavior.hotspots),
        "output_signature": behavior.output_signature,
    }


def behavior_from_payload(payload: Optional[Mapping[str, Any]]) -> BehaviorFeatures:
    """Reconstructs behaviour descriptors from a payload."""

    if payload is None:
        return BehaviorFeatures()
    coverage = payload.get("coverage_bits", [])
    hotspots_raw = payload.get("hotspots", {})
    if isinstance(coverage, (list, tuple)):
        coverage_bits = tuple(int(item) for item in coverage)
    else:
        coverage_bits = ()
    hotspots: Dict[str, float] = {}
    if isinstance(hotspots_raw, Mapping):
        for key, value in hotspots_raw.items():
            try:
                hotspots[str(key)] = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):  # pragma: no cover - defensive
                continue
    return BehaviorFeatures(
        coverage_bits=coverage_bits,
        hotspots=hotspots,
        output_signature=str(payload.get("output_signature", "")),
    )


def candidate_to_payload(candidate: ProgramCandidate) -> Dict[str, Any]:
    """Serialises a ProgramCandidate (including metrics and behaviour)."""

    payload: Dict[str, Any] = {
        "id": candidate.id,
        "parents": list(candidate.parents),
        "generation": candidate.generation,
        "prompt_arm": candidate.prompt_arm,
        "llm_backend": candidate.llm_backend,
        "patch_payload": candidate.patch_payload,
        "problem_id": candidate.problem_id,
        "source_path": candidate.source_path,
        "metrics": metrics_to_payload(candidate.metrics),
        "behavior": behavior_to_payload(candidate.behavior),
        "eval_passes": list(candidate.eval_passes),
        "status": candidate.status.value,
        "created_at": candidate.created_at.isoformat(),
        "evaluated_at": candidate.evaluated_at.isoformat() if candidate.evaluated_at else None,
        "novelty_score": candidate.novelty_score,
        "pareto_rank": candidate.pareto_rank,
        "crowding_distance": candidate.crowding_distance,
    }
    return payload


def candidate_from_payload(payload: Mapping[str, Any]) -> ProgramCandidate:
    """Rehydrates a ProgramCandidate from a serialised payload."""

    created_raw = payload.get("created_at")
    created_at = (
        datetime.fromisoformat(str(created_raw))
        if created_raw
        else datetime.now(timezone.utc)
    )
    evaluated_raw = payload.get("evaluated_at")
    evaluated_at = (
        datetime.fromisoformat(str(evaluated_raw))
        if evaluated_raw
        else None
    )
    status_raw = str(payload.get("status", EvalStatus.PENDING.value))
    try:
        status = EvalStatus(status_raw)
    except ValueError:  # pragma: no cover - defensive
        status = EvalStatus.PENDING
    candidate = ProgramCandidate(
        id=str(payload.get("id", "")),
        parents=tuple(str(item) for item in payload.get("parents", [])),
        generation=int(payload.get("generation", 0)),
        prompt_arm=str(payload.get("prompt_arm", "")),
        llm_backend=str(payload.get("llm_backend", "")),
        patch_payload=cast(Dict[str, object], payload.get("patch_payload", {})),
        problem_id=str(payload.get("problem_id", "sample_problem")),
        source_path=str(payload.get("source_path", "")),
        metrics=metrics_from_payload(cast(Mapping[str, Any], payload.get("metrics", {}))),
        behavior=behavior_from_payload(cast(Mapping[str, Any], payload.get("behavior"))),
        eval_passes=list(payload.get("eval_passes", [])),
        status=status,
        created_at=created_at,
        evaluated_at=evaluated_at,
        novelty_score=float(payload.get("novelty_score", 0.0)),
        pareto_rank=int(payload.get("pareto_rank", 0)),
        crowding_distance=float(payload.get("crowding_distance", 0.0)),
    )
    return candidate

