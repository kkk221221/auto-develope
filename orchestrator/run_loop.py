"""Async orchestration loop for the self-evolving system."""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from collections import deque
from dataclasses import asdict, replace
from typing import Deque, Iterable, List, Optional

from .behaviors import extract_behavior_features
from .caching import CacheManager
from .models import ArchiveState, EvalStatus, EvaluationResult, ProgramCandidate, SchedulerConfig
from .prompt_policy import PromptBandit
from .scheduler import EvaluationScheduler
from .selection import ArchiveManager, SelectionStrategy

LOGGER = logging.getLogger(__name__)


class EvolutionOrchestrator:
    """Coordinates sampling, generation, evaluation, and selection."""

    def __init__(
        self,
        scheduler_config: SchedulerConfig,
        prompt_bandit: PromptBandit,
        selection_strategy: SelectionStrategy,
        archive_manager: ArchiveManager,
        cache_manager: CacheManager,
    ) -> None:
        self.scheduler = EvaluationScheduler(config=scheduler_config)
        self.prompt_bandit = prompt_bandit
        self.selection_strategy = selection_strategy
        self.archive_manager = archive_manager
        self.cache_manager = cache_manager
        self.pending_candidates: Deque[ProgramCandidate] = deque()

    def queue_initial_population(self, seeds: Iterable[ProgramCandidate]) -> None:
        """Seed the orchestrator with an initial population."""

        for candidate in seeds:
            LOGGER.info("Queueing seed candidate %s", candidate.id)
            self.pending_candidates.append(candidate)

    async def step(self) -> Optional[ProgramCandidate]:
        """Executes a single orchestration step."""

        if not self.pending_candidates:
            LOGGER.debug("No candidates pending evaluation; sampling new ones.")
            new_candidate = self._sample_and_generate()
            self.pending_candidates.append(new_candidate)

        candidate = self.pending_candidates.popleft()
        LOGGER.debug("Dequeued candidate %s for scheduling", candidate.id)

        for tier in self.scheduler.tier_order:
            cached = self.cache_manager.lookup(candidate, tier)
            if cached:
                LOGGER.info("Cache hit for candidate %s tier %s", candidate.id, tier)
                result = EvaluationResult(
                    candidate_id=candidate.id,
                    tier=tier,
                    passed=True,
                    metrics=cached.metrics,
                )
            else:
                LOGGER.debug("Scheduling candidate %s for tier %s", candidate.id, tier)
                result = await self.scheduler.run_tier(candidate, tier)

            candidate = self._apply_result(candidate, result)
            if not result.passed:
                LOGGER.info(
                    "Candidate %s failed tier %s; halting cascade", candidate.id, tier
                )
                break
        else:
            LOGGER.info("Candidate %s completed all tiers", candidate.id)

        self.archive_manager.update(candidate)
        self.selection_strategy.observe_candidate(candidate)
        self.prompt_bandit.update_reward(candidate.prompt_arm, candidate.metrics.accuracy)
        next_candidate = self.selection_strategy.select_next()
        if next_candidate:
            LOGGER.info("Selected candidate %s for future evaluation", next_candidate.id)
            self.pending_candidates.append(next_candidate)
        return candidate

    def _sample_and_generate(self) -> ProgramCandidate:
        arm_name, prompt = self.prompt_bandit.pick_prompt()
        candidate_id = str(uuid.uuid4())
        LOGGER.debug("Generating new candidate %s with arm %s", candidate_id, arm_name)
        # Placeholder for actual LLM generation; we simulate metrics.
        candidate = ProgramCandidate(
            id=candidate_id,
            parents=tuple(),
            generation=0,
            prompt_arm=arm_name,
            llm_backend=prompt.backend,
            patch_payload={"diff_type": "sr", "payload": ""},
        )
        return candidate

    def _apply_result(
        self, candidate: ProgramCandidate, result: EvaluationResult
    ) -> ProgramCandidate:
        LOGGER.debug(
            "Recording result for candidate %s tier %s", candidate.id, result.tier
        )
        updated_metrics = replace(candidate.metrics, **asdict(result.metrics))
        updated_behavior = result.behavior or extract_behavior_features(result)
        updated_passes = [*candidate.eval_passes, result.tier] if result.passed else candidate.eval_passes
        status = EvalStatus.SUCCEEDED if result.passed else EvalStatus.FAILED
        updated_candidate = replace(
            candidate,
            metrics=updated_metrics,
            behavior=updated_behavior,
            eval_passes=updated_passes,
            status=status,
            evaluated_at=result.completed_at,
        )
        return updated_candidate

    async def run(self, max_steps: Optional[int] = None) -> List[ProgramCandidate]:
        """Continuously executes orchestration steps until completion."""

        completed: List[ProgramCandidate] = []
        steps = 0
        while max_steps is None or steps < max_steps:
            result = await self.step()
            if result:
                completed.append(result)
            steps += 1
        return completed


async def demo_run() -> None:
    """Demonstrates the orchestrator with mocked dependencies."""

    random.seed(0)
    scheduler_config = SchedulerConfig(
        population_size=4,
        retention={"L0": 0.6, "L1": 0.4, "L2": 0.2},
        tier_budgets_s={"L0": 10, "L1": 60, "L2": 180},
        novelty_alpha=1.0,
        novelty_tau=8,
    )
    prompt_bandit = PromptBandit.from_directory("agents/prompts")
    default_arm = next(iter(prompt_bandit.arms))
    selection = SelectionStrategy(population_size=4, default_prompt_arm=default_arm)
    archive_manager = ArchiveManager(ArchiveState())
    cache_manager = CacheManager()

    orchestrator = EvolutionOrchestrator(
        scheduler_config=scheduler_config,
        prompt_bandit=prompt_bandit,
        selection_strategy=selection,
        archive_manager=archive_manager,
        cache_manager=cache_manager,
    )

    orchestrator.queue_initial_population(selection.bootstrap_population())
    await orchestrator.run(max_steps=5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo_run())
