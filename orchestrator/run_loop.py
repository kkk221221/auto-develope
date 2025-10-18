"""Async orchestration loop for the self-evolving system."""
from __future__ import annotations

import asyncio
import logging
import random
from collections import deque
from dataclasses import asdict, replace
from typing import Deque, Iterable, List, Optional

from pathlib import Path

from .behaviors import extract_behavior_features
from .caching import CacheManager
from .evaluation import ProblemEvaluator, TierExecutor, load_tier_specs
from .generation import ProgramGenerator
from .models import (
    ArchiveState,
    EvalStatus,
    EvaluationResult,
    Metrics,
    ProgramCandidate,
    SchedulerConfig,
    candidate_to_payload,
)
from .prompt_policy import PromptBandit
from .persistence import FilesystemPersistence, PersistenceGateway, RunState
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
        program_generator: ProgramGenerator,
        persistence: Optional[PersistenceGateway] = None,
    ) -> None:
        tier_specs = load_tier_specs(Path("configs/tiers.yaml"))
        evaluator = ProblemEvaluator("problems.sample_problem")
        tier_executor = TierExecutor(tier_specs=tier_specs, evaluator=evaluator)
        self.scheduler = EvaluationScheduler(config=scheduler_config, tier_executor=tier_executor)
        self.prompt_bandit = prompt_bandit
        self.selection_strategy = selection_strategy
        self.archive_manager = archive_manager
        self.cache_manager = cache_manager
        self.program_generator = program_generator
        self.pending_candidates: Deque[ProgramCandidate] = deque()
        self.persistence = persistence
        self._restored_from_state = False
        if self.persistence:
            state = self.persistence.load()
            if state:
                LOGGER.info("Restoring orchestrator state from persistence")
                self._restore_from_state(state)
                self._restored_from_state = True

    def queue_initial_population(self, seeds: Iterable[ProgramCandidate]) -> None:
        """Seed the orchestrator with an initial population."""

        if self._restored_from_state:
            LOGGER.info("Persisted state present; skipping initial seeding")
            return
        for candidate in seeds:
            LOGGER.info("Queueing seed candidate %s", candidate.id)
            self.pending_candidates.append(candidate)
        self._persist_state()

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
                    metrics=Metrics(**asdict(cached.metrics)),
                )
            else:
                LOGGER.debug("Scheduling candidate %s for tier %s", candidate.id, tier)
                result = await self.scheduler.run_tier(candidate, tier)
                if result.passed:
                    self.cache_manager.record(candidate, result)

            candidate = self._apply_result(candidate, result)
            if not result.passed:
                LOGGER.info(
                    "Candidate %s failed tier %s; halting cascade", candidate.id, tier
                )
                self.prompt_bandit.ingest_feedback(candidate.prompt_arm, [f"{tier}_fail"])
                break
        else:
            LOGGER.info("Candidate %s completed all tiers", candidate.id)

        self.archive_manager.update(candidate)
        self.selection_strategy.observe_candidate(candidate)
        reward = self._score_prompt_reward(candidate.metrics)
        self.prompt_bandit.update_reward(candidate.prompt_arm, reward)
        next_candidate = self.selection_strategy.select_next(self.program_generator, self.prompt_bandit)
        if next_candidate:
            LOGGER.info("Selected candidate %s for future evaluation", next_candidate.id)
            self.pending_candidates.append(next_candidate)
        self._persist_state()
        return candidate

    def _sample_and_generate(self) -> ProgramCandidate:
        arm_name, prompt = self.prompt_bandit.pick_prompt()
        candidate = self.program_generator.spawn_candidate(arm_name, prompt.backend)
        LOGGER.debug("Generating new candidate %s with arm %s", candidate.id, arm_name)
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

    def _score_prompt_reward(self, metrics: Metrics) -> float:
        accuracy_component = max(0.0, min(1.0, metrics.accuracy))
        runtime_norm = 1.0 / (1.0 + max(metrics.runtime_ms, 0.0) / 100.0)
        robustness_component = max(0.0, min(1.0, metrics.robustness))
        reward = 0.6 * accuracy_component + 0.3 * runtime_norm + 0.1 * robustness_component
        return max(0.0, min(1.0, reward))

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

    def _persist_state(self) -> None:
        if not self.persistence:
            return
        state = RunState(
            archive_snapshot=self.archive_manager.snapshot(),
            selection_snapshot=self.selection_strategy.snapshot(),
            prompt_snapshot=self.prompt_bandit.snapshot(),
            cache_snapshot=self.cache_manager.snapshot(),
            pending_candidates=[candidate_to_payload(candidate) for candidate in self.pending_candidates],
        )
        self.persistence.save(state)

    def _restore_from_state(self, state: RunState) -> None:
        self.archive_manager.restore(state.archive_snapshot)
        self.selection_strategy.restore(state.selection_snapshot, self.archive_manager)
        self.prompt_bandit.restore(state.prompt_snapshot)
        self.cache_manager.restore(state.cache_snapshot)
        self.pending_candidates = deque(state.iter_pending())


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
    archive_manager = ArchiveManager(ArchiveState())
    selection = SelectionStrategy(
        population_size=4,
        archive=archive_manager,
        default_prompt_arm=default_arm,
        novelty_alpha=scheduler_config.novelty_alpha,
        novelty_tau=scheduler_config.novelty_tau,
    )
    cache_manager = CacheManager()
    baseline_path = Path("solutions/workdir/sample_solution.py")
    generator = ProgramGenerator(baseline_path=baseline_path, output_root=Path(".artifacts/candidates"))
    persistence = FilesystemPersistence(Path(".artifacts/run_state.json"))

    orchestrator = EvolutionOrchestrator(
        scheduler_config=scheduler_config,
        prompt_bandit=prompt_bandit,
        selection_strategy=selection,
        archive_manager=archive_manager,
        cache_manager=cache_manager,
        program_generator=generator,
        persistence=persistence,
    )

    orchestrator.queue_initial_population(selection.bootstrap_population(generator))
    await orchestrator.run(max_steps=5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo_run())
