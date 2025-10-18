from __future__ import annotations

import json
import subprocess

from orchestrator.agents import GeminiAgentAdapter, GeminiAgentError
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
    adapter = GeminiAgentAdapter(cli_command=["gemini"], runner=_fake_runner_factory(payload))
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
