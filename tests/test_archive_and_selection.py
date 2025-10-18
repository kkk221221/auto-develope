from __future__ import annotations

import random
from pathlib import Path

from orchestrator.caching import CacheManager
from orchestrator.generation import ProgramGenerator
from orchestrator.models import (
    ArchiveState,
    BehaviorFeatures,
    EvaluationResult,
    Metrics,
    ProgramCandidate,
)
from orchestrator.prompt_policy import PromptBandit
from orchestrator.selection import ArchiveManager, SelectionStrategy


def _make_candidate(
    generator: ProgramGenerator,
    arm: str,
    backend: str,
    *,
    accuracy: float,
    runtime: float,
    robustness: float,
    loc: int,
) -> ProgramCandidate:
    candidate = generator.spawn_candidate(arm, backend)
    candidate.metrics = Metrics(
        accuracy=accuracy,
        runtime_ms=runtime,
        robustness=robustness,
        memory_peak_mb=runtime / 10.0,
        loc=loc,
    )
    candidate.behavior = BehaviorFeatures(
        coverage_bits=(loc,),
        hotspots={"main": runtime},
        output_signature=f"{accuracy:.2f}/{robustness:.2f}",
    )
    return candidate


def test_archive_manager_tracks_pareto_and_map(tmp_path) -> None:
    baseline = Path("solutions/workdir/sample_solution.py")
    generator = ProgramGenerator(baseline_path=baseline, output_root=tmp_path / "candidates")
    archive = ArchiveManager(ArchiveState(), complexity_bins=4, robustness_bins=4)

    cand_a = _make_candidate(generator, "mutate.perf_first", "flash", accuracy=0.95, runtime=12.0, robustness=0.8, loc=26)
    cand_b = _make_candidate(generator, "mutate.robust_first", "flash", accuracy=0.9, runtime=6.0, robustness=0.95, loc=34)
    cand_c = _make_candidate(generator, "mutate.simple_first", "flash", accuracy=0.7, runtime=18.0, robustness=0.6, loc=22)

    archive.update(cand_a)
    archive.update(cand_b)
    archive.update(cand_c)

    assert set(archive.state.pareto_front) == {cand_a.id, cand_b.id}
    assert archive.state.map_elites_cells
    assert cand_a.novelty_score > 0.0


def test_selection_strategy_generates_offspring(tmp_path) -> None:
    random.seed(42)
    baseline = Path("solutions/workdir/sample_solution.py")
    generator = ProgramGenerator(baseline_path=baseline, output_root=tmp_path / "population")
    prompt_bandit = PromptBandit.from_directory("agents/prompts")
    archive = ArchiveManager(ArchiveState())
    strategy = SelectionStrategy(population_size=4, archive=archive, novelty_alpha=1.0, novelty_tau=4)

    parent = _make_candidate(generator, "mutate.perf_first", "flash", accuracy=0.96, runtime=10.0, robustness=0.85, loc=24)
    archive.update(parent)
    strategy.observe_candidate(parent)

    child = strategy.select_next(generator, prompt_bandit)
    assert child is not None
    assert parent.id in child.parents
    assert child.generation == parent.generation + 1
    assert Path(child.source_path).exists()


def test_cache_manager_uses_content_signature(tmp_path) -> None:
    baseline = Path("solutions/workdir/sample_solution.py")
    generator = ProgramGenerator(baseline_path=baseline, output_root=tmp_path / "cache")
    cache = CacheManager()

    candidate = generator.spawn_candidate("mutate.perf_first", "flash")
    metrics = Metrics(accuracy=0.8, runtime_ms=15.0)
    result = EvaluationResult(candidate_id=candidate.id, tier="L0", passed=True, metrics=metrics)
    cache.record(candidate, result)

    clone = ProgramCandidate(
        id="clone",
        parents=candidate.parents,
        generation=candidate.generation,
        prompt_arm=candidate.prompt_arm,
        llm_backend=candidate.llm_backend,
        patch_payload=candidate.patch_payload,
        source_path=candidate.source_path,
    )

    assert cache.lookup(clone, "L0") is not None
    cache.invalidate(clone)
    assert cache.lookup(clone, "L0") is None

