from __future__ import annotations

import pytest

from orchestrator.evaluation import ProblemEvaluator


@pytest.fixture
def evaluator() -> ProblemEvaluator:
    return ProblemEvaluator(
        {"sample_problem": "problems.sample_problem"},
        execution_timeout_s=0.5,
        memory_limit_mb=64,
    )


def test_execute_solver_enforces_timeout(evaluator: ProblemEvaluator, tmp_path) -> None:
    source_path = tmp_path / "candidate_timeout.py"
    source_path.write_text(
        "def solve(samples):\n"
        "    while True:\n"
        "        pass\n",
        encoding="utf-8",
    )
    with pytest.raises(TimeoutError):
        evaluator._execute_solver(str(source_path), [])


def test_execute_solver_returns_value(evaluator: ProblemEvaluator, tmp_path) -> None:
    source_path = tmp_path / "candidate_ok.py"
    source_path.write_text(
        "def solve(samples):\n"
        "    return 42\n",
        encoding="utf-8",
    )
    result = evaluator._execute_solver(str(source_path), [1, 2, 3])
    assert result == 42.0
