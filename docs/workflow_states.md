# Workflow states

`content_jobs.status` is the single source of truth for where a job is. Transitions are enforced in `backend/orchestration/states.py`; an illegal move returns `409 INVALID_STATE`.

```mermaid
stateDiagram-v2
  [*] --> INTAKE
  INTAKE --> CONTEXT_PREPARING
  CONTEXT_PREPARING --> CONTEXT_READY
  CONTEXT_PREPARING --> NEEDS_INPUT: blocking gaps
  NEEDS_INPUT --> CONTEXT_PREPARING: inputs added
  CONTEXT_READY --> DRAFTING
  DRAFTING --> TECH_REVIEW
  TECH_REVIEW --> TONE_OPTIMIZING
  TONE_OPTIMIZING --> STRUCTURE_OPTIMIZING
  STRUCTURE_OPTIMIZING --> IN_REVIEW
  IN_REVIEW --> APPROVED: no open unsupported claims
  IN_REVIEW --> REVISION_REQUESTED
  IN_REVIEW --> REJECTED
  REVISION_REQUESTED --> DRAFTING
  REVISION_REQUESTED --> TONE_OPTIMIZING: rerun selected stage
  REVISION_REQUESTED --> IN_REVIEW: human edit
  APPROVED --> PUBLISH_PREPARING
  PUBLISH_PREPARING --> PUBLISH_READY
  PUBLISH_READY --> EXPORTED
  APPROVED --> REVISION_REQUESTED: edit after approval
  DRAFTING --> FAILED
  TECH_REVIEW --> FAILED
  TONE_OPTIMIZING --> FAILED
  STRUCTURE_OPTIMIZING --> FAILED
  FAILED --> TONE_OPTIMIZING: retry resumes at failed stage
```

| Status | Meaning | Who acts next |
|---|---|---|
| `INTAKE` | Job created, inputs attached | Creator starts the workflow |
| `CONTEXT_PREPARING` | Retrieval + Context Reader running | System |
| `CONTEXT_READY` | Context pack built, no blocking gaps | System continues, or creator reviews context |
| `NEEDS_INPUT` | Context Reader found blocking gaps | Creator adds inputs |
| `DRAFTING` / `TECH_REVIEW` / `TONE_OPTIMIZING` / `STRUCTURE_OPTIMIZING` | Agent stage running | System |
| `IN_REVIEW` | Draft scored and waiting for a human | Technical reviewer or documentation lead |
| `REVISION_REQUESTED` | Reviewer asked for changes, or a rerun is queued | System or creator |
| `REJECTED` | Reviewer rejected the draft | Creator revises |
| `APPROVED` | Latest version approved | Publisher |
| `PUBLISH_PREPARING` / `PUBLISH_READY` | Publishing Coordinator prepared metadata | Publisher exports |
| `EXPORTED` | Published as Markdown, CMS JSON or merge request | – |
| `FAILED` | A stage failed after retries; `last_error` explains | Creator retries |

While a stage is running, `last_error.code = "MODEL_BUSY"` is a notice, not a failure: Gemini returned 503 or 429 and the agent is waiting to retry (2s, 4s, 8s, 16s, or the `retryDelay` the server suggests on a 429, plus 1s), then switches to `GEMINI_FALLBACK_MODEL`. Real LLM calls are also spaced to `LLM_REQUESTS_PER_MINUTE` across all stages; a longer wait for a slot shows the same notice. Each retry is audited as `workflow.model_busy`, and the next status change clears the notice. If both models stay busy, the stage moves to `FAILED` with `MODEL_FAILED`.

## Stage outputs

| Stage | Agent | Output schema | New draft version? |
|---|---|---|---|
| `context` | Context Reader | `ContextPack` | No (stored in `context_packs`) |
| `draft` | Documentation Writer | `Draft` | Yes |
| `tech_review` | Technical Reviewer | `TechReviewOutput` (report + draft) | Yes, plus `claim_checks` rows |
| `tone` | Tone Optimizer | `Draft` | Yes |
| `structure` | Structure Optimizer | `Draft` | Yes |
| `quality` | Quality Scorer (no LLM) | `QualityScores` | No (scores on latest draft) |
| `publish_prep` | Publishing Coordinator | `PublishPackage` | No |
