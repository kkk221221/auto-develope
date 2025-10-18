from __future__ import annotations

import json
import os

import pytest

from orchestrator.agents import LLMApiAgentAdapter
from orchestrator.prompt_policy import PromptMaterialization


@pytest.mark.integration
def test_llm_api_adapter_uses_real_api() -> None:
    pytest.importorskip("openai")

    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        pytest.skip("DASHSCOPE_API_KEY is not configured")

    expected_payload = {
        "version": 1,
        "patches": [
            {
                "diff_type": "sr",
                "payload": {
                    "search": "PLACEHOLDER",
                    "replace": "def solve():\n    return 123",
                },
                "file": "solutions/workdir/sample_solution.py",
            }
        ],
    }

    expected_json = json.dumps(expected_payload, ensure_ascii=False)
    adapter = LLMApiAgentAdapter(
        model=os.getenv("LLM_API_TEST_MODEL", "qwen3-max"),
        api_key=api_key,
        temperature=0.0,
        stream=True,
        system_prompt=(
            "You are an integration test helper. "
            "Reply ONLY with the JSON payload described in the user prompt. "
            "Do not add commentary or formatting even if metadata is provided."
        ),
        max_retries=0,
    )

    prompt = PromptMaterialization(
        name="integration.test",
        backend="integration",
        content=(
            "Return EXACTLY the following JSON without markdown fences, explanations, or extra whitespace. "
            "Ignore any metadata after the blank line.\n"
            f"{expected_json}"
        ),
        generation=0,
        checklist=[],
    )

    result = adapter.generate(prompt)
    assert result.snippet
    assert "def solve" in result.snippet
    assert result.metadata["strategy"] == "llm_api"
