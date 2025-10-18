"""Async orchestration loop for the self-evolving system."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from collections import deque
from dataclasses import asdict, replace
from pathlib import Path
from typing import Deque, Iterable, List, Mapping, Optional

from .agents import LLMApiAgentAdapter
from .behaviors import extract_behavior_features
from .caching import CacheManager
from .dashboard import render_map_elites_dashboard
from .evaluation import ProblemEvaluator, TierExecutor, load_tier_specs
from .generation import ProgramGenerator
from .git_lineage import GitLineageTracker
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
from .problem_specs import load_problem_specs
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
        package_map = {
            problem_id: spec.package for problem_id, spec in program_generator.problem_specs.items()
        }
        evaluator = ProblemEvaluator(package_map)
        tier_executor = TierExecutor(tier_specs=tier_specs, evaluator=evaluator)
        self.scheduler = EvaluationScheduler(config=scheduler_config, tier_executor=tier_executor)
        self.prompt_bandit = prompt_bandit
        self.selection_strategy = selection_strategy
        self.archive_manager = archive_manager
        self.cache_manager = cache_manager
        self.program_generator = program_generator
        self.problem_ids = list(program_generator.problem_specs.keys())
        self._problem_cycle: Deque[str] = deque(self.problem_ids)
        self.pending_candidates: Deque[ProgramCandidate] = deque()
        self.persistence = persistence
        self.archive_export_path = Path(".artifacts/map_elites.json")
        self.archive_export_path.parent.mkdir(parents=True, exist_ok=True)
        self.dashboard_path = Path(".artifacts/dashboard.html")
        self.prompt_telemetry_path = Path(".artifacts/prompt_telemetry.json")
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
                failure_context = self._build_failure_context(candidate, result)
                self._queue_repair_candidate(candidate, failure_context)
                break
        else:
            LOGGER.info("Candidate %s completed all tiers", candidate.id)

        self.archive_manager.update(candidate)
        self._export_archive()
        self.selection_strategy.observe_candidate(candidate)
        reward = self._score_prompt_reward(candidate.metrics)
        self.prompt_bandit.update_reward(candidate.prompt_arm, reward)
        LOGGER.info(
            "Arm %s produced candidate %s with reward %.3f and metrics %s",
            candidate.prompt_arm,
            candidate.id,
            reward,
            candidate.metrics,
        )
        if self.prompt_telemetry_path:
            try:
                self.prompt_bandit.export_telemetry(self.prompt_telemetry_path)
            except OSError as error:  # pragma: no cover - best effort only
                LOGGER.debug("Failed to export prompt telemetry: %s", error)
        next_candidate = self.selection_strategy.select_next(self.program_generator, self.prompt_bandit)
        if next_candidate:
            LOGGER.info("Selected candidate %s for future evaluation", next_candidate.id)
            self.pending_candidates.append(next_candidate)
        self._persist_state()
        return candidate

    def _sample_and_generate(self) -> ProgramCandidate:
        problem_id = "knapsack"
        arm_name, prompt = self.prompt_bandit.pick_prompt(
            intent="mutate", problem_id=problem_id, prefer_island="robustness"
        )
        candidate = self.program_generator.spawn_candidate(arm_name, prompt, problem_id=problem_id)
        LOGGER.debug(
            "Generating new candidate %s with arm %s for problem %s",
            candidate.id,
            arm_name,
            problem_id,
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

    def _next_problem_id(self) -> str:
        if not self._problem_cycle:
            raise RuntimeError("No problem ids configured for orchestrator")
        problem_id = self._problem_cycle[0]
        self._problem_cycle.rotate(-1)
        return problem_id

    def _queue_repair_candidate(
        self, candidate: ProgramCandidate, failure_context: List[str]
    ) -> None:
        try:
            arm, prompt = self.prompt_bandit.pick_prompt(
                intent="repair", problem_id=candidate.problem_id
            )
        except ValueError:
            LOGGER.debug("No repair prompt available for problem %s", candidate.problem_id)
            return
        prompt_with_context = prompt.with_context(failure_context)
        repair_candidate = self.program_generator.spawn_candidate(
            arm,
            prompt_with_context,
            problem_id=candidate.problem_id,
            parents=(candidate.id,),
            generation=candidate.generation + 1,
            intent="repair",
            failure_context="\n".join(failure_context),
        )
        LOGGER.info(
            "Queued repair candidate %s for failed candidate %s",
            repair_candidate.id,
            candidate.id,
        )
        self.pending_candidates.appendleft(repair_candidate)

    def _build_failure_context(
        self, candidate: ProgramCandidate, result: EvaluationResult
    ) -> List[str]:
        metrics = result.metrics
        context = [
            f"candidate_id: {candidate.id}",
            f"problem_id: {candidate.problem_id}",
            f"tier: {result.tier}",
            "status: failed",
            (
                "metrics: accuracy={:.3f}, runtime_ms={:.2f}, robustness={:.3f}, mem={:.2f}".format(
                    metrics.accuracy,
                    metrics.runtime_ms,
                    metrics.robustness,
                    metrics.memory_peak_mb,
                )
            ),
            f"eval_passes: {candidate.eval_passes}",
        ]
        if result.logs_path:
            context.append(f"logs_path: {result.logs_path}")
        return context

    def _export_archive(self) -> None:
        if not self.archive_export_path:
            return
        snapshot = self.archive_manager.snapshot()
        try:
            with self.archive_export_path.open("w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, indent=2)
        except OSError as error:  # pragma: no cover - best effort only
            LOGGER.debug("Failed to export archive snapshot: %s", error)
            return
        self._render_dashboard(snapshot)

    def _render_dashboard(self, snapshot: Mapping[str, object]) -> None:
        if not self.dashboard_path:
            return
        try:
            render_map_elites_dashboard(
                snapshot,
                self.archive_manager.candidates,
                complexity_bins=self.archive_manager.complexity_bins,
                robustness_bins=self.archive_manager.robustness_bins,
                output_path=self.dashboard_path,
            )
        except Exception as error:  # pragma: no cover - best effort only
            LOGGER.debug("Failed to render dashboard: %s", error)


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
    problem_specs = load_problem_specs(Path("configs/problems.json"))
    focus_problem = os.getenv("EVOLVE_PROBLEM")
    if focus_problem and focus_problem in problem_specs:
        ordered_ids = [focus_problem] + [pid for pid in problem_specs if pid != focus_problem]
        problem_specs = {pid: problem_specs[pid] for pid in ordered_ids}
    agent: LLMApiAgentAdapter | None = None
    model = os.getenv("LLM_API_MODEL")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if model and api_key:
        temperature_env = os.getenv("LLM_API_TEMPERATURE")
        try:
            temperature = float(temperature_env) if temperature_env is not None else None
        except ValueError:
            temperature = None
        agent = LLMApiAgentAdapter(
            model=model,
            api_key=api_key,
            base_url=os.getenv(
                "LLM_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
            temperature=temperature,
            system_prompt=os.getenv("LLM_API_SYSTEM_PROMPT"),
        )
    lineage_tracker = GitLineageTracker(Path(".artifacts/git_lineage"))
    generator = ProgramGenerator(
        problem_specs=problem_specs,
        output_root=Path(".artifacts/candidates"),
        agent=agent,
        lineage_tracker=lineage_tracker,
    )
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

    orchestrator.queue_initial_population(
        selection.bootstrap_population(
            generator,
            prompt_bandit,
            list(problem_specs.keys()),
        )
    )
    await orchestrator.run(max_steps=5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo_run())
