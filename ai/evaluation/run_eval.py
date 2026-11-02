"""Evaluation harness.

Runs every demo scenario in data/sample_inputs/scenarios.yaml through
  (a) a one-shot baseline (a single writer call with writer prompt v1, no review/tone/structure), and
  (b) the full multi-agent workflow (active prompt versions),
then grades both against data/eval/golden/<scenario>.yaml and writes docs/evaluation_report.md.

Usage:  python -m ai.evaluation.run_eval            # uses LLM_PROVIDER from the environment
        python -m ai.evaluation.run_eval --print    # also prints each final draft
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def load_scenarios() -> list[dict]:
    return yaml.safe_load((DATA / "sample_inputs" / "scenarios.yaml").read_text())["scenarios"]


def grade(markdown: str, golden: dict) -> dict:
    low = markdown.lower()
    hits = [all(str(w).lower() in low for w in group) for group in golden["key_facts"]]
    forbidden = [f for f in golden.get("forbidden", []) if f.lower() in low]
    return {"key_fact_recall": round(sum(hits) / len(hits), 3), "missed_facts": [g for g, h in
                                                                                 zip(golden["key_facts"], hits) if not h],
            "forbidden_found": forbidden}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", dest="show")
    args = parser.parse_args()
    os.environ.setdefault("DATABASE_URL", "sqlite://")
    os.environ.setdefault("MOCK_LATENCY_MS", "0")

    from ai.agents.documentation_writer import agent as writer
    from ai.agents.technical_reviewer.agent import mock_review
    from ai.evaluation.quality import score_draft
    from ai.schemas import ContextPack
    from ai.text_utils import draft_to_markdown
    from backend.auth.deps import ensure_demo_users
    from backend.database.models import ContentJob, JobInput
    from backend.database.session import init_db, new_session
    from backend.orchestration import runner
    from ai.retrieval.ingest import ingest_all
    from backend.config import get_settings

    init_db()
    rows = []
    with new_session() as db:
        ensure_demo_users(db)
        ingest_all(db)
        for sc in load_scenarios():
            golden = yaml.safe_load((DATA / "eval" / "golden" / f"{sc['id']}.yaml").read_text())
            job = ContentJob(title=sc["title"], content_type=sc["content_type"], audience=sc["audience"],
                             product_area=sc["product_area"], target_channel=sc["target_channel"],
                             target_length=sc["target_length"], owner_id="demo-creator")
            db.add(job)
            db.flush()
            for i in sc["inputs"]:
                path = DATA / "sample_inputs" / i["file"]
                db.add(JobInput(job_id=job.id, kind=i["kind"], filename=path.name, text=path.read_text()))
            db.commit()
            db.refresh(job)

            # Full multi-agent workflow
            runner.run_workflow(db, job.id)
            final = runner.latest_draft(db, job.id)
            pack_row = runner.latest_pack(db, job.id)
            sources = runner.sources_of(pack_row)
            pack = ContextPack.model_validate(pack_row.pack_json)

            # One-shot baseline: writer v1 only, graded with the same deterministic checks
            one = writer.run(pack, sources, runner.job_dict(job), prompt_version=1).output
            one_claims = mock_review(one, sources).report.claims
            one_scores = score_draft(one, pack, sources, one_claims, job.content_type)
            one_md = draft_to_markdown(one)

            for label, md, q in (("one-shot (writer v1)", one_md, one_scores.model_dump()),
                                 ("multi-agent workflow", final.content_md, final.quality_scores)):
                g = grade(md, golden)
                rows.append({"scenario": sc["id"], "mode": label, **g,
                             "unsupported_claims": q["unsupported_claims"], "claim_support_rate": q["claim_support_rate"],
                             "citation_validity": q["citation_validity"], "structure": q["structure_compliance"],
                             "overall": q["overall"]})
            if args.show:
                print(f"\n{'=' * 80}\n{sc['id']}  ({job.status})\n{'=' * 80}\n{final.content_md}")

    lines = [
        "# Evaluation report", "",
        f"Generated {date.today().isoformat()} with `LLM_PROVIDER={get_settings().llm_provider}` by "
        "`python -m ai.evaluation.run_eval`.", "",
        "Each scenario is run twice on the same inputs: a one-shot baseline (one writer call, prompt v1, no review "
        "stages) and the full multi-agent workflow. Key-fact recall is graded against `data/eval/golden/`.", "",
        "| Scenario | Mode | Key-fact recall | Unsupported claims | Claim support | Citation validity | "
        "Structure | Overall | Forbidden phrases |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['scenario']} | {r['mode']} | {r['key_fact_recall']:.0%} | {r['unsupported_claims']} | "
                     f"{r['claim_support_rate']:.0%} | {r['citation_validity']:.0%} | {r['structure']:.0%} | "
                     f"{r['overall']} | {', '.join(r['forbidden_found']) or 'none'} |")
    missed = [f"- **{r['scenario']}** ({r['mode']}): {r['missed_facts']}" for r in rows if r["missed_facts"]]
    if missed:
        lines += ["", "## Missed key facts", "", *missed]
    lines += ["", "Note: in mock mode the agents are deterministic stand-ins, so these numbers test the pipeline and "
              "the governance checks. Re-run with `LLM_PROVIDER=crewai` and a Gemini key to evaluate real model output."]
    out = ROOT / "docs" / "evaluation_report.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[6:]))
    print(f"\nWrote {out.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
