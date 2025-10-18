"""Core data models for the self-evolving system."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


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
    patch_payload: Dict[str, str]
    metrics: Metrics = field(default_factory=Metrics)
    behavior: BehaviorFeatures = field(default_factory=BehaviorFeatures)
    eval_passes: List[str] = field(default_factory=list)
    status: EvalStatus = EvalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    evaluated_at: Optional[datetime] = None
    novelty_score: float = 0.0


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
    completed_at: datetime = field(default_factory=datetime.utcnow)


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
    created_at: datetime = field(default_factory=datetime.utcnow)

