"""Grouped citations from real models ("[S1, S2]") must behave exactly like canonical ones ("[S1] [S2]")."""
import pytest

from ai.agents.technical_reviewer import agent as technical_reviewer
from ai.evaluation.quality import score_draft, strip_internal_markers
from ai.prompts.loader import content_type_template
from ai.schemas import ClaimCheck, ContextPack, Draft, ReviewReport, Section, SourceFact, SourceRef, TechReviewOutput
from ai.text_utils import (citations, draft_to_markdown, markdown_to_draft, normalise_citations, normalise_output,
                           normalise_source_ids, plain_text)


@pytest.mark.parametrize("grouped, canonical", [
    ("Counts per key [S1, S2].", "Counts per key [S1] [S2]."),
    ("Counts per key [S1,S2].", "Counts per key [S1] [S2]."),
    ("Counts per key [S1; S2].", "Counts per key [S1] [S2]."),
    ("Counts per key [S1 and S2].", "Counts per key [S1] [S2]."),
    ("Counts per key [S1, S2, and S3].", "Counts per key [S1] [S2] [S3]."),
    ("Counts per key [ S4 ].", "Counts per key [S4]."),
    ("Counts per key (S1).", "Counts per key [S1]."),
    ("Counts per key (S1, S2).", "Counts per key [S1] [S2]."),
    ("Counts per key [S2, S2].", "Counts per key [S2]."),
    ("Counts per key [S1] [S2].", "Counts per key [S1] [S2]."),  # already canonical: unchanged
])
def test_grouped_forms_become_one_id_per_bracket(grouped, canonical):
    assert normalise_citations(grouped) == canonical
    assert normalise_citations(canonical) == canonical  # idempotent


def test_code_and_unknown_parenthesised_ids_are_left_alone():
    text = "Run `grep '[S1, S2]' log` then:\n```\nlabel [S3, S4]\n```\nStore files in object storage (S3) [S1, S2]."
    out = normalise_citations(text, known_ids={"S1", "S2"})
    assert "`grep '[S1, S2]' log`" in out and "label [S3, S4]" in out  # code untouched
    assert "object storage (S3) [S1] [S2]." in out  # S3 is not a source of this job: prose, not a citation


def test_source_id_lists_are_split():
    assert normalise_source_ids(["S1, S2", "[S3]", "S2", "S4 and S5"]) == ["S1", "S2", "S3", "S4", "S5"]


def test_helpers_read_grouped_citations_without_normalising():
    sentence = "The endpoint returns hit and miss counts for each key [S1, S2] [S3 and S4]."
    assert citations(sentence) == ["S1", "S2", "S3", "S4"]
    assert plain_text(sentence) == "The endpoint returns hit and miss counts for each key."
    assert strip_internal_markers(sentence) == plain_text(sentence)


def test_human_edits_are_stored_canonical():
    base = Draft(title="T", summary="S", sections=[])
    edited = markdown_to_draft("# T\n\nS\n\n## Overview\n\nCounts per key [S1, S2]. Object storage (S3) works.\n", base)
    assert edited.sections[0].body_markdown == "Counts per key [S1] [S2]. Object storage (S3) works."
    assert edited.sections[0].source_ids == ["S1", "S2"]


# ---------------------------------------------------------------- scoring a grouped draft
FACT_1 = "The cache statistics endpoint returns hit and miss counts for each cache key."
FACT_2 = "Statistics are kept for thirty days after each pipeline finishes."
FACT_3 = "Request statistics with a project access token that has the read_api scope."
SOURCES = [SourceRef(id=f"S{i}", chunk_id=f"input:spec.yaml#{i}", origin="input", title="Spec", text=t)
           for i, t in enumerate([FACT_1, FACT_2, FACT_3], start=1)]
PACK = ContextPack(summary="s", audience="Developers", content_type="docs_page",
                   facts=[SourceFact(id=f"F{i}", source_id=f"S{i}", text=s.text) for i, s in enumerate(SOURCES, 1)])


def _draft(cite_1: str, cite_2: str, cite_3: str) -> Draft:
    headings = content_type_template("docs_page")["required_headings"]
    bodies = {0: f"{FACT_1[:-1]} {cite_1}. {FACT_2[:-1]} {cite_2}.", 1: f"{FACT_3[:-1]} {cite_3}."}
    return Draft(title="Cache statistics", summary="Cache statistics for pipelines.",
                 sections=[Section(heading=h, body_markdown=bodies.get(i, "[NEEDS SOURCE: details]"))
                           for i, h in enumerate(headings)])


GROUPED = _draft("[S1, S2]", "[S2;S1]", "(S3)")
CANONICAL = _draft("[S1] [S2]", "[S2] [S1]", "[S3]")


@pytest.fixture()
def mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("MOCK_LATENCY_MS", "0")
    from backend.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_grouped_draft_scores_the_same_as_canonical(mock_llm):
    grouped = technical_reviewer.run(GROUPED, PACK, SOURCES).output
    canonical = technical_reviewer.run(CANONICAL, PACK, SOURCES).output
    assert draft_to_markdown(grouped.draft) == draft_to_markdown(canonical.draft)  # stored canonical
    assert [c.verdict for c in grouped.report.claims] == ["supported"] * 3
    assert grouped.report.claims == canonical.report.claims

    scores = score_draft(grouped.draft, PACK, SOURCES, grouped.report.claims, "docs_page")
    assert scores == score_draft(canonical.draft, PACK, SOURCES, canonical.report.claims, "docs_page")
    assert (scores.claim_support_rate, scores.source_coverage, scores.citation_validity) == (1.0, 1.0, 1.0)


def test_scorer_and_reviewer_tolerate_grouped_drafts_that_were_never_normalised():
    """Defence in depth: drafts stored before this fix still score correctly."""
    raw = Draft(title="T", summary="S", sections=[Section(heading="Overview",
                                                          body_markdown=f"{FACT_1[:-1]} [S1, S2]. {FACT_2[:-1]} [S2 and S1].")])
    claims = technical_reviewer.mock_review(raw, SOURCES).report.claims
    assert [c.verdict for c in claims] == ["supported", "supported"]
    scores = score_draft(raw, PACK, SOURCES, claims, "docs_page")
    assert scores.citation_validity == 1.0 and scores.invalid_citations == []
    assert scores.source_coverage == pytest.approx(2 / 3, abs=0.001)  # S1 and S2 of three facts


def test_grouped_claim_source_ids_are_not_downgraded_to_partial(mock_llm, monkeypatch):
    """Real Gemini returned source_ids=["S1, S2"]; the reviewer's recheck used to mark those claims partial."""
    report = ReviewReport(claims=[ClaimCheck(claim=FACT_1, verdict="supported", source_ids=["S1, S2"])])
    monkeypatch.setattr(technical_reviewer, "mock_review", lambda d, s: TechReviewOutput(report=report, draft=d))
    claim = technical_reviewer.run(CANONICAL, PACK, SOURCES).output.report.claims[0]
    assert claim.verdict == "supported" and claim.source_ids == ["S1", "S2"]


def test_every_agent_output_is_normalised(mock_llm):
    from ai.agents.base import AgentSpec, run_agent
    spec = AgentSpec(name="tone_optimizer", stage="tone", output_model=Draft)
    variables = {"target_channel": "docs", "tone_rules": "", "glossary_terms": "", "draft_json": "{}", "instructions": ""}
    result = run_agent(spec, variables, mock=lambda: GROUPED, known_source_ids={"S1", "S2", "S3"})
    assert draft_to_markdown(result.output) == draft_to_markdown(CANONICAL)
    assert normalise_output(result.output) == result.output  # nothing left to normalise
