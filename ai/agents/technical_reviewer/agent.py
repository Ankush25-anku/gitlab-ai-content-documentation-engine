"""Agent 3 - Technical Reviewer: checks every claim against the sources.

It corrects wrong or missing citations, but it never silently deletes an unsupported claim:
unsupported claims are reported and block approval until a human resolves them.
"""
import json
import re

from ai.agents.base import AgentResult, AgentSpec, run_agent
from ai.schemas import ClaimCheck, ContextPack, Draft, ReviewReport, Section, SourceRef, TechReviewOutput
from ai.text_utils import (NEEDS_SOURCE_RE, citations, is_checkable, normalise_citations, normalise_draft, overlap,
                           plain_text, split_sentences)

SPEC = AgentSpec(name="technical_reviewer", stage="tech_review", output_model=TechReviewOutput,
                 model_setting="llm_model_review")

SUPPORTED, PARTIAL = 0.6, 0.35
RISK_WORDS = {
    "breaking": "Breaking change mentioned; confirm upgrade guidance is complete.",
    "deprecat": "Deprecation mentioned; confirm the removal milestone with the product owner.",
    "security": "Security-related statement; needs a security reviewer.",
    "token": "Mentions tokens or credentials; check no secret values appear.",
    "delete": "Describes deletion; confirm data-loss behaviour is accurately stated.",
    "migration": "Describes a migration; confirm steps were tested.",
}


def check_claim(sentence: str, sources: dict[str, SourceRef]) -> ClaimCheck:
    cited = citations(sentence)
    valid = [c for c in cited if c in sources]
    invalid = [c for c in cited if c not in sources]
    plain = plain_text(sentence)

    if valid:
        best = max(overlap(plain, sources[c].text) for c in valid)
        if best >= SUPPORTED and not invalid:
            return ClaimCheck(claim=plain, verdict="supported", source_ids=valid)
        if best >= PARTIAL:
            return ClaimCheck(claim=plain, verdict="partial", source_ids=valid,
                              fix=("Remove invalid citation(s) " + ", ".join(invalid)) if invalid
                              else "Only part of this sentence is stated by the cited source; narrow it.")
    # No (valid) citation that supports it: look for any source that does.
    scored = sorted(((overlap(plain, s.text), sid) for sid, s in sources.items()), reverse=True)
    if scored and scored[0][0] >= SUPPORTED:
        return ClaimCheck(claim=plain, verdict="partial", source_ids=[scored[0][1]],
                          fix=f"Cite [{scored[0][1]}] for this sentence.")
    fix = "No source states this. Remove it or add a source that does."
    if invalid:
        fix = f"Cited source(s) {', '.join(invalid)} do not exist. " + fix
    return ClaimCheck(claim=plain, verdict="unsupported", source_ids=[], fix=fix)


def _apply_citation_fixes(body: str, checks: list[ClaimCheck]) -> str:
    body = normalise_citations(body, known_ids=())  # so "[S9]" can be removed even from "[S1, S9]"
    for chk in checks:
        if chk.verdict == "partial" and chk.fix and chk.fix.startswith("Cite [") and chk.source_ids:
            idx = body.find(chk.claim)
            if idx >= 0:
                end = idx + len(chk.claim)
                body = body[:end].rstrip(".") + f" [{chk.source_ids[0]}]." + body[end:].lstrip(".")
        if chk.fix and chk.fix.startswith("Remove invalid citation"):
            for bad in re.findall(r"S\d+", chk.fix.split("(s)")[1]):
                body = body.replace(f"[{bad}]", "")
    return body


def mock_review(draft: Draft, sources: list[SourceRef]) -> TechReviewOutput:
    by_id = {s.id: s for s in sources}
    all_checks: list[ClaimCheck] = []
    new_sections: list[Section] = []
    texts = [("summary", draft.summary)] + [(s.heading, s.body_markdown) for s in draft.sections]
    fixed_summary = draft.summary
    for heading, body in texts:
        checks = []
        if heading.lower() in ("related links", "related topics"):  # navigation links, not claims
            new_sections.append(next(s for s in draft.sections if s.heading == heading))
            continue
        for sentence in split_sentences(body):
            if NEEDS_SOURCE_RE.search(sentence) or not is_checkable(sentence) or sentence.startswith("|"):
                continue
            checks.append(check_claim(sentence, by_id))
        all_checks.extend(checks)
        fixed = _apply_citation_fixes(body, checks)
        if heading == "summary":
            fixed_summary = fixed
        else:
            orig = next(s for s in draft.sections if s.heading == heading)
            new_sections.append(orig.model_copy(update={
                "body_markdown": fixed,
                "source_ids": sorted(set(citations(fixed)), key=lambda x: int(x[1:]))}))

    full = " ".join(t for _, t in texts).lower()
    risks = [msg for word, msg in RISK_WORDS.items() if word in full]
    unsupported = [c for c in all_checks if c.verdict == "unsupported"]
    questions = [f"Is this claim correct, and what is its source? \"{c.claim[:120]}\"" for c in unsupported]
    questions += [f"Please resolve: {n}" for n in draft.reviewer_notes if n.startswith("Conflict")]
    fixed_count = sum(1 for c in all_checks if c.fix and c.fix.startswith(("Cite [", "Remove invalid")))
    new_draft = draft.model_copy(update={
        "summary": fixed_summary, "sections": new_sections,
        "change_log": [f"Checked {len(all_checks)} claims: {len(all_checks) - len(unsupported)} supported or "
                       f"partial, {len(unsupported)} unsupported; fixed {fixed_count} citations."]})
    return TechReviewOutput(report=ReviewReport(claims=all_checks, risk_flags=risks, reviewer_questions=questions),
                            draft=new_draft)


def run(draft: Draft, pack: ContextPack, sources: list[SourceRef], prompt_version: int | None = None) -> AgentResult:
    valid_ids = {s.id for s in sources}
    draft = normalise_draft(draft, valid_ids)  # drafts stored before citations were normalised may be grouped
    facts = [{"source_id": s.id, "title": s.title, "text": s.text} for s in sources]
    variables = {"facts_json": json.dumps(facts, indent=1), "draft_json": draft.model_dump_json(indent=1)}
    result = run_agent(SPEC, variables, lambda: mock_review(draft, sources), prompt_version,
                       known_source_ids=valid_ids)
    # Defence in depth: whatever the model says, recheck citations deterministically.
    # (run_agent already split grouped source_ids such as ["S1, S2"], which used to fail this check.)
    out: TechReviewOutput = result.output
    for chk in out.report.claims:
        bad = [c for c in chk.source_ids if c not in valid_ids]
        if bad and chk.verdict == "supported":
            chk.verdict = "partial"
            chk.fix = f"Cited source(s) {', '.join(bad)} do not exist."
    return result
