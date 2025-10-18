from __future__ import annotations

import json
from typing import Callable

import pytest

from orchestrator.agents import LLMApiAgentAdapter, LLMApiAgentError, _NoopRateLimiter
from orchestrator.prompt_policy import PromptMaterialization


def _fake_completion_factory(payload: dict[str, object]) -> Callable[[PromptMaterialization], str]:
    def _complete(_: PromptMaterialization) -> str:
        return json.dumps(payload)

    return _complete


def test_llm_api_adapter_parses_search_replace_payload() -> None:
    payload = {
        "version": 1,
        "patches": [
            {
                "diff_type": "sr",
                "payload": {
                    "search": "EVOLVE", "replace": "def solve():\n    return 1"
                },
                "file": "solutions/workdir/sample_solution.py",
            }
        ],
        "telemetry_tags": ["explore"],
    }
    adapter = LLMApiAgentAdapter(
        model="test-model",
        completion_factory=_fake_completion_factory(payload),
        rate_limiter=_NoopRateLimiter(),
    )
    prompt = PromptMaterialization(
        name="mutate.perf_first",
        backend="flash",
        content="instructions",
        generation=0,
        checklist=[],
    )
    result = adapter.generate(prompt)
    assert "def solve" in result.snippet
    assert result.metadata["file"] == "solutions/workdir/sample_solution.py"
    assert result.metadata["telemetry"] == ["explore"]
    assert result.metadata["payload_version"] == 1
    assert "raw_response" in result.metadata


def test_llm_api_adapter_raises_on_invalid_output() -> None:
    adapter = LLMApiAgentAdapter(
        model="test-model",
        completion_factory=_fake_completion_factory({"version": 1, "patches": []}),
        rate_limiter=_NoopRateLimiter(),
    )
    prompt = PromptMaterialization(
        name="mutate.robust_first",
        backend="flash",
        content="",
        generation=0,
        checklist=[],
    )
    try:
        adapter.generate(prompt)
    except LLMApiAgentError as exc:
        assert "SEARCH/REPLACE" in str(exc)
    else:  # pragma: no cover - safety net
        raise AssertionError("Expected LLMApiAgentError")


def test_llm_api_adapter_retries_on_timeout() -> None:
    payload = {
        "version": 1,
        "patches": [
            {
                "diff_type": "sr",
                "payload": "def solve():\n    return 2",
                "file": "solutions/workdir/sample_solution.py",
            }
        ]
    }
    calls = {"count": 0}

    def _completion(_: PromptMaterialization) -> str:
        if calls["count"] == 0:
            calls["count"] += 1
            raise TimeoutError()
        calls["count"] += 1
        return json.dumps(payload)

    adapter = LLMApiAgentAdapter(
        model="test-model",
        completion_factory=_completion,
        rate_limiter=_NoopRateLimiter(),
        max_retries=1,
    )
    prompt = PromptMaterialization(
        name="mutate.perf_first",
        backend="flash",
        content="instructions",
        generation=0,
        checklist=[],
    )
    result = adapter.generate(prompt)
    assert result.snippet.startswith("def solve")
    assert calls["count"] == 2


def test_llm_api_adapter_extracts_json_from_code_fence() -> None:
    fenced_payload = """```json
    {"version": 1, "patches": [{"diff_type": "sr", "payload": "x"}]}
    ```"""

    adapter = LLMApiAgentAdapter(
        model="test-model",
        completion_factory=_fake_completion_factory({"patches": []}),
        rate_limiter=_NoopRateLimiter(),
    )

    extracted = adapter._extract_json_blob(fenced_payload)
    assert extracted == '{"version": 1, "patches": [{"diff_type": "sr", "payload": "x"}]}'


def test_llm_api_adapter_rejects_missing_version() -> None:
    adapter = LLMApiAgentAdapter(
        model="test-model",
        completion_factory=_fake_completion_factory({"patches": []}),
        rate_limiter=_NoopRateLimiter(),
    )
    prompt = PromptMaterialization(
        name="mutate.robust_first",
        backend="flash",
        content="",
        generation=0,
        checklist=[],
    )
    with pytest.raises(LLMApiAgentError):
        adapter.generate(prompt)
