"""Quality Scorer: deterministic checks that run after the Structure Optimizer (no LLM involved).

These scores are shown as badges in the Draft Editor and aggregated on the dashboard.
"""
from ai.prompts.loader import content_type_template
from ai.schemas import ClaimCheck, ContextPack, Draft, QualityScores, SourceRef
from ai.text_utils import (CITATION_RE, NEEDS_SOURCE_RE, citations, draft_to_markdown, split_sentences,
                           strip_citations, word_count)


def score_draft(draft: Draft, pack: ContextPack | None, sources: list[SourceRef],
                claims: list[ClaimCheck], content_type: str) -> QualityScores:
    md = draft_to_markdown(draft)
    valid_ids = {s.id for s in sources}
    cited = citations(md)
    invalid = sorted({c for c in cited if c not in valid_ids})
    citation_validity = 1.0 if not cited else sum(c in valid_ids for c in cited) / len(cited)

    # Coverage: share of input-sourced facts whose source is cited somewhere in the draft.
    input_ids = {s.id for s in sources if s.origin == "input"}
    facts = [f for f in (pack.facts if pack else []) if f.source_id in input_ids]
    cited_set = set(cited)
    coverage = 1.0 if not facts else sum(f.source_id in cited_set for f in facts) / len(facts)

    support = 1.0 if not claims else sum(c.verdict == "supported" for c in claims) / len(claims)
    unsupported = sum(c.verdict == "unsupported" for c in claims)

    required = content_type_template(content_type)["required_headings"]
    present = {s.heading.lower() for s in draft.sections}
    missing = [h for h in required if h.lower() not in present]
    structure = (len(required) - len(missing)) / len(required)

    sentences = [CITATION_RE.sub("", s) for s in split_sentences(md) if not s.startswith(("|", "#"))]
    avg_words = sum(len(s.split()) for s in sentences) / max(1, len(sentences))
    needs = len(NEEDS_SOURCE_RE.findall(md))

    readability = 1.0 if avg_words <= 20 else max(0.0, 1 - (avg_words - 20) / 20)
    overall = 100 * (0.25 * support + 0.20 * citation_validity + 0.20 * coverage + 0.15 * structure
                     + 0.10 * readability + 0.10 * (1.0 if unsupported == 0 else 0.0))
    overall -= min(15, 3 * needs)
    return QualityScores(
        source_coverage=round(coverage, 3), citation_validity=round(citation_validity, 3),
        invalid_citations=invalid, claim_support_rate=round(support, 3), unsupported_claims=unsupported,
        needs_source_markers=needs, structure_compliance=round(structure, 3), missing_headings=missing,
        readability_avg_sentence_words=round(avg_words, 1), word_count=word_count(md),
        overall=round(max(0.0, overall), 1),
    )


def strip_internal_markers(md: str) -> str:
    """Remove citation markers (single or grouped) for publication while keeping the text."""
    return strip_citations(md)
