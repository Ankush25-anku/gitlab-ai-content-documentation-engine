"""Seed a running backend with realistic demo jobs so the dashboard is never empty.

Usage:  python scripts/seed_demo.py --api http://localhost:8000
Requires AUTH_MODE=dev on the backend (uses the demo:<role> tokens).

Creates:
  - the four demo scenarios (release note, docs page, blog, API reference), run to IN_REVIEW
  - the release note approved and exported as Markdown
  - the blog drafted with writer prompt v1, so it carries an unsupported claim to resolve live
  - one job stuck in NEEDS_INPUT (incomplete API notes)
  - one job FAILED at the tone stage (simulated), to demo Retry
"""
import argparse
import time
from pathlib import Path

import httpx
import yaml

DATA = Path(__file__).resolve().parents[1] / "data" / "sample_inputs"


def h(role: str) -> dict:
    return {"Authorization": f"Bearer demo:{role}"}


def wait(c: httpx.Client, job_id: str, timeout: int = 300) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        job = c.get(f"/api/content-jobs/{job_id}", headers=h("creator")).json()
        if job["status"] not in ("INTAKE", "CONTEXT_PREPARING", "DRAFTING", "TECH_REVIEW", "TONE_OPTIMIZING",
                                 "STRUCTURE_OPTIMIZING", "PUBLISH_PREPARING"):
            return job
        time.sleep(1.5)
    raise TimeoutError(job_id)


def create(c: httpx.Client, sc: dict, inputs: list[dict]) -> str:
    body = {k: sc[k] for k in ("title", "content_type", "audience", "product_area", "target_channel", "target_length")}
    body["reviewer_id"] = "demo-reviewer"
    body["inputs"] = inputs
    r = c.post("/api/content-jobs", json=body, headers=h("creator"))
    r.raise_for_status()
    return r.json()["id"]


def scenario_inputs(sc: dict) -> list[dict]:
    return [{"kind": i["kind"], "filename": Path(i["file"]).name, "text": (DATA / i["file"]).read_text()}
            for i in sc["inputs"]]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api", default="http://localhost:8000")
    args = p.parse_args()
    scenarios = {s["id"]: s for s in yaml.safe_load((DATA / "scenarios.yaml").read_text())["scenarios"]}

    with httpx.Client(base_url=args.api, timeout=120) as c:
        ids = {}
        for sid, sc in scenarios.items():
            ids[sid] = create(c, sc, scenario_inputs(sc))
            run = {"job_id": ids[sid]}
            if sid == "blog":
                run["prompt_versions"] = {"draft": 1}  # older prompt: produces a claim to catch in review
            c.post("/api/agent-workflow/run", json=run, headers=h("creator")).raise_for_status()
        jobs = {sid: wait(c, jid) for sid, jid in ids.items()}
        for sid, job in jobs.items():
            print(f"{sid:14s} {job['status']:12s} {job['id']}")

        rn = jobs["release_note"]["latest_draft"]["id"]
        c.post(f"/api/drafts/{rn}/review", json={"action": "approve", "comment": "Checked against MR !4821."},
               headers=h("tech_reviewer")).raise_for_status()
        r = c.post("/api/publish/export", json={"draft_id": rn, "format": "markdown"}, headers=h("publisher"))
        print("release_note export:", r.status_code, r.json().get("file_path"))

        incomplete = {**scenarios["api_reference"], "title": "Runner usage API"}
        jid = create(c, incomplete, [{"kind": "notes", "filename": "runner-usage-notes.md",
                                      "text": (DATA / "edge_cases" / "incomplete_api_change.md").read_text()}])
        c.post("/api/agent-workflow/run", json={"job_id": jid}, headers=h("creator"))
        print("needs input   ", wait(c, jid)["status"], jid)

        failing = {**scenarios["docs_page"], "title": "Configure cache fallback keys"}
        jid = create(c, failing, scenario_inputs(scenarios["docs_page"]))
        c.post("/api/agent-workflow/run", json={"job_id": jid, "simulate_failure": "tone"}, headers=h("creator"))
        print("failed        ", wait(c, jid)["status"], jid)


if __name__ == "__main__":
    main()
