"""Core data models for the self-evolving system."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, cast


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

