"""LLM agent adapters for candidate generation."""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from .prompt_policy import PromptMaterialization

LOGGER = logging.getLogger(__name__)


class GeminiAgentError(RuntimeError):
    """Raised when the Gemini CLI invocation fails or returns invalid data."""


@dataclass
class AgentGeneration:
    """Represents a snippet and metadata produced by an agent backend."""

    snippet: str
    metadata: MutableMapping[str, Any]
    telemetry_tags: Sequence[str]


class GeminiAgentAdapter:
    """Thin wrapper around the `gemini-cli` executable.

    The adapter expects prompts that already embed instructions for JSON-only
    output matching the schema described in the project documentation. The
    command invocation can be customised for tests via the ``runner`` callback.
    """

    def __init__(
        self,
        *,
        cli_command: Sequence[str] | None = None,
        timeout_s: int = 120,
        runner: Callable[[Sequence[str], str, int], subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.cli_command = list(cli_command or ["gemini", "prompt", "--output", "json"])
        self.timeout_s = timeout_s
        self._runner = runner or self._default_runner

    @staticmethod
    def _default_runner(
        command: Sequence[str],
        prompt: str,
        timeout_s: int,
    ) -> subprocess.CompletedProcess[str]:
        """Invoke the CLI via ``subprocess.run``."""

        return subprocess.run(  # noqa: S603,S607 - deliberate CLI execution
            command,
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )

    def generate(self, prompt: PromptMaterialization) -> AgentGeneration:
        """Execute the CLI and parse the JSON response."""

        command = list(self.cli_command)
        LOGGER.debug("Invoking Gemini CLI: %s", " ".join(command))
        completed = self._runner(command, prompt.content, self.timeout_s)
        if completed.returncode != 0:
            stderr = completed.stderr.strip() if completed.stderr else "(no stderr)"
            raise GeminiAgentError(f"Gemini CLI failed with code {completed.returncode}: {stderr}")
        stdout = completed.stdout.strip()
        if not stdout:
            raise GeminiAgentError("Gemini CLI produced no output")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise GeminiAgentError("Gemini CLI returned invalid JSON") from exc
        return self._parse_payload(payload)

    def _parse_payload(self, payload: Mapping[str, Any]) -> AgentGeneration:
        patches = payload.get("patches")
        snippet = ""
        metadata: MutableMapping[str, Any] = {
            "strategy": "gemini_cli",
        }
        telemetry_tags: Sequence[str] = ()
        if isinstance(payload.get("telemetry_tags"), list):
            telemetry_tags = [str(tag) for tag in payload["telemetry_tags"]]
        if isinstance(patches, list):
            for patch in patches:
                if not isinstance(patch, Mapping):
                    continue
                diff_type = str(patch.get("diff_type", "")).lower()
                if diff_type != "sr":
                    continue
                patch_payload = patch.get("payload")
                if isinstance(patch_payload, Mapping):
                    replacement = (
                        patch_payload.get("replace")
                        or patch_payload.get("replacement")
                        or patch_payload.get("body")
                    )
                    if isinstance(replacement, str) and replacement.strip():
                        snippet = replacement
                        metadata.update({
                            "anchor": patch_payload.get("search"),
                            "file": patch.get("file", ""),
                        })
                        break
                if isinstance(patch_payload, str) and patch_payload.strip():
                    snippet = patch_payload
                    metadata.update({"file": patch.get("file", "")})
                    break
        if not snippet:
            plan = payload.get("plan")
            if isinstance(plan, list) and plan:
                first_step = plan[0]
                if isinstance(first_step, Mapping):
                    snippet = str(first_step.get("snippet", ""))
        if not snippet:
            raise GeminiAgentError("Gemini CLI response did not include a SEARCH/REPLACE payload")
        metadata.update({"telemetry": list(telemetry_tags)})
        return AgentGeneration(snippet=snippet, metadata=metadata, telemetry_tags=telemetry_tags)
