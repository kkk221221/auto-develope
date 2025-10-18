"""Evaluation cascade scheduler implementing successive halving."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .evaluation import TierExecutor
from .models import EvaluationResult, ProgramCandidate, SchedulerConfig


@dataclass
class TierConfig:
    name: str
    retention: float
    timeout_s: int


class EvaluationScheduler:
    """Schedules candidate evaluations across tiered cascades."""

    def __init__(self, config: SchedulerConfig, tier_executor: TierExecutor) -> None:
        self.config = config
        self.tier_order = list(config.retention.keys())
        self.tier_configs: Dict[str, TierConfig] = {
            name: TierConfig(name=name, retention=ret, timeout_s=config.tier_budgets_s[name])
            for name, ret in config.retention.items()
        }
        self.tier_executor = tier_executor

    async def run_tier(self, candidate: ProgramCandidate, tier: str) -> EvaluationResult:
        return await self.tier_executor.run(candidate, tier)

