"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import ContextReview from "@/components/ContextReview";
import PublishPanel from "@/components/PublishPanel";
import StageRail from "@/components/StageRail";
import WorkflowMonitor from "@/components/WorkflowMonitor";
import { ErrorNote, StatusPill } from "@/components/ui";
import DraftEditor from "@/content-editor/DraftEditor";
import { TYPE_LABEL, api, streamEvents } from "@/lib/api";
import type { JobDetail } from "@/lib/types";

const TABS = [
  { id: "context", label: "Context" },
  { id: "workflow", label: "Workflow" },
  { id: "draft", label: "Draft and review" },
  { id: "publish", label: "Publish" },
];
const RUNNING = ["CONTEXT_PREPARING", "DRAFTING", "TECH_REVIEW", "TONE_OPTIMIZING", "STRUCTURE_OPTIMIZING", "PUBLISH_PREPARING"];

function defaultTab(job: JobDetail) {
  if (job.status === "NEEDS_INPUT") return "context";
  if (RUNNING.includes(job.status) || job.status === "FAILED") return "workflow";
  if (["APPROVED", "PUBLISH_READY", "EXPORTED"].includes(job.status)) return "publish";
  return "draft";
}

function JobPage() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tab = search.get("tab") ?? (job ? defaultTab(job) : "draft");
  const streaming = useRef<AbortController | null>(null);

  const load = useCallback(() => api<JobDetail>(`/api/content-jobs/${id}`).then(setJob).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  // Live updates while agents run: stream status changes, reload the full job when it changes.
  const watch = useCallback(() => {
    streaming.current?.abort();
    const ctrl = new AbortController();
    streaming.current = ctrl;
    streamEvents(`/api/content-jobs/${id}/events`, () => { load(); }, ctrl.signal).catch(() => {}).finally(() => load());
  }, [id, load]);
  useEffect(() => { if (job && RUNNING.includes(job.status)) watch(); }, [job?.status, watch]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => streaming.current?.abort(), []);

  const refresh = () => { load().then(() => setTimeout(load, 400)); watch(); };

  if (error) return <ErrorNote error={error} />;
  if (!job) return <p className="text-ink-soft">Loading job…</p>;

  return (
    <div className="max-w-[1280px]">
      <Link href="/jobs" className="text-sm text-ink-soft hover:text-ink">Content jobs</Link>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold leading-tight">{job.title}</h1>
          <p className="mt-1 text-sm text-ink-soft">
            {TYPE_LABEL[job.content_type]} for {job.audience.charAt(0).toLowerCase() + job.audience.slice(1)} · {job.product_area}
            {job.owner && ` · requested by ${job.owner.name}`}{job.deadline && ` · due ${job.deadline}`}
          </p>
        </div>
        <StatusPill status={job.status} />
      </div>

      {tab !== "workflow" && (
        <div className="mt-5 rounded-lg border border-line bg-sheet px-2 py-4">
          <StageRail status={job.status} current={job.current_stage} runs={job.runs}
            onSelect={() => router.replace(`/jobs/${job.id}?tab=workflow`, { scroll: false })} />
        </div>
      )}

      <nav className="mt-6 flex gap-1 border-b border-line" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id}
            onClick={() => router.replace(`/jobs/${job.id}?tab=${t.id}`, { scroll: false })}
            className={`-mb-px border-b-2 px-4 py-2 text-sm ${tab === t.id ? "border-accent font-medium text-accent" : "border-transparent text-ink-soft hover:text-ink"}`}>
            {t.label}
          </button>
        ))}
      </nav>

      <div className="mt-6">
        {tab === "context" && <ContextReview job={job} onChange={refresh} />}
        {tab === "workflow" && <WorkflowMonitor job={job} onChange={refresh} />}
        {tab === "draft" && <DraftEditor job={job} onChange={refresh} />}
        {tab === "publish" && <PublishPanel job={job} onChange={refresh} />}
      </div>
    </div>
  );
}

export default function Page() {
  return <Suspense fallback={<p className="text-ink-soft">Loading job…</p>}><JobPage /></Suspense>;
}
