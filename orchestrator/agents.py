"""LLM agent adapters for candidate generation."""
from __future__ import annotations

import json
import logging
import os
import random
import subprocess
import threading
import time
from dataclasses import dataclass
from subprocess import TimeoutExpired
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from .prompt_policy import PromptMaterialization

LOGGER = logging.getLogger(__name__)

# Gemini CLI defaults: prefer non-interactive JSON output, auto-approve edits,
# and allow core tools invoked during code generation/evaluation.
DEFAULT_ALLOWED_TOOLS = ",".join(
    [
        "run_shell_command",
        "replace",
        "write_file",
        "read_file",
        "search_file_content",
        "web_fetch",
    ]
)
DEFAULT_CLI_COMMAND: Sequence[str] = (
    "gemini",
    "--output-format",
    "json",
    "--approval-mode",
    "auto_edit",
    "--allowed-tools",
    DEFAULT_ALLOWED_TOOLS,
)


class GeminiAgentError(RuntimeError):
    """Raised when the Gemini CLI invocation fails or returns invalid data."""


@dataclass
class AgentGeneration:
    """Represents a snippet and metadata produced by an agent backend."""

    snippet: str
    metadata: MutableMapping[str, Any]
    telemetry_tags: Sequence[str]


class _NoopRateLimiter:
    """Context manager that performs no throttling."""

    def __enter__(self) -> "_NoopRateLimiter":
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> bool:
        return False


class _RateLimiter:
    """Token-bucket rate limiter with optional concurrency control."""

    def __init__(
        self,
        *,
        requests_per_minute: int,
        max_concurrency: int,
        burst: int,
    ) -> None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        self._capacity = max(1, burst)
        self._tokens = float(self._capacity)
        self._refill_per_sec = max(requests_per_minute, 1) / 60.0
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_concurrency)
        self._max_sleep = min(5.0, max(0.25, 1.0 / self._refill_per_sec))

    def __enter__(self) -> "_RateLimiter":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> bool:
        self.release()
        return False

    def acquire(self) -> None:
        self._semaphore.acquire()
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                if elapsed > 0:
                    self._tokens = min(
                        float(self._capacity),
                        self._tokens + elapsed * self._refill_per_sec,
                    )
                    self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = 1.0 - self._tokens
                sleep_time = max(deficit / self._refill_per_sec, 0.1)
                sleep_time = min(sleep_time, self._max_sleep)
            time.sleep(sleep_time)

    def release(self) -> None:
        self._semaphore.release()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


_DEFAULT_RPM = _env_int("GEMINI_RATE_LIMIT_RPM", 45)
_DEFAULT_CONCURRENCY = _env_int("GEMINI_RATE_LIMIT_CONCURRENCY", 4)
_DEFAULT_BURST = _env_int("GEMINI_RATE_LIMIT_BURST", 6)
_DEFAULT_TIMEOUT = _env_int("GEMINI_CLI_TIMEOUT_S", 60)

if _DEFAULT_RPM > 0:
    _GLOBAL_RATE_LIMITER: _RateLimiter | _NoopRateLimiter = _RateLimiter(
        requests_per_minute=_DEFAULT_RPM,
        max_concurrency=max(1, _DEFAULT_CONCURRENCY),
        burst=max(1, _DEFAULT_BURST),
    )
else:
    _GLOBAL_RATE_LIMITER = _NoopRateLimiter()


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
        timeout_s: int = _DEFAULT_TIMEOUT,
        runner: Callable[[Sequence[str], str, int], subprocess.CompletedProcess[str]] | None = None,
        rate_limiter: _RateLimiter | _NoopRateLimiter | None = None,
        max_retries: int = 3,
        backoff_base_s: float = 1.0,
        backoff_max_s: float = 32.0,
    ) -> None:
        self.cli_command = list(cli_command or DEFAULT_CLI_COMMAND)
        self.timeout_s = timeout_s
        self._runner = runner or self._default_runner
        self._rate_limiter = rate_limiter or _GLOBAL_RATE_LIMITER
        self._max_retries = max(0, max_retries)
        self._backoff_base = max(0.1, backoff_base_s)
        self._backoff_cap = max(self._backoff_base, backoff_max_s)

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

        with self._rate_limiter:
            payload = self._invoke_with_retries(prompt)
        return self._parse_payload(payload)

    def _invoke_with_retries(self, prompt: PromptMaterialization) -> Mapping[str, Any]:
        command = list(self.cli_command)
        attempt = 0
        while True:
            LOGGER.debug("Invoking Gemini CLI: %s", " ".join(command))
            try:
                completed = self._runner(command, prompt.content, self.timeout_s)
            except TimeoutExpired as exc:
                message = self._format_timeout_message(exc)
                if attempt >= self._max_retries:
                    raise GeminiAgentError(message) from exc
                delay = self._compute_backoff(attempt)
                LOGGER.warning(
                    "Gemini CLI timeout (attempt %s/%s): %s; retrying in %.2fs",
                    attempt + 1,
                    self._max_retries,
                    message,
                    delay,
                )
                time.sleep(delay)
                attempt += 1
                continue

            stdout = completed.stdout.strip() if completed.stdout else ""
            stderr = completed.stderr.strip() if completed.stderr else ""
            if completed.returncode == 0 and stdout:
                try:
                    return json.loads(stdout)
                except json.JSONDecodeError as exc:
                    raise GeminiAgentError("Gemini CLI returned invalid JSON") from exc

            message = stderr or stdout or "no output"
            should_retry = (
                attempt < self._max_retries and self._should_retry(message, completed.returncode)
            )
            if not should_retry:
                raise GeminiAgentError(
                    f"Gemini CLI failed with code {completed.returncode}: {message}"
                )
            delay = self._compute_backoff(attempt)
            LOGGER.warning(
                "Gemini CLI throttled (attempt %s/%s): %s; retrying in %.2fs",
                attempt + 1,
                self._max_retries,
                message.splitlines()[0],
                delay,
            )
            time.sleep(delay)
            attempt += 1

    def _should_retry(self, message: str, returncode: int) -> bool:
        lowered = message.lower()
        rate_limit_signals = (
            "429" in lowered
            or ("rate" in lowered and "limit" in lowered)
            or "resource exhausted" in lowered
            or "quota" in lowered
            or "too many requests" in lowered
        )
        timeout_signal = "timeout" in lowered
        transient_exit = returncode in {54, 255}
        return rate_limit_signals or timeout_signal or transient_exit

    def _compute_backoff(self, attempt: int) -> float:
        capped_attempt = min(attempt, 8)
        base_delay = min(self._backoff_cap, self._backoff_base * (2 ** capped_attempt))
        jitter = random.uniform(0.85, 1.15)
        return max(0.25, base_delay * jitter)

    def _format_timeout_message(self, exc: TimeoutExpired) -> str:
        timeout = exc.timeout if exc.timeout else self.timeout_s
        stderr_msg = ""
        if exc.stderr:
            stderr_msg = str(exc.stderr).strip()
        return f"Gemini CLI timed out after {timeout} seconds{': ' + stderr_msg if stderr_msg else ''}"

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
