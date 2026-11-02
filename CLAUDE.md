# CLAUDE.md

Context for Claude (and new team members) working in this repository.

## What this is

A capstone project: the **GitLab AI Content & Documentation Engine**. It turns technical inputs (merge request descriptions, diffs, OpenAPI specs, release notes) into source-grounded release notes, docs pages, blogs, API references and onboarding guides through a six-agent CrewAI pipeline, with a mandatory human approval gate before export.

Core principle: **a governed workflow, not a text generator**. Never weaken these guarantees:
- every factual sentence cites a source as `[S#]`; missing facts become `[NEEDS SOURCE: ...]`
- unsupported claims block approval until removed or overridden with a written reason
- `POST /api/publish/export` refuses anything but the latest approved draft
- secrets are redacted from inputs before storage or any model call
- every status change, model call, review and export is written to `audit_logs`

## Layout

- `backend/` FastAPI: `api/` routes, `auth/deps.py` roles, `orchestration/runner.py` stage runner, `orchestration/states.py` job state machine, `database/models.py` + `database/migrations/*.sql` (Supabase), `publishing/exporters.py`, `services/` (errors, audit, redaction)
- `ai/` agents and AI: `agents/<agent>/agent.py` (six agents, each with a deterministic mock), `agents/base.py` (mock vs CrewAI runtime), `prompts/<agent>/v<N>.yaml` (versioned prompts), `prompts/content_types/`, `prompts/tone/`, `schemas/content.py` (Pydantic outputs), `retrieval/` (chunking, embeddings, pgvector search, context pack), `evaluation/` (quality scorer, eval harness)
- `frontend/` Next.js 16 + Tailwind 4: `app/` routes, `components/`, `content-editor/`, `review-panel/`, `lib/api.ts`, design tokens in `styles/globals.css`
- `data/` knowledge base docs, style guide, glossary, templates, demo inputs, golden eval files
- `tests/` pytest suites (functional, ai_output, security, edge_cases); `docs/`; `deployment/`; `scripts/`

## Commands (run from the repo root, virtual environment active)

```bash
uvicorn backend.main:app --reload          # API on :8000, docs at /docs
cd frontend && npm run dev                  # UI on :3000
pytest -q                                   # always mock mode, in-memory SQLite
python -m ai.evaluation.run_eval            # writes docs/evaluation_report.md
python scripts/seed_demo.py [--api URL]     # demo jobs (needs AUTH_MODE=dev)
python -m ai.retrieval.ingest --reset       # re-embed the knowledge base
cd frontend && npm run typecheck && npm run build
ruff check backend ai tests scripts --select E,F --ignore E501
```

## Configuration

- Backend settings: `backend/config.py`, read from `.env` (copy of `.env.example`). Frontend: `frontend/.env.local`.
- `LLM_PROVIDER=mock` (default, offline) or `crewai` (real Gemini via CrewAI; needs `GEMINI_API_KEY` and `pip install -r requirements-ai.txt`).
- `AUTH_MODE=dev` uses `Authorization: Bearer demo:<role>`; `supabase` verifies Supabase JWTs. Production (`APP_ENV=production`) refuses dev auth; the capstone deployment uses `APP_ENV=staging` + `AUTH_MODE=dev` so evaluators can use demo users.
- SQLite locally; Supabase Postgres + pgvector when `DATABASE_URL` is `postgresql+psycopg://...` (run the SQL migrations first).

## Rules for changes

1. **Never print, log, commit or echo secrets.** Keys live only in `.env`, `frontend/.env.local`, or hosting dashboards. Do not read `.env` aloud in responses.
2. **Prompts are versioned.** To change an agent's prompt, add a new `v<N+1>.yaml`; never edit an existing version (eval comparisons and `agent_runs.prompt_version_id` depend on them).
3. **Every agent keeps a deterministic mock** so tests and CI run without keys. Agent outputs must validate against `ai/schemas/content.py`.
4. **Tests run in mock mode** (`tests/conftest.py`). New behaviour gets a test. Before finishing a task run `pytest -q`, and `npm run build` if the frontend changed.
5. API errors use `AppError(code, message, job_id)` from `backend/services/errors.py`; add new codes to `ERROR_STATUS` and `docs/api_documentation.md`.
6. Job status changes go through `runner.set_status` (validated transitions + audit). Update `docs/workflow_states.md` if you change the state machine.
7. Frontend: reuse tokens in `styles/globals.css` and components in `components/ui.tsx`; keep it accessible (labels, focus states) and responsive.
8. Sample content in `data/` is written for this project in GitLab's documentation style; do not copy text verbatim from docs.gitlab.com or other sources.
9. Keep changes small and explain them; the team must be able to defend every change in their viva.
