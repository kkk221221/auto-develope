from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.caching import CacheManager
from orchestrator.models import (
    ArchiveState,
    BehaviorFeatures,
    EvalStatus,
    Metrics,
    ProgramCandidate,
    candidate_from_payload,
    candidate_to_payload,
)
from orchestrator.persistence import FilesystemPersistence, RunState
from orchestrator.prompt_policy import PromptBandit
from orchestrator.selection import ArchiveManager, SelectionStrategy


def _make_candidate(workdir: Path, candidate_id: str, arm: str) -> ProgramCandidate:
    source = workdir / f"{candidate_id}.py"
    source.write_text(
        "def solve(pairs):\n    return 42.0\n",
        encoding="utf-8",
    )
    candidate = ProgramCandidate(
        id=candidate_id,
        parents=(),
        generation=0,
        prompt_arm=arm,
        llm_backend="flash",
        patch_payload={"diff_type": "sr", "payload": "return 42.0"},
        problem_id="sample_problem",
        source_path=str(source),
    )
    candidate.metrics = Metrics(
        accuracy=0.9,
        runtime_ms=12.5,
        memory_peak_mb=1.1,
        loc=5,
        cyclomatic=2.0,
        robustness=0.75,
        llm_style=0.65,
    )
    candidate.behavior = BehaviorFeatures(
        coverage_bits=(1, 2, 3),
        hotspots={"runtime_mean": 12.5},
        output_signature="sig",
    )
    candidate.eval_passes = ["L0"]
    candidate.status = EvalStatus.SUCCEEDED
    return candidate


def test_candidate_serialisation_round_trip(tmp_path: Path) -> None:
    bandit = PromptBandit.from_directory("agents/prompts")
    arm = next(iter(bandit.arms))
    candidate = _make_candidate(tmp_path, "cand", arm)
    payload = candidate_to_payload(candidate)
    restored = candidate_from_payload(payload)
    assert restored.id == candidate.id
    assert restored.prompt_arm == candidate.prompt_arm
    assert restored.metrics.accuracy == pytest.approx(candidate.metrics.accuracy)
    assert tuple(restored.behavior.coverage_bits) == tuple(candidate.behavior.coverage_bits)
    assert restored.status == EvalStatus.SUCCEEDED


def test_filesystem_persistence_roundtrip(tmp_path: Path) -> None:
    bandit = PromptBandit.from_directory("agents/prompts")
    arm = next(iter(bandit.arms))
    archive = ArchiveManager(ArchiveState())
    selection = SelectionStrategy(
        population_size=2,
        archive=archive,
        default_prompt_arm=arm,
        novelty_alpha=1.0,
        novelty_tau=4,
    )
    cache = CacheManager()
    cache.stats.record_hit()
    cache.stats.record_miss()

    candidate = _make_candidate(tmp_path, "cand", arm)
    archive.update(candidate)
    selection.observe_candidate(candidate)
    bandit.update_reward(arm, 0.8)

    pending = _make_candidate(tmp_path, "pending", arm)
    run_state = RunState(
        archive_snapshot=archive.snapshot(),
        selection_snapshot=selection.snapshot(),
        prompt_snapshot=bandit.snapshot(),
        cache_snapshot=cache.snapshot(),
        pending_candidates=[candidate_to_payload(pending)],
    )
    persistence = FilesystemPersistence(tmp_path / "state.json")
    persistence.save(run_state)

    loaded = persistence.load()
    assert loaded is not None

    restored_archive = ArchiveManager(ArchiveState())
    restored_archive.restore(loaded.archive_snapshot)
    assert set(restored_archive.candidates) == set(archive.candidates)

    restored_selection = SelectionStrategy(
        population_size=2,
        archive=restored_archive,
        default_prompt_arm=arm,
        novelty_alpha=1.0,
        novelty_tau=4,
    )
    restored_selection.restore(loaded.selection_snapshot, restored_archive)
    assert restored_selection.snapshot()["population"] == selection.snapshot()["population"]

    restored_bandit = PromptBandit.from_directory("agents/prompts")
    restored_bandit.restore(loaded.prompt_snapshot)
    assert restored_bandit.arms[arm].successes == pytest.approx(bandit.arms[arm].successes)

    restored_cache = CacheManager()
    restored_cache.restore(loaded.cache_snapshot)
    assert restored_cache.stats.lookups == cache.stats.lookups
    assert restored_cache.stats.hits == cache.stats.hits

    restored_pending = list(loaded.iter_pending())
    assert len(restored_pending) == 1
    assert restored_pending[0].id == "pending"
