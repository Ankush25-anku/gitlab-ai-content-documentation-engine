-- Supabase / Postgres schema for the AI Content & Documentation Engine.
-- Run in the Supabase SQL editor (or psql) in order: 001, 002, 003.
-- Local development uses SQLite and creates the same tables from backend/database/models.py.

create extension if not exists vector;

create table if not exists profiles (
  id          text primary key,              -- = auth.users.id (as text)
  email       text unique not null,
  name        text not null,
  role        text not null check (role in ('creator','tech_reviewer','doc_lead','publisher','admin')),
  created_at  timestamptz not null default now()
);

create table if not exists content_jobs (
  id                  text primary key,
  title               text not null,
  content_type        text not null check (content_type in
                        ('release_note','docs_page','blog','api_reference','onboarding_guide')),
  audience            text not null,
  product_area        text not null,
  target_channel      text not null,
  target_length       integer not null default 600,
  owner_id            text not null references profiles(id),
  reviewer_id         text references profiles(id),
  deadline            text,
  publication_format  text not null default 'markdown',
  status              text not null default 'INTAKE',
  current_stage       text,
  last_error          jsonb,
  excluded_chunk_ids  jsonb not null default '[]',
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
create index if not exists content_jobs_status_idx on content_jobs(status);
create index if not exists content_jobs_owner_idx on content_jobs(owner_id);

create table if not exists job_inputs (
  id          text primary key,
  job_id      text not null references content_jobs(id) on delete cascade,
  kind        text not null,
  filename    text not null,
  text        text not null,
  redacted    boolean not null default false,
  redactions  jsonb not null default '[]',
  created_at  timestamptz not null default now()
);

create table if not exists context_packs (
  id              text primary key,
  job_id          text not null references content_jobs(id) on delete cascade,
  version         integer not null default 1,
  retrieval_json  jsonb not null,
  pack_json       jsonb,
  created_at      timestamptz not null default now()
);

create table if not exists prompt_versions (
  id          text primary key,                 -- "<agent>@v<n>"
  agent       text not null,
  version     integer not null,
  file_hash   text not null,
  body        text not null,
  created_at  timestamptz not null default now()
);

create table if not exists agent_runs (
  id                 text primary key,
  job_id             text not null references content_jobs(id) on delete cascade,
  stage              text not null,
  attempt            integer not null default 1,
  prompt_version_id  text references prompt_versions(id),
  model              text not null,
  input_hash         text not null default '',
  output_json        jsonb,
  status             text not null default 'running',
  error              text,
  latency_ms         integer not null default 0,
  tokens_in          integer not null default 0,
  tokens_out         integer not null default 0,
  started_at         timestamptz not null default now(),
  finished_at        timestamptz
);
create index if not exists agent_runs_job_idx on agent_runs(job_id);

create table if not exists drafts (
  id              text primary key,
  job_id          text not null references content_jobs(id) on delete cascade,
  version         integer not null,
  parent_version  integer,
  stage           text not null,
  content_md      text not null,
  draft_json      jsonb not null,
  created_by      text not null,
  quality_scores  jsonb,
  review_state    text not null default 'pending',
  created_at      timestamptz not null default now(),
  unique (job_id, version)
);

create table if not exists claim_checks (
  id               text primary key,
  draft_id         text not null references drafts(id) on delete cascade,
  claim            text not null,
  verdict          text not null check (verdict in ('supported','partial','unsupported')),
  source_ids       jsonb not null default '[]',
  fix              text,
  resolved         boolean not null default false,
  resolved_by      text,
  resolution_note  text
);

create table if not exists review_actions (
  id              text primary key,
  draft_id        text not null references drafts(id) on delete cascade,
  reviewer_id     text not null references profiles(id),
  action          text not null,
  comment         text,
  issue_category  text,
  created_at      timestamptz not null default now()
);

create table if not exists kb_documents (
  id            text primary key,
  title         text not null,
  source_url    text,
  product_area  text not null default 'general',
  content_type  text not null default 'docs_page',
  kind          text not null default 'doc',
  owner         text,
  updated_at    text not null
);

create table if not exists kb_chunks (
  id           text primary key,                -- <slug>#<anchor>#<n>
  document_id  text not null references kb_documents(id) on delete cascade,
  heading      text not null,
  text         text not null,
  embedding    vector(768) not null,
  meta         jsonb not null default '{}'
);
create index if not exists kb_chunks_embedding_idx
  on kb_chunks using hnsw (embedding vector_cosine_ops);

create table if not exists exports (
  id           text primary key,
  draft_id     text not null references drafts(id),
  format       text not null,
  target       text,
  mr_url       text,
  status       text not null,
  exported_by  text not null,
  payload      jsonb,
  created_at   timestamptz not null default now()
);

create table if not exists audit_logs (
  id          text primary key,
  actor_id    text,
  job_id      text,
  event       text not null,
  details     jsonb not null default '{}',
  created_at  timestamptz not null default now()
);
create index if not exists audit_logs_job_idx on audit_logs(job_id);

create table if not exists metric_snapshots (
  id          text primary key,
  name        text not null,
  value       double precision not null,
  created_at  timestamptz not null default now()
);
