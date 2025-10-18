from __future__ import annotations

import random
from pathlib import Path

from orchestrator.generation import ProgramGenerator
from orchestrator.problem_specs import load_problem_specs
from orchestrator.prompt_policy import PromptBandit, PromptMaterialization
from orchestrator.selection import ArchiveManager, SelectionStrategy
from orchestrator.models import ArchiveState

PROBLEM_SPECS = load_problem_specs(Path("configs/problems.json"))


def test_program_generator_supports_multiple_problems(tmp_path) -> None:
    generator = ProgramGenerator(problem_specs=PROBLEM_SPECS, output_root=tmp_path / "multi")
    prompt = PromptMaterialization(
        name="mutate.perf_first",
        backend="flash",
        content="",
        generation=0,
        checklist=[],
    )
    sample_candidate = generator.spawn_candidate("mutate.perf_first", prompt, problem_id="sample_problem")
    shortest_prompt = PromptMaterialization(
        name="mutate.shortest_path.perf_first",
        backend="flash",
        content="",
        generation=0,
        checklist=[],
    )
    shortest_candidate = generator.spawn_candidate(
        "mutate.shortest_path.perf_first", shortest_prompt, problem_id="shortest_path"
    )
    knapsack_prompt = PromptMaterialization(
        name="mutate.knapsack.perf_first",
        backend="flash",
        content="",
        generation=0,
        checklist=[],
    )
    knapsack_candidate = generator.spawn_candidate(
        "mutate.knapsack.perf_first", knapsack_prompt, problem_id="knapsack"
    )

    assert sample_candidate.problem_id == "sample_problem"
    assert shortest_candidate.problem_id == "shortest_path"
    assert knapsack_candidate.problem_id == "knapsack"
    assert Path(sample_candidate.source_path).exists()
    assert Path(shortest_candidate.source_path).exists()
    assert Path(knapsack_candidate.source_path).exists()


def test_selection_bootstrap_distributes_over_problems(tmp_path) -> None:
    random.seed(7)
    generator = ProgramGenerator(problem_specs=PROBLEM_SPECS, output_root=tmp_path / "bootstrap")
    bandit = PromptBandit.from_directory("agents/prompts")
    archive = ArchiveManager(ArchiveState())
    strategy = SelectionStrategy(population_size=6, archive=archive, novelty_alpha=1.0, novelty_tau=4)
    seeds = strategy.bootstrap_population(
        generator,
        bandit,
        ["sample_problem", "shortest_path", "knapsack"],
    )
    problems = {seed.problem_id for seed in seeds}
    assert {"sample_problem", "shortest_path", "knapsack"}.issubset(problems)


def test_prompt_bandit_filters_by_intent() -> None:
    bandit = PromptBandit.from_directory("agents/prompts")
    mutate_arm, _ = bandit.pick_prompt(intent="mutate", problem_id="shortest_path")
    assert "shortest_path" in mutate_arm
    repair_arm, _ = bandit.pick_prompt(intent="repair", problem_id="knapsack")
    assert repair_arm.startswith("repair")


def test_repair_snippet_is_generated(tmp_path) -> None:
    generator = ProgramGenerator(problem_specs=PROBLEM_SPECS, output_root=tmp_path / "repair")
    prompt = PromptMaterialization(
        name="repair.v1",
        backend="flash",
        content="",
        generation=0,
        checklist=[],
    )
    candidate = generator.spawn_candidate(
        "repair.v1",
        prompt,
        problem_id="shortest_path",
        intent="repair",
        failure_context="tier=L1",
    )
    source = Path(candidate.source_path).read_text(encoding="utf-8")
    assert "def solve" in source
    assert candidate.patch_payload["intent"] == "repair"
