"""Agent 1 - Context Reader: sources -> ContextPack (facts with source ids, gaps, conflicts)."""
import json
import re

from ai.agents.base import AgentResult, AgentSpec, run_agent
from ai.retrieval.knowledge import terms_found_in
from ai.schemas import ContextPack, SourceFact, SourceRef
from ai.text_utils import INJECTION_RE

SPEC = AgentSpec(name="context_reader", stage="context", output_model=ContextPack)

ENDPOINT_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+/[\w/:{}.-]+")
VERSION_RE = re.compile(r"\b(?:GitLab\s+)?\d+\.\d+\b")
FACT_SIGNALS = re.compile(
    r"(`[^`]+`|\bdefault\b|\bdeprecat|\bflag\b|\bparameter\b|\battribute\b|\bendpoint\b|\bversion\b|"
    r"\brequire|\bbreaking\b|\blimit\b|\bremoved?\b|\badds?\b|\bnew\b|\bsupports?\b|\benabled?\b|"
    r"\btier\b|\bPremium\b|\bUltimate\b|\d)", re.I)
SPEAKER_RE = re.compile(r"^(?:Product manager|Engineer|Designer|Reviewer|Maintainer|PM|User|Customer)\s*:\s*", re.I)
DEFAULT_RE = re.compile(r"`(\w+)`[^.\n]*?\bdefaults?\b(?:\s+(?:value|is|to|of))*[:\s]+`?([\w.-]+)`?", re.I)

BLOCKING_NEEDS = {
    "api_reference": [(ENDPOINT_RE, "HTTP method and endpoint path")],
    "docs_page": [],
    "release_note": [],
    "blog": [],
    "onboarding_guide": [],
}
SOFT_NEEDS = {
    "api_reference": [(re.compile(r"\b(parameter|attribute)s?\b|\|\s*\w+\s*\|\s*(string|integer|boolean)", re.I),
                       "parameter list with types"),
                      (re.compile(r"\bresponse\b|\"\w+\"\s*:", re.I), "example response body")],
    "docs_page": [(re.compile(r"^\s*\d+\.\s|\bstep\b", re.I | re.M), "ordered setup steps"),
                  (re.compile(r"\bprerequisite|\brequires?\b|\bmust have\b", re.I), "prerequisites")],
    "release_note": [(VERSION_RE, "GitLab version the change ships in"),
                     (re.compile(r"\b(Free|Premium|Ultimate)\b"), "tier availability")],
    "blog": [(re.compile(r"\bwhy\b|\bproblem\b|\bbecause\b", re.I), "the user problem or motivation")],
    "onboarding_guide": [(re.compile(r"^\s*\d+\.\s|\bstep\b", re.I | re.M), "ordered setup steps")],
}


GRAPE_PARAM = re.compile(r"(requires|optional)\s+:(\w+),\s*type:\s*(\w+)(?:,\s*default:\s*([\w.'\"]+))?"
                         r"(?:,\s*desc:\s*'([^']*)')?")
GRAPE_ROUTE = re.compile(r"^(get|post|put|patch|delete)\s+'([^']+)'")
GRAPE_TEXT = re.compile(r"^(?:desc|detail)\s+'([^']+)'")


def _facts_from_diff(text: str) -> list[str]:
    """Pull documentation-relevant facts out of a code diff: routes, params, descriptions, comments."""
    facts = []
    for raw in text.splitlines():
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        line = raw[1:].strip()
        if m := GRAPE_ROUTE.match(line):
            path = m.group(2) if m.group(2).startswith("/") else "/projects/" + m.group(2)
            facts.append(f"The endpoint is `{m.group(1).upper()} {path}`.")
        elif m := GRAPE_PARAM.search(line):
            kind, name, typ, default, desc = m.groups()
            extra = f", default `{default.strip(chr(39) + chr(34))}`" if default else ""
            req = "required" if kind == "requires" else "optional"
            facts.append(f"`{name}` ({typ.lower()}, {req}{extra}): {desc or 'no description'}.")
        elif m := GRAPE_TEXT.match(line):
            facts.append(m.group(1).rstrip(".") + ".")
        elif line.startswith("#") and len(line.split()) >= 5:
            facts.append(line.lstrip("# ").rstrip(".") + ".")
    return facts


def _facts_from_openapi(text: str) -> list[str]:
    import yaml
    try:
        spec = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if not isinstance(spec, dict) or "paths" not in spec:
        return []
    facts = []
    for path, methods in (spec.get("paths") or {}).items():
        for method, op in (methods or {}).items():
            api_path = re.sub(r"\{(\w+)\}", r":\1", path)
            facts.append(f"The endpoint is `{method.upper()} {api_path}`.")
            for key in ("summary", "description"):
                if op.get(key):
                    facts.append(str(op[key]).strip().rstrip(".") + ".")
            for p in op.get("parameters", []):
                typ = (p.get("schema") or {}).get("type", "string")
                default = (p.get("schema") or {}).get("default")
                extra = f", default `{str(default).lower()}`" if default is not None else ""
                req = "required" if p.get("required") else "optional"
                facts.append(f"`{p['name']}` ({typ}, {req}{extra}): {p.get('description', '').rstrip('.')}.")
            for code, resp in (op.get("responses") or {}).items():
                facts.append(f"Response `{code}`: {str(resp.get('description', '')).rstrip('.')}.")
                for media in (resp.get("content") or {}).values():
                    if "example" in media:
                        import json
                        facts.append("Example response: `" + json.dumps(media["example"]) + "`.")
    return facts


def _candidate_lines(text: str, filename: str = "", strict: bool = False) -> list[str]:
    if filename.endswith((".diff", ".patch")) or text.lstrip().startswith("diff --git"):
        return _facts_from_diff(text)
    if filename.endswith((".yaml", ".yml", ".json")):
        spec_facts = _facts_from_openapi(text)
        if spec_facts:
            return spec_facts
    lines = []
    in_code = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line or line.startswith(("diff --git", "index ", "@@", "---", "+++", "#")):
            continue
        line = re.sub(r"^(#+|[-*]|\d+\.)\s+", "", line).strip()
        line = SPEAKER_RE.sub("", line)
        if len(line.split()) < 4 or set(line) <= set("|-: "):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z`])", line):
            if INJECTION_RE.search(sentence):
                continue  # instruction-like text inside a source is data, never a fact or an instruction
            # Job inputs: every real sentence matters. KB chunks: only fact-like sentences.
            if len(sentence.split()) >= 4 and (not strict or FACT_SIGNALS.search(sentence)):
                lines.append(sentence.strip())
    return lines


def mock_context(sources: list[SourceRef], content_type: str, audience: str) -> ContextPack:
    facts: list[SourceFact] = []
    seen: set[str] = set()
    input_sources = [s for s in sources if s.origin == "input" and s.chunk_id != "job:metadata"]
    kb_sources = [s for s in sources if s.origin == "kb"]
    from ai.text_utils import tokens
    seen_tokens: list[set[str]] = []
    for src in input_sources + kb_sources:
        if src.chunk_id == "job:metadata":
            continue
        limit = 14 if src.origin == "input" else 2
        filename = src.title.split(": ", 1)[-1]
        for line in _candidate_lines(src.text, filename, strict=src.origin == "kb")[:limit]:
            key = line.lower()
            toks = tokens(line)
            if key in seen or any(toks and len(toks & t) / len(toks | t) >= 0.8 for t in seen_tokens):
                continue  # near-duplicate of a fact already taken from an earlier source
            seen.add(key)
            seen_tokens.append(toks)
            conf = "high" if src.origin == "input" else "medium"
            if src.stale:
                conf = "low"
            facts.append(SourceFact(id=f"F{len(facts) + 1}", source_id=src.id, text=line, confidence=conf))

    # Check required information against both the raw inputs and the facts extracted from specs/diffs.
    all_input_text = "\n".join([s.text for s in input_sources] + [f.text for f in facts])
    gaps, blocking = [], []
    if not input_sources:
        blocking.append("No job inputs were provided; upload at least one technical source.")
    for rx, label in BLOCKING_NEEDS.get(content_type, []):
        if not rx.search(all_input_text):
            blocking.append(f"Missing {label} in the job inputs.")
    for rx, label in SOFT_NEEDS.get(content_type, []):
        if not rx.search(all_input_text):
            gaps.append(f"No {label} found in the sources.")
    suspicious = sorted({s.title for s in input_sources if INJECTION_RE.search(s.text)})
    if suspicious:
        gaps.append(f"Possible prompt injection ignored in: {', '.join(suspicious)}. Check these inputs.")
    stale = [s.title for s in kb_sources if s.stale]
    if stale:
        gaps.append(f"Retrieved documentation may be stale: {', '.join(sorted(set(stale)))}.")

    defaults: dict[str, dict[str, str]] = {}
    for src in sources:
        for name, value in DEFAULT_RE.findall(src.text):
            defaults.setdefault(name.lower(), {})[src.id] = value.strip("`.").lower()
    conflicts = []
    for name, by_src in defaults.items():
        if len(set(by_src.values())) > 1:
            detail = ", ".join(f"{v} in [{sid}]" for sid, v in by_src.items())
            conflicts.append(f"Default value of `{name}` differs between sources: {detail}.")

    first = input_sources[0].text if input_sources else (kb_sources[0].text if kb_sources else "")
    first_name = input_sources[0].title.split(": ", 1)[-1] if input_sources else ""
    summary_lines = _candidate_lines(first, first_name)[:2] or [first[:200]]
    return ContextPack(
        summary=" ".join(summary_lines)[:400],
        audience=audience,
        content_type=content_type,
        key_points=[f.text for f in facts[:5]],
        facts=facts[:40],
        gaps=gaps,
        blocking_gaps=blocking,
        conflicts=conflicts,
        terminology=terms_found_in(all_input_text),
    )


def run(sources: list[SourceRef], job: dict, prompt_version: int | None = None) -> AgentResult:
    variables = {
        "content_type": job["content_type"], "audience": job["audience"],
        "product_area": job["product_area"], "target_channel": job["target_channel"],
        "sources_json": json.dumps([s.model_dump(exclude={"score"}) for s in sources], indent=1),
    }
    return run_agent(SPEC, variables, lambda: mock_context(sources, job["content_type"], job["audience"]),
                     prompt_version)
