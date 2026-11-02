# Demo script (about 9 minutes)

Record on the **deployed URL**, browser zoom about 110%, 1080p. Before recording, run `python scripts/seed_demo.py --api <backend-url>` so the dashboard has data, and open `/health` once so the backend is awake. Each member presents the part they built.

| Time | Presenter | Screen | What to show and say |
|---|---|---|---|
| 0:00–1:00 | M1 | Slide, then login page | GitLab ships changes faster than writers can document them. The engine turns technical change into reviewed content; nothing is published without approval. Show the architecture diagram. |
| 1:00–2:00 | M2 | New request | Sign in as Priya (creator). Create an **API reference** "Pipeline cache statistics API". Upload `cache_stats.diff`, `openapi_cache_stats.yaml`, `mr_description.md`. Start drafting. |
| 2:00–3:15 | M5 | Workflow tab | Stages light up live (server-sent events). Open the Documentation Writer output JSON; point at prompt version, model, latency, tokens. |
| 3:15–4:00 | M6 | Context tab | Facts with source ids, retrieved docs with match scores, the **stale** legacy page flagged; untick it and rebuild. Show the Style and knowledge page: templates, glossary, retrieval search. |
| 4:00–5:15 | M3 | Draft tab on the seeded blog job | Click a citation to see the exact source text. Quality badges. One sentence is highlighted red: written by writer prompt v1, caught by the Technical Reviewer. Approve is disabled. |
| 5:15–6:00 | M3 / M4 | Draft tab | Sign in as Arjun (reviewer). Try Approve on the blog job via the API to show `409 UNSUPPORTED_CLAIMS`, then **Remove from draft**, then Approve. Rerun **Tone only** with "more concise" on another job, compare versions (diff). |
| 6:00–7:00 | M7 | Publish tab | Sign in as Rahul (publisher). Prepare for publishing; show file path, labels, MR text. Export as **merge request** and open the real MR on gitlab.com. Show that exporting an unapproved draft returns `403 NOT_APPROVED`. |
| 7:00–7:45 | M4 / M7 | Failed job, audit trail | Open the seeded failed job: error card, earlier outputs kept, **Retry** resumes at the tone stage. Show the audit trail and that secrets in `with_secrets.md` were redacted on upload. |
| 7:45–8:30 | M1 | Pipeline health | Cycle times, rework, quality, writer v1 vs v2 table. Show `docs/evaluation_report.md` (one-shot vs multi-agent). |
| 8:30–9:00 | All | Slide | Team contribution table. One line each on what you owned. |

## Backup plan

If the model quota runs out during recording, set `LLM_PROVIDER=mock` on the backend and redeploy: the whole flow, including governance, still works. Say so on camera; it shows the system degrades safely.
