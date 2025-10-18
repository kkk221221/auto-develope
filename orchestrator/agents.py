"""LLM agent adapters for candidate generation."""
from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Sequence

try:  # pragma: no cover - optional dependency may be absent in tests
    from openai import OpenAI  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for optional install
    OpenAI = None  # type: ignore[assignment]

try:  # pragma: no cover - optional safety for older clients
    from openai import (  # type: ignore
        APIConnectionError,
        APIError,
        APIStatusError,
        APITimeoutError,
        RateLimitError,
    )
except Exception:  # pragma: no cover - defensive fallback
    APIConnectionError = APIError = APIStatusError = APITimeoutError = RateLimitError = Exception  # type: ignore[misc,assignment]

from .prompt_policy import PromptMaterialization


DEFAULT_SYSTEM_PROMPT = (
    "You are an automated code-evolution agent. Respond with a single JSON object "
    "using compact formatting and no surrounding text. The JSON MUST match the schema "
    '{"version":1,"patches":[{"diff_type":"sr","file":"<problem_file>","payload":{"search":"<existing block>","replace":"<replacement block>"}}],"telemetry_tags":[]}.'
    "Rules: (1) version is always 1. (2) patches is an array; use an empty array if you have no safe change. (3) Each patch must set diff_type to \"sr\". (4) payload.search is an exact substring from the existing EVOLVE block, payload.replace is the full replacement block. (5) file must be one of the following based on the problem id in the user prompt: sample_problem -> solutions/workdir/sample_solution.py; shortest_path -> solutions/workdir/shortest_path_solution.py; knapsack -> solutions/workdir/knapsack_solution.py. (6) Do not emit markdown, code fences, comments, explanations, or additional keys."
)

LOGGER = logging.getLogger(__name__)


class LLMApiAgentError(RuntimeError):
    """Raised when the LLM API invocation fails or returns invalid data."""


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


_DEFAULT_RPM = _env_int("LLM_API_RATE_LIMIT_RPM", 45)
_DEFAULT_CONCURRENCY = _env_int("LLM_API_RATE_LIMIT_CONCURRENCY", 4)
_DEFAULT_BURST = _env_int("LLM_API_RATE_LIMIT_BURST", 6)
_DEFAULT_TIMEOUT = _env_int("LLM_API_TIMEOUT_S", 60)

if _DEFAULT_RPM > 0:
    _GLOBAL_RATE_LIMITER: _RateLimiter | _NoopRateLimiter = _RateLimiter(
        requests_per_minute=_DEFAULT_RPM,
        max_concurrency=max(1, _DEFAULT_CONCURRENCY),
        burst=max(1, _DEFAULT_BURST),
    )
else:
    _GLOBAL_RATE_LIMITER = _NoopRateLimiter()


class LLMApiAgentAdapter:
    """Adapter that communicates with an OpenAI-compatible LLM endpoint."""

    CompletionFactory = Callable[[PromptMaterialization], Iterable[str] | str]

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        timeout_s: int = _DEFAULT_TIMEOUT,
        system_prompt: str | None = None,
        stream: bool = True,
        completion_factory: CompletionFactory | None = None,
        rate_limiter: _RateLimiter | _NoopRateLimiter | None = None,
        max_retries: int = 3,
        backoff_base_s: float = 1.0,
        backoff_max_s: float = 32.0,
    ) -> None:
        if not model:
            raise ValueError("model must be provided")
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or os.getenv(
            "LLM_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.temperature = temperature
        self.timeout_s = timeout_s
        env_prompt = os.getenv("LLM_API_SYSTEM_PROMPT")
        self.system_prompt = system_prompt or env_prompt or DEFAULT_SYSTEM_PROMPT
        self.stream = stream
        self._rate_limiter = rate_limiter or _GLOBAL_RATE_LIMITER
        self._max_retries = max(0, max_retries)
        self._backoff_base = max(0.1, backoff_base_s)
        self._backoff_cap = max(self._backoff_base, backoff_max_s)
        self._client = None
        if completion_factory is None:
            if OpenAI is None:
                raise RuntimeError(
                    "openai package is required when completion_factory is not provided"
                )
            key = api_key or os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
            if not key:
                raise ValueError("api_key must be provided when completion_factory is not supplied")
            self._client = OpenAI(api_key=key, base_url=self.base_url)
        self._completion_factory = completion_factory or self._default_completion_factory

    def generate(self, prompt: PromptMaterialization) -> AgentGeneration:
        """Invoke the API and parse the JSON response."""

        with self._rate_limiter:
            payload, raw_response = self._invoke_with_retries(prompt)
        return self._parse_payload(payload, raw_response)

    def _invoke_with_retries(
        self, prompt: PromptMaterialization
    ) -> tuple[Mapping[str, Any], str]:
        attempt = 0
        while True:
            try:
                response = self._completion_factory(prompt)
                response_text = self._normalise_response(response)
                if not response_text:
                    raise LLMApiAgentError("LLM API returned an empty response")
                json_blob = self._extract_json_blob(response_text)
                if not json_blob:
                    raise LLMApiAgentError("LLM API response did not include a JSON object")
                return json.loads(json_blob), response_text
            except json.JSONDecodeError as exc:
                raise LLMApiAgentError("LLM API returned invalid JSON") from exc
            except (APITimeoutError, TimeoutError) as exc:
                message = f"LLM API timed out after {self.timeout_s} seconds"
                if attempt >= self._max_retries:
                    raise LLMApiAgentError(message) from exc
                delay = self._compute_backoff(attempt)
                LOGGER.warning(
                    "LLM API timeout (attempt %s/%s): %s; retrying in %.2fs",
                    attempt + 1,
                    self._max_retries,
                    message,
                    delay,
                )
                time.sleep(delay)
                attempt += 1
                continue
            except (APIConnectionError, RateLimitError) as exc:
                message = str(exc)
                if attempt >= self._max_retries:
                    raise LLMApiAgentError(f"LLM API connection error: {message}") from exc
                delay = self._compute_backoff(attempt)
                LOGGER.warning(
                    "LLM API connection issue (attempt %s/%s): %s; retrying in %.2fs",
                    attempt + 1,
                    self._max_retries,
                    message,
                    delay,
                )
                time.sleep(delay)
                attempt += 1
                continue
            except APIStatusError as exc:
                status_code = getattr(exc, "status_code", 0) or 0
                message = str(exc)
                should_retry = attempt < self._max_retries and self._should_retry(status_code, message)
                if not should_retry:
                    raise LLMApiAgentError(
                        f"LLM API request failed with status {status_code}: {message}"
                    ) from exc
                delay = self._compute_backoff(attempt)
                LOGGER.warning(
                    "LLM API status error (attempt %s/%s): %s; retrying in %.2fs",
                    attempt + 1,
                    self._max_retries,
                    message,
                    delay,
                )
                time.sleep(delay)
                attempt += 1
                continue
            except APIError as exc:
                status_code = getattr(exc, "status_code", 0) or 0
                message = str(exc)
                should_retry = attempt < self._max_retries and self._should_retry(status_code, message)
                if not should_retry:
                    raise LLMApiAgentError(f"LLM API request failed: {message}") from exc
                delay = self._compute_backoff(attempt)
                LOGGER.warning(
                    "LLM API error (attempt %s/%s): %s; retrying in %.2fs",
                    attempt + 1,
                    self._max_retries,
                    message,
                    delay,
                )
                time.sleep(delay)
                attempt += 1
                continue
            except Exception as exc:  # pragma: no cover - defensive catch-all
                status_code = getattr(exc, "status_code", 0) or 0
                message = str(exc)
                should_retry = attempt < self._max_retries and self._should_retry(status_code, message)
                if not should_retry:
                    raise LLMApiAgentError(f"LLM API request failed: {message}") from exc
                delay = self._compute_backoff(attempt)
                LOGGER.warning(
                    "LLM API exception (attempt %s/%s): %s; retrying in %.2fs",
                    attempt + 1,
                    self._max_retries,
                    message,
                    delay,
                )
                time.sleep(delay)
                attempt += 1

    def _default_completion_factory(self, prompt: PromptMaterialization) -> Iterable[str]:
        if not self._client:
            raise LLMApiAgentError("LLM API client is not initialised")
        messages = self._build_messages(prompt)
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": self.stream,
            "timeout": self.timeout_s,
        }
        if self.temperature is not None:
            request_kwargs["temperature"] = self.temperature
        completion = self._client.chat.completions.create(**request_kwargs)
        if self.stream:
            return self._consume_stream(completion)
        choice = completion.choices[0]
        content = getattr(choice, "message", None)
        text = ""
        if content is not None:
            text = getattr(content, "content", "") or ""
        else:
            text = getattr(choice, "text", "") or ""
        return [text]

    def _build_messages(self, prompt: PromptMaterialization) -> list[dict[str, object]]:
        checklist_section = ""
        if prompt.checklist:
            checklist_lines = "\n".join(f"- {item}" for item in prompt.checklist)
            checklist_section = f"\n\nChecklist:\n{checklist_lines}"
        metadata_block = json.dumps(
            {
                "prompt": prompt.name,
                "backend": prompt.backend,
                "generation": prompt.generation,
            },
            ensure_ascii=False,
        )
        user_content = f"{prompt.content}{checklist_section}\n\nMetadata: {metadata_block}"
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

    def _consume_stream(self, completion: Iterable[Any]) -> Iterable[str]:
        for chunk in completion:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = getattr(choice, "delta", None)
            if delta is not None:
                content = getattr(delta, "content", "") or ""
            else:
                content = getattr(choice, "text", "") or ""
            if content:
                yield content

    @staticmethod
    def _normalise_response(response: Iterable[str] | str) -> str:
        if isinstance(response, str):
            return response.strip()
        parts = []
        for part in response:
            if part:
                parts.append(str(part))
        return "".join(parts).strip()

    @staticmethod
    def _extract_json_blob(response_text: str) -> str:
        stripped = response_text.strip()
        if not stripped:
            return ""
        fenced_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            stripped,
            flags=re.DOTALL,
        )
        if fenced_match:
            return fenced_match.group(1).strip()
        brace_index = stripped.find("{")
        if brace_index == -1:
            return ""
        depth = 0
        for position, char in enumerate(stripped[brace_index:], start=brace_index):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return stripped[brace_index : position + 1].strip()
        return ""

    def _should_retry(self, status_code: int, message: str) -> bool:
        if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True
        lowered = message.lower()
        return "timeout" in lowered or "temporarily" in lowered or "retry" in lowered

    def _compute_backoff(self, attempt: int) -> float:
        capped_attempt = min(attempt, 8)
        base_delay = min(self._backoff_cap, self._backoff_base * (2 ** capped_attempt))
        jitter = random.uniform(0.85, 1.15)
        return max(0.25, base_delay * jitter)

    def _parse_payload(
        self, payload: Mapping[str, Any], raw_response: str
    ) -> AgentGeneration:
        if not isinstance(payload, Mapping):
            raise LLMApiAgentError("LLM API payload must be a JSON object")
        version = payload.get("version")
        try:
            version_int = int(version)
        except (TypeError, ValueError):
            raise LLMApiAgentError("LLM API payload is missing a valid version field")
        if version_int != 1:
            raise LLMApiAgentError(
                f"Unsupported LLM payload version: {version_int}"
            )
        patches = payload.get("patches")
        snippet = ""
        metadata: MutableMapping[str, Any] = {
            "strategy": "llm_api",
            "payload_version": version_int,
        }
        telemetry_tags: Sequence[str] = ()
        if isinstance(payload.get("telemetry_tags"), list):
            telemetry_tags = [str(tag) for tag in payload["telemetry_tags"]]
        found_patch = False
        if isinstance(patches, list):
            for patch in patches:
                if not isinstance(patch, Mapping):
                    continue
                diff_type = patch.get("diff_type")
                if str(diff_type).lower() != "sr":
                    raise LLMApiAgentError(
                        f"Unsupported diff_type in patch payload: {diff_type}"
                    )
                patch_payload = patch.get("payload")
                if isinstance(patch_payload, Mapping):
                    replacement = (
                        patch_payload.get("replace")
                        or patch_payload.get("replacement")
                        or patch_payload.get("body")
                    )
                    if isinstance(replacement, str) and replacement.strip():
                        snippet = replacement
                        metadata.update(
                            {
                                "anchor": patch_payload.get("search"),
                                "file": patch.get("file", ""),
                            }
                        )
                        found_patch = True
                        break
                elif isinstance(patch_payload, str) and patch_payload.strip():
                    snippet = patch_payload
                    metadata.update({"file": patch.get("file", "")})
                    found_patch = True
                    break
        if not found_patch or not snippet.strip():
            raise LLMApiAgentError("LLM API response did not include a SEARCH/REPLACE payload")
        metadata.update({"telemetry": list(telemetry_tags)})
        metadata["raw_response"] = raw_response[:4096]
        return AgentGeneration(snippet=snippet, metadata=metadata, telemetry_tags=telemetry_tags)
