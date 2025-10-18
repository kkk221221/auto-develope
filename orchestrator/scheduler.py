"""Evaluation cascade scheduler implementing successive halving."""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Dict, Iterable, List

from .models import EvaluationResult, Metrics, ProgramCandidate, SchedulerConfig


@dataclass
class TierConfig:
    name: str
    retention: float
    timeout_s: int


class EvaluationScheduler:
    """Schedules candidate evaluations across tiered cascades."""

    def __init__(self, config: SchedulerConfig) -> None:
        self.config = config
        self.tier_order = list(config.retention.keys())
        self.tier_configs: Dict[str, TierConfig] = {
            name: TierConfig(name=name, retention=ret, timeout_s=config.tier_budgets_s[name])
            for name, ret in config.retention.items()
        }

    async def run_tier(self, candidate: ProgramCandidate, tier: str) -> EvaluationResult:
        await asyncio.sleep(0)
        metrics = Metrics(
            accuracy=random.uniform(0, 1),
            runtime_ms=random.uniform(1, 1000),
            memory_peak_mb=random.uniform(10, 256),
            loc=random.randint(10, 500),
            cyclomatic=random.uniform(1, 15),
            robustness=random.uniform(0, 1),
            llm_style=random.uniform(0, 1),
        )
        passed = metrics.accuracy > 0.3
        return EvaluationResult(
            candidate_id=candidate.id,
            tier=tier,
            passed=passed,
            metrics=metrics,
        )

