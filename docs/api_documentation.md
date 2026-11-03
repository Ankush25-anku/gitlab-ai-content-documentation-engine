# API documentation

Base URL: `http://localhost:8000` locally. Interactive OpenAPI docs: `/docs`.

All endpoints except `/health` need `Authorization: Bearer <token>`. With `AUTH_MODE=dev` the token is `demo:<role>` (`creator`, `tech_reviewer`, `doc_lead`, `publisher`, `admin`). With `AUTH_MODE=supabase` it is the Supabase access token.

Every error has the same shape:

```json
{"error": {"code": "UNSUPPORTED_CLAIMS", "message": "1 unsupported claim(s) must be removed or overridden before approval.", "job_id": "…", "retryable": false, "details": {"claim_ids": ["…"]}}}
```

| Code | HTTP | When |
|---|---|---|
| `INPUT_INVALID` | 422 | Validation failure, empty or oversized input, unsupported file type, unknown prompt version |
| `UNAUTHORIZED` | 401 | Missing or invalid token |
| `FORBIDDEN` | 403 | Role not allowed |
| `NOT_APPROVED` | 403 | Export of a draft that is not the latest approved version |
| `NOT_FOUND` | 404 | Job, draft, claim or version not found (or not visible to you) |
| `INVALID_STATE` | 409 | Action not allowed in the job's current status |
| `CONTEXT_INSUFFICIENT` | 409 | Blocking gaps in the context pack |
| `UNSUPPORTED_CLAIMS` | 409 | Approval with unresolved unsupported claims |
| `MODEL_FAILED` | 502 | LLM failed after retries (retryable). If the API rejected the request itself (400/401/403/404, e.g. an unsupported schema or bad key), the stage fails at once without retries and the job's `last_error.retryable` is `false` |
| `EXPORT_FAILED` | 502 | GitLab API error or GitLab not configured (retryable) |
| `RETRIEVAL_FAILED` | – | Non-fatal: recorded as a context warning, drafting continues |

## Endpoints

| Method | Path | Roles | Description |
|---|---|---|---|
| POST | `/api/content-jobs` | creator, doc_lead | Create a job, optionally with inline inputs |
| GET | `/api/content-jobs` | any (creators see own) | List jobs, `?status=` filter |
| GET | `/api/content-jobs/{job_id}` | owner, staff | Job, inputs, context pack, drafts, latest draft with claims, agent runs |
| POST | `/api/content-jobs/{job_id}/inputs` | owner, doc_lead | Multipart `files[]` and/or form `text`, `kind`, `filename`. Redacts secrets |
| DELETE | `/api/content-jobs/{job_id}/inputs/{input_id}` | owner, doc_lead | Remove an input |
| POST | `/api/context-pack` | owner, doc_lead | Retrieval + Context Reader. Body `{job_id, excluded_chunk_ids?}` |
| POST | `/api/agent-workflow/run` | owner, doc_lead | Start or resume. Body `{job_id, from_stage?, prompt_versions?, simulate_failure?}`. Returns 202 |
| GET | `/api/content-jobs/{job_id}/runs` | owner, staff | Agent runs with outputs |
| GET | `/api/content-jobs/{job_id}/events` | owner, staff | Server-Sent Events: `job` snapshots, then `done` |
| GET | `/api/drafts/{draft_id}` | owner, staff | Draft, claims, review actions |
| GET | `/api/drafts/{draft_id}/versions?compare=a,b` | owner, staff | Version list and unified diff |
| POST | `/api/drafts/{draft_id}/review` | reviewers (owner may `edit`/`comment`) | `action`: approve, reject, edit, request_revision, comment, resolve_claim |
| POST | `/api/drafts/{draft_id}/refine` | owner, reviewers | Rerun selected stages: `{stages: ["tone"], instructions?, prompt_versions?}`. Returns 202 |
| POST | `/api/publish/prepare` | publisher, doc_lead, tech_reviewer | Run the Publishing Coordinator; returns package + Markdown preview. `409 INVALID_STATE` while a prepare is already running for the job |
| POST | `/api/publish/export` | publisher, doc_lead | `{draft_id, format: markdown \| cms_json \| gitlab_mr}` |
| GET | `/api/publish/exports` | publisher, doc_lead, tech_reviewer | Recent exports |
| GET | `/api/metrics` | any | Throughput, cycle times, rework, latency, quality, prompt comparison |
| POST | `/api/kb/ingest?reset=` | admin | Re-ingest `data/` into the knowledge base |
| GET | `/api/kb/documents` | any | Knowledge base documents with chunk counts |
| GET | `/api/kb/search?q=&product_area=&k=` | any | Retrieval playground |
| GET | `/api/library` | any | Templates, tone rules, glossary |
| GET | `/api/prompts` | any | All prompt versions with hashes |
| GET | `/api/audit-logs?job_id=` | doc_lead, tech_reviewer | Audit trail |
| GET | `/api/me`, `/api/users` | any | Session info and user list |
| GET | `/health` | public | Liveness, provider and auth mode |

## Walkthrough with curl

```bash
API=http://localhost:8000
C="Authorization: Bearer demo:creator"; R="Authorization: Bearer demo:tech_reviewer"; P="Authorization: Bearer demo:publisher"

JOB=$(curl -s -X POST $API/api/content-jobs -H "$C" -H 'Content-Type: application/json' -d '{
  "title": "Pipeline cache statistics API", "content_type": "api_reference",
  "audience": "Developers who automate GitLab", "product_area": "Verify", "target_channel": "api_reference"}' | jq -r .id)

curl -s -X POST $API/api/content-jobs/$JOB/inputs -H "$C" \
  -F files=@data/sample_inputs/pipeline_cache_analytics/cache_stats.diff \
  -F files=@data/sample_inputs/pipeline_cache_analytics/openapi_cache_stats.yaml

curl -s -X POST $API/api/agent-workflow/run -H "$C" -H 'Content-Type: application/json' -d "{\"job_id\": \"$JOB\"}"
sleep 8
DRAFT=$(curl -s $API/api/content-jobs/$JOB -H "$C" | jq -r .latest_draft.id)

curl -s -X POST $API/api/drafts/$DRAFT/refine -H "$C" -H 'Content-Type: application/json' -d '{"stages": ["tone"], "instructions": "more concise"}'
sleep 3
DRAFT=$(curl -s $API/api/content-jobs/$JOB -H "$C" | jq -r .latest_draft.id)

curl -s -X POST $API/api/drafts/$DRAFT/review -H "$R" -H 'Content-Type: application/json' -d '{"action": "approve", "comment": "Checked against the diff"}'
curl -s -X POST $API/api/publish/export -H "$P" -H 'Content-Type: application/json' -d "{\"draft_id\": \"$DRAFT\", \"format\": \"markdown\"}"
```
