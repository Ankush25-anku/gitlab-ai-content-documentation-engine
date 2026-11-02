-- Row-level security and an append-only audit log.
-- The FastAPI backend connects with the service role (bypasses RLS) and enforces roles in code.
-- RLS protects the tables from any direct use of the public anon key.

alter table profiles        enable row level security;
alter table content_jobs    enable row level security;
alter table job_inputs      enable row level security;
alter table context_packs   enable row level security;
alter table agent_runs      enable row level security;
alter table drafts          enable row level security;
alter table claim_checks    enable row level security;
alter table review_actions  enable row level security;
alter table exports         enable row level security;
alter table audit_logs      enable row level security;
alter table kb_documents    enable row level security;
alter table kb_chunks       enable row level security;
alter table prompt_versions enable row level security;

-- Users can read their own profile.
create policy "own profile" on profiles for select using (auth.uid()::text = id);

-- Creators see their own jobs; reviewers, leads, publishers and admins see all jobs.
create policy "jobs visible to owner or staff" on content_jobs for select using (
  owner_id = auth.uid()::text
  or exists (select 1 from profiles p where p.id = auth.uid()::text
             and p.role in ('tech_reviewer','doc_lead','publisher','admin'))
);

-- Knowledge base is readable by any signed-in user.
create policy "kb readable" on kb_documents for select using (auth.role() = 'authenticated');
create policy "kb chunks readable" on kb_chunks for select using (auth.role() = 'authenticated');

-- Audit log: no updates or deletes, ever.
create or replace function forbid_audit_change() returns trigger language plpgsql as $$
begin
  raise exception 'audit_logs is append-only';
end; $$;

drop trigger if exists audit_logs_no_update on audit_logs;
create trigger audit_logs_no_update before update or delete on audit_logs
  for each row execute function forbid_audit_change();
