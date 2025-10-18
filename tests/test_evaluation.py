from __future__ import annotations

import asyncio

import pytest

from orchestrator.evaluation import ProblemEvaluator, TierExecutor, TierSpec
from orchestrator.models import ProgramCandidate


@pytest.fixture
def evaluator() -> ProblemEvaluator:
    return ProblemEvaluator(
        {"sample_problem": "problems.sample_problem"},
        execution_timeout_s=5.0,
        memory_limit_mb=64,
    )


def _make_executor(evaluator: ProblemEvaluator) -> TierExecutor:
    return TierExecutor({"L0": TierSpec(name="L0", timeout_s=1, checks=[], tests=[])}, evaluator)


def _make_candidate(source_path: str) -> ProgramCandidate:
    return ProgramCandidate(
        id="cand",
        parents=(),
        generation=0,
        prompt_arm="arm",
        llm_backend="llm_api",
        patch_payload={},
        source_path=source_path,
    )


def test_execute_solver_enforces_timeout(evaluator: ProblemEvaluator, tmp_path) -> None:
    source_path = tmp_path / "candidate_timeout.py"
    source_path.write_text(
        "def solve(samples):\n"
        "    while True:\n"
        "        pass\n",
        encoding="utf-8",
    )
    timed_evaluator = ProblemEvaluator(
        evaluator.problem_packages,
        execution_timeout_s=0.2,
        memory_limit_mb=evaluator.memory_limit_mb,
    )
    with pytest.raises(TimeoutError):
        timed_evaluator._execute_solver(str(source_path), [])


def test_execute_solver_returns_value(evaluator: ProblemEvaluator, tmp_path) -> None:
    source_path = tmp_path / "candidate_ok.py"
    source_path.write_text(
        "def solve(samples):\n"
        "    return 42\n",
        encoding="utf-8",
    )
    result = evaluator._execute_solver(str(source_path), [1, 2, 3])
    assert result == 42.0


def test_ast_rules_rejects_dangerous_calls(
    evaluator: ProblemEvaluator, tmp_path
) -> None:
    source_path = tmp_path / "candidate_danger.py"
    source_path.write_text(
        "def solve(samples):\n"
        "    return eval('1 + 1')\n",
        encoding="utf-8",
    )
    executor = _make_executor(evaluator)
    candidate = _make_candidate(str(source_path))
    assert not asyncio.run(executor._ast_rules(candidate))


def test_ast_rules_rejects_suspicious_attributes(
    evaluator: ProblemEvaluator, tmp_path
) -> None:
    source_path = tmp_path / "candidate_attr.py"
    source_path.write_text(
        "def solve(samples):\n"
        "    return {'x': 1}.__class__\n",
        encoding="utf-8",
    )
    executor = _make_executor(evaluator)
    candidate = _make_candidate(str(source_path))
    assert not asyncio.run(executor._ast_rules(candidate))


def test_ast_rules_accepts_simple_solution(
    evaluator: ProblemEvaluator, tmp_path
) -> None:
    source_path = tmp_path / "candidate_safe.py"
    source_path.write_text(
        "def solve(samples):\n"
        "    total = 0\n"
        "    for value in samples:\n"
        "        total += value\n"
        "    return total\n",
        encoding="utf-8",
    )
    executor = _make_executor(evaluator)
    candidate = _make_candidate(str(source_path))
    assert asyncio.run(executor._ast_rules(candidate))
