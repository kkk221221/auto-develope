from orchestrator.generation import _parse_failure_signals, _repair_snippet


def test_parse_failure_signals_detects_keywords() -> None:
    context = "TimeoutError: deadline exceeded; ValueError negative weight"
    signals = _parse_failure_signals(context)
    assert signals["timeout"]
    assert signals["negative"]


def test_repair_snippet_shortest_path_injects_guards() -> None:
    context = "timeout due to negative weight causing inf"
    snippet = _repair_snippet("shortest_path", context)
    assert "if len(queue) > nodes * 4" in snippet
    assert "if weight < 0" in snippet
    assert "return float('inf')  # unreachable" in snippet


def test_repair_snippet_knapsack_normalises_items() -> None:
    context = "TypeError in items iteration"
    snippet = _repair_snippet("knapsack", context)
    assert "_normalise_items" in snippet


def test_repair_snippet_sample_problem_handles_nan() -> None:
    context = "nan encountered"
    snippet = _repair_snippet("sample_problem", context)
    assert "total == float('inf')" in snippet
