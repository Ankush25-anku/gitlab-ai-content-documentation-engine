"""Agent runtime shared by all six agents.

Two providers:
  - "mock"   : runs each agent's deterministic implementation (no API key, used for local dev,
               CI and as a safe fallback). The pipeline, schemas, logging and UI behave exactly
               as in production.
  - "crewai" : builds a single-task CrewAI crew per stage with the agent's versioned prompt and
               Pydantic output schema, using any LiteLLM model string (default: Gemini).

Each stage runs as its own crew so the orchestrator can persist every intermediate output and
rerun any single stage.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from pydantic import BaseModel

from ai.prompts.loader import PromptTemplate, load_prompt
from backend.config import get_settings

# Waits before each retry when the model is overloaded (503) or rate limited (429).
BUSY_RETRY_DELAYS = (2, 4, 8, 16)
_BUSY_CODES = {429, 503}
_BUSY_TEXT = re.compile(r"\b(429|503)\b|UNAVAILABLE|RESOURCE_EXHAUSTED|high demand|overloaded|rate.?limit",
                        re.IGNORECASE)
# 429 bodies carry the wait Google wants: RetryInfo {"retryDelay": "13s"} or "Please retry in 13.2s."
_RETRY_AFTER = (re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s"),
                re.compile(r"retry in (\d+(?:\.\d+)?)\s*s", re.IGNORECASE))
# A longer suggested wait usually means the daily quota is gone: move to the fallback model instead.
MAX_SERVER_RETRY_DELAY = 90

# The orchestrator registers a callback here to show "AI service busy" on the job while we wait.
_on_busy: ContextVar[Callable[[str], None] | None] = ContextVar("on_model_busy", default=None)


class AgentError(Exception):
    """Raised when the model fails or returns output that does not validate."""


@contextmanager
def busy_notifications(callback: Callable[[str], None]) -> Iterator[None]:
    """Call `callback(message)` whenever an agent waits on a busy model inside this block."""
    token = _on_busy.set(callback)
    try:
        yield
    finally:
        _on_busy.reset(token)


def _notify_busy(message: str) -> None:
    callback = _on_busy.get()
    if callback:
        callback(message)


def _is_busy(exc: BaseException) -> bool:
    """True for 503 (overloaded) and 429 (rate limit) errors, including ones CrewAI wraps."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        for attr in ("status_code", "code"):
            if getattr(cur, attr, None) in _BUSY_CODES:
                return True
        if _BUSY_TEXT.search(str(cur)):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _retry_after(exc: BaseException) -> float | None:
    """The retry delay the server suggested in a 429 response, in seconds, if any."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        text = f"{cur} {getattr(cur, 'details', '')}"
        for pattern in _RETRY_AFTER:  # structured RetryInfo first, then the human-readable hint
            match = pattern.search(text)
            if match:
                return float(match.group(1))
        cur = cur.__cause__ or cur.__context__
    return None


def _with_provider(model: str) -> str:
    return model if "/" in model else f"gemini/{model}"


class _RateLimiter:
    """Hands out evenly spaced request slots (60 / per_minute seconds apart) to every thread in the process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def wait(self, per_minute: int) -> None:
        if per_minute <= 0:
            return
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + 60 / per_minute
        delay = slot - now
        if delay >= 2:
            _notify_busy(f"Pacing requests ({per_minute} per minute), continuing in {math.ceil(delay)}s…")
        if delay > 0:
            time.sleep(delay)


_limiter = _RateLimiter()
_hook_lock = threading.Lock()
_hook_installed = False


def _pace_llm_call(_context: Any) -> None:
    """CrewAI before_llm_call hook: runs once per real request, including CrewAI's own internal calls."""
    _limiter.wait(get_settings().llm_requests_per_minute)


def _install_rate_limit_hook() -> None:
    global _hook_installed
    with _hook_lock:
        if not _hook_installed:
            from crewai.hooks import register_before_llm_call_hook
            register_before_llm_call_hook(_pace_llm_call)
            _hook_installed = True


@dataclass
class AgentResult:
    output: BaseModel
    model: str
    prompt: PromptTemplate
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    attempts: int = 1
    meta: dict = field(default_factory=dict)


@dataclass
class AgentSpec:
    name: str                       # prompt folder name, e.g. "documentation_writer"
    stage: str                      # orchestrator stage name, e.g. "draft"
    output_model: type[BaseModel]
    model_setting: str = "llm_model_draft"


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def run_agent(spec: AgentSpec, variables: dict[str, Any], mock: Callable[[], BaseModel],
              prompt_version: int | None = None) -> AgentResult:
    settings = get_settings()
    prompt = load_prompt(spec.name, prompt_version)
    system, user = prompt.render(**variables)
    started = time.perf_counter()

    if settings.llm_provider == "mock":
        if settings.mock_latency_ms:
            time.sleep(settings.mock_latency_ms / 1000)
        output = mock()
        result = AgentResult(output=output, model="mock", prompt=prompt,
                             tokens_in=_estimate_tokens(system + user),
                             tokens_out=_estimate_tokens(output.model_dump_json()))
    else:
        result = _run_crewai(spec, prompt, system, user, variables, settings)

    result.latency_ms = int((time.perf_counter() - started) * 1000)
    return result


def _run_crewai(spec: AgentSpec, prompt: PromptTemplate, system: str, user: str,
                variables: dict, settings) -> AgentResult:
    try:
        from crewai import LLM, Agent, Crew, Process, Task
    except ImportError as exc:  # pragma: no cover
        raise AgentError("crewai is not installed; pip install -r requirements-ai.txt") from exc

    schema_hint = json.dumps(spec.output_model.model_json_schema())
    _install_rate_limit_hook()

    def attempt(model: str) -> AgentResult:
        # The Gemini provider and google-genai make a single attempt per call; retries live in
        # _call_with_retries only. max_retry_limit=0 stops CrewAI re-running the task on errors.
        llm = LLM(model=model, api_key=settings.gemini_api_key or None, temperature=0.2)
        agent = Agent(
            role=prompt.render_field("role", **variables),
            goal=prompt.render_field("goal", **variables),
            backstory=prompt.render_field("backstory", **variables) or prompt.role,
            llm=llm, allow_delegation=False, verbose=False, max_iter=1, max_retry_limit=0,
        )
        # Prompts are fully rendered here; kickoff() is called without inputs so CrewAI does not
        # try to interpolate the JSON braces inside the sources.
        task = Task(
            description=f"{system}\n\n{user}",
            expected_output=f"A JSON object valid against this JSON schema: {schema_hint}",
            agent=agent,
            output_pydantic=spec.output_model,
        )
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        out = crew.kickoff()
        parsed = out.pydantic or spec.output_model.model_validate_json(_extract_json(out.raw))
        usage = out.token_usage
        return AgentResult(output=parsed, model=model, prompt=prompt,
                           tokens_in=getattr(usage, "prompt_tokens", 0) or _estimate_tokens(system + user),
                           tokens_out=getattr(usage, "completion_tokens", 0) or _estimate_tokens(out.raw))

    models = [getattr(settings, spec.model_setting)]
    if settings.gemini_fallback_model:
        fallback = _with_provider(settings.gemini_fallback_model)
        if fallback != models[0]:
            models.append(fallback)
    return _call_with_retries(spec.name, models, attempt, settings.llm_max_retries)


def _call_with_retries(name: str, models: list[str], attempt: Callable[[str], AgentResult],
                       max_retries: int) -> AgentResult:
    """Busy errors (503/429): retry with BUSY_RETRY_DELAYS, then move to the next model.
    Other errors (bad output, timeouts): retry up to `max_retries` times on the same model."""
    calls = 0
    last_error: Exception | None = None
    for i, model in enumerate(models):
        busy_retries = other_retries = 0
        while True:
            calls += 1
            try:
                result = attempt(model)
                result.attempts = calls
                return result
            except Exception as exc:  # noqa: BLE001 - surfaced as MODEL_FAILED
                last_error = exc
                if not _is_busy(exc):
                    if other_retries >= max_retries:
                        raise AgentError(f"{name} failed after retries: {exc}") from exc
                    other_retries += 1
                    time.sleep(min(2 ** other_retries, 8))
                    continue
                if busy_retries >= len(BUSY_RETRY_DELAYS):
                    break
                suggested = _retry_after(exc)
                if suggested is not None and suggested > MAX_SERVER_RETRY_DELAY:
                    break
                busy_retries += 1
                progress = f"(retry {busy_retries} of {len(BUSY_RETRY_DELAYS)})…"
                if suggested is not None:
                    delay = suggested + 1
                    _notify_busy(f"Rate limit reached, continuing in {math.ceil(delay)}s {progress}")
                else:
                    delay = BUSY_RETRY_DELAYS[busy_retries - 1]
                    _notify_busy(f"AI service busy, retrying in {delay}s {progress}")
                time.sleep(delay)
        if i + 1 < len(models):
            _notify_busy(f"AI service still busy; switching to backup model {models[i + 1]}…")
    raise AgentError(f"AI service busy: {name} could not get a response from {' or '.join(models)} "
                     f"after retries. Try again in a few minutes. Last error: {str(last_error)[:200]}")


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start:end + 1] if start >= 0 else raw
