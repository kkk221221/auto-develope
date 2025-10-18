from __future__ import annotations

import json
import subprocess

from subprocess import TimeoutExpired

from orchestrator.agents import (
    GeminiAgentAdapter,
    GeminiAgentError,
    _NoopRateLimiter,
)
from orchestrator.prompt_policy import PromptMaterialization


def _fake_runner_factory(payload: dict[str, object], returncode: int = 0):
    def _runner(command, prompt, timeout):  # type: ignore[override]
        return subprocess.CompletedProcess(command, returncode, json.dumps(payload), "")

    return _runner


def test_gemini_adapter_parses_search_replace_payload() -> None:
    payload = {
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
    adapter = GeminiAgentAdapter(
        cli_command=["gemini"],
        runner=_fake_runner_factory(payload),
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


def test_gemini_adapter_raises_on_invalid_output() -> None:
    adapter = GeminiAgentAdapter(
        cli_command=["gemini"],
        runner=_fake_runner_factory({}, returncode=0),
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
    except GeminiAgentError as exc:
        assert "SEARCH/REPLACE" in str(exc)
    else:  # pragma: no cover - safety net
        raise AssertionError("Expected GeminiAgentError")


def test_gemini_adapter_retries_on_timeout() -> None:
    payload = {
        "patches": [
            {
                "diff_type": "sr",
                "payload": "def solve():\n    return 2",
                "file": "solutions/workdir/sample_solution.py",
            }
        ]
    }
    calls = {"count": 0}

    def _runner(command, prompt, timeout):  # type: ignore[override]
        if calls["count"] == 0:
            calls["count"] += 1
            raise TimeoutExpired(command, timeout)
        calls["count"] += 1
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    adapter = GeminiAgentAdapter(
        cli_command=["gemini"],
        runner=_runner,
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
