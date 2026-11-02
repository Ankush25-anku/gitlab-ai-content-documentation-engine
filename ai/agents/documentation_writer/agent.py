"""Agent 2 - Documentation Writer: ContextPack -> first structured Draft for the requested content type."""
import json
import re

from ai.agents.base import AgentResult, AgentSpec, run_agent
from ai.prompts.loader import channel_for, content_type_template, tone_rules
from ai.retrieval.knowledge import glossary_prompt_text
from ai.schemas import ContextPack, Draft, Section, SourceRef

SPEC = AgentSpec(name="documentation_writer", stage="draft", output_model=Draft)

ENDPOINT_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+/[\w/:{}.-]+")
PARAM_FACT = re.compile(r"^`(\w+)` \((\w+), (required|optional)(?:, default `([^`]+)`)?\): (.*?)\.? \[(S\d+)\]\.$")
TABLE_HEADINGS = {"parameters", "configuration options"}


def _as_table(items: list[str]) -> list[str]:
    """Render parameter facts as a Markdown table; keep other items as sentences after it."""
    rows, rest = [], []
    for item in items:
        m = PARAM_FACT.match(item)
        if m:
            name, typ, req, default, desc, sid = m.groups()
            desc = desc + (f" Default: `{default}`." if default else "")
            rows.append(f"| `{name}` | {typ} | {'Yes' if req == 'required' else 'No'} | {desc} [{sid}] |")
        else:
            rest.append(item)
    if not rows:
        return items
    table = "| Attribute | Type | Required | Description |\n|-----------|------|----------|-------------|\n" + "\n".join(rows)
    return [table] + rest

# Keywords that steer a fact into a template heading (mock mode and a hint for real models).
HEADING_KEYWORDS: dict[str, list[str]] = {
    "the problem": ["problem", "slow", "manual", "hard", "because", "why", "pain", "wait", "cannot", "asking"],
    "what we built": ["adds", "new", "introduc", "now", "support"],
    "what's new": ["adds", "new", "introduc", "now", "support", "available"],
    "how it works": ["works", "calculat", "stores", "collect", "when", "each"],
    "prerequisites": ["require", "must", "prerequisite", "permission", "role", "tier", "premium", "ultimate",
                      "maintainer", "reporter", "need"],
    "before you begin": ["require", "must", "prerequisite", "permission", "role", "access"],
    "steps": ["step", "run", "configure", "set ", "enable", "add ", ".gitlab-ci.yml", "go to", "select", "review the"],
    "step-by-step setup": ["step", "run", "configure", "set ", "enable", "add ", ".gitlab-ci.yml", "go to", "select"],
    "how to get started": ["enable", "configure", "set ", "go to", "select", ".gitlab-ci.yml"],
    "try it": ["enable", "configure", "go to", "select", "try"],
    "configuration options": ["default", "option", "variable", "setting", "`"],
    "parameters": ["parameter", "attribute", "default", "required", "optional", "integer", "string", "boolean"],
    "endpoint": ["get /", "post /", "put /", "patch /", "delete /", "endpoint"],
    "example request": ["curl", "request"],
    "example response": ["response", "returns", "json"],
    "errors": ["error", "fail", "400", "401", "403", "404", "422", "returns 4", "`4"],
    "troubleshooting": ["error", "fail", "troubleshoot", "if the", "not working"],
    "changelog": ["deprecat", "removed", "breaking", "version", "introduced in"],
    "who it affects": ["users", "teams", "administrators", "maintainers", "developers", "affects"],
    "verify it works": ["verify", "check", "should see", "confirm"],
    "what's next": ["next", "future", "planned", "follow"],
    "next steps": ["next", "learn more", "see also"],
}
RELATED_HEADINGS = {"related links", "related topics"}
AUDIENCE_HEADINGS = {"who it affects", "who this guide is for"}


def _sentence(text: str, sid: str) -> str:
    text = text.strip().rstrip(".")
    return f"{text} [{sid}]."


def _best_heading(fact_text: str, headings: list[str]) -> str | None:
    low = fact_text.lower()
    best, best_score = None, 0
    for h in headings:
        score = sum(1 for kw in HEADING_KEYWORDS.get(h.lower(), []) if kw in low)
        if score > best_score:
            best, best_score = h, score
    return best


def mock_draft(pack: ContextPack, sources: list[SourceRef], job: dict, prompt_version: int) -> Draft:
    template = content_type_template(job["content_type"])
    headings: list[str] = template["required_headings"]
    first = headings[0]
    buckets: dict[str, list[str]] = {h: [] for h in headings}
    unused: list[str] = []
    endpoint_shown = False
    by_id = {s.id: s for s in sources}

    summary_fact = next((f for f in pack.facts if by_id.get(f.source_id) and by_id[f.source_id].origin == "input"),
                        None)
    for fact in pack.facts:
        src = by_id.get(fact.source_id)
        if (src and src.origin == "kb") or fact is summary_fact:
            continue  # KB facts are used for related links and terminology, not as new claims
        target = _best_heading(fact.text, [h for h in headings if h.lower() not in RELATED_HEADINGS])
        if target is None:
            if len(buckets[first]) >= 6:
                unused.append(fact.id)  # keep the opening section short; the reviewer sees what was left out
                continue
            target = first
        if target.lower() == "endpoint" and ENDPOINT_RE.search(fact.text) and not endpoint_shown:
            endpoint_shown = True
            ep = ENDPOINT_RE.search(fact.text).group(0)
            buckets[target].append(f"```plaintext\n{ep}\n```\n\n{_sentence(fact.text, fact.source_id)}")
        else:
            buckets[target].append(_sentence(fact.text, fact.source_id))

    meta = next((s for s in sources if s.chunk_id == "job:metadata"), None)
    kb = [s for s in sources if s.origin == "kb" and not s.stale]
    sections = []
    for h in headings:
        body_items = buckets[h]
        hl = h.lower()
        if hl in RELATED_HEADINGS or hl in ("next steps",) and not body_items:
            seen_docs: list[str] = []
            for s in kb:
                doc_title = s.title.split(" > ")[0]
                if doc_title not in seen_docs:
                    seen_docs.append(doc_title)
                    body_items.append(f"- {s.title} [{s.id}]")
                if len(seen_docs) == 4:
                    break
        if hl in AUDIENCE_HEADINGS and meta and not body_items:
            body_items.append(f"This content is written for {job['audience']} [{meta.id}].")
        if hl in TABLE_HEADINGS:
            body_items = _as_table(body_items)
        if not body_items:
            body_items = [f"[NEEDS SOURCE: {h.lower()} details are not in the provided inputs]"]
        joiner = "\n" if body_items[0].startswith("- ") else "\n\n"
        cited = sorted(set(re.findall(r"\[(S\d+)\]", " ".join(body_items))), key=lambda x: int(x[1:]))
        sections.append(Section(heading=h, body_markdown=joiner.join(body_items), source_ids=cited))

    if prompt_version < 2 and sections:
        # v1 has no self-check step; it tends to add an unsourced promotional claim.
        sections[0].body_markdown += ("\n\nThis update makes every pipeline dramatically faster and more "
                                      "reliable for all teams.")

    summary = _sentence(summary_fact.text, summary_fact.source_id) if summary_fact else pack.summary
    notes = [f"Gap: {g}" for g in pack.gaps] + [f"Conflict: {c}" for c in pack.conflicts]
    if unused:
        notes.append(f"Facts not used in this draft: {', '.join(unused)}")
    return Draft(title=job["title"], summary=summary, sections=sections,
                 assumptions=[f"Audience is {job['audience']}."], reviewer_notes=notes,
                 change_log=[f"First draft from {len(pack.facts)} facts using the {job['content_type']} template."])


def run(pack: ContextPack, sources: list[SourceRef], job: dict, prompt_version: int | None = None) -> AgentResult:
    from ai.prompts.loader import load_prompt
    version = prompt_version or load_prompt(SPEC.name).version
    template = content_type_template(job["content_type"])
    channel = channel_for(job["content_type"], job.get("target_channel"))
    facts = [f.model_dump() | {"source_title": next((s.title for s in sources if s.id == f.source_id), "")}
             for f in pack.facts]
    meta_src = next((s for s in sources if s.chunk_id == "job:metadata"), None)
    if meta_src:
        facts.append({"id": "F0", "source_id": meta_src.id, "text": meta_src.text, "confidence": "high"})
    variables = {
        "content_type": job["content_type"], "audience": job["audience"], "title": job["title"],
        "target_length": job.get("target_length", 600),
        "structure_template": " > ".join(template["required_headings"]) + ". " + template["guidance"],
        "tone_rules": " ".join(tone_rules(channel)), "glossary_terms": glossary_prompt_text(),
        "facts_json": json.dumps(facts, indent=1), "gaps": "; ".join(pack.gaps + pack.conflicts) or "none",
    }
    return run_agent(SPEC, variables, lambda: mock_draft(pack, sources, job, version), version)
