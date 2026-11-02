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
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel

from ai.prompts.loader import PromptTemplate, load_prompt
from backend.config import get_settings


class AgentError(Exception):
    """Raised when the model fails or returns output that does not validate."""


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

    model = getattr(settings, spec.model_setting)
    llm = LLM(model=model, api_key=settings.gemini_api_key or None, temperature=0.2)
    agent = Agent(
        role=prompt.render_field("role", **variables),
        goal=prompt.render_field("goal", **variables),
        backstory=prompt.render_field("backstory", **variables) or prompt.role,
        llm=llm, allow_delegation=False, verbose=False, max_iter=3,
    )
    schema_hint = json.dumps(spec.output_model.model_json_schema())
    # Prompts are fully rendered here; kickoff() is called without inputs so CrewAI does not
    # try to interpolate the JSON braces inside the sources.
    task = Task(
        description=f"{system}\n\n{user}",
        expected_output=f"A JSON object valid against this JSON schema: {schema_hint}",
        agent=agent,
        output_pydantic=spec.output_model,
    )
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    last_error: Exception | None = None
    for attempt in range(1, settings.llm_max_retries + 2):
        try:
            out = crew.kickoff()
            parsed = out.pydantic or spec.output_model.model_validate_json(_extract_json(out.raw))
            usage = out.token_usage
            return AgentResult(output=parsed, model=model, prompt=prompt,
                               tokens_in=getattr(usage, "prompt_tokens", 0) or _estimate_tokens(system + user),
                               tokens_out=getattr(usage, "completion_tokens", 0) or _estimate_tokens(out.raw),
                               attempts=attempt)
        except Exception as exc:  # noqa: BLE001 - surfaced as MODEL_FAILED
            last_error = exc
            time.sleep(min(2 ** attempt, 8))
    raise AgentError(f"{spec.name} failed after retries: {last_error}")


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start:end + 1] if start >= 0 else raw
