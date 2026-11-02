"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useMe } from "@/components/Shell";
import { ErrorNote, StatusPill } from "@/components/ui";
import { TYPE_LABEL, api } from "@/lib/api";
import type { JobSummary } from "@/lib/types";

const FILTERS: { label: string; match: (s: string) => boolean }[] = [
  { label: "All", match: () => true },
  { label: "Needs a reviewer", match: (s) => s === "IN_REVIEW" },
  { label: "Needs input or failed", match: (s) => ["NEEDS_INPUT", "FAILED", "REVISION_REQUESTED", "REJECTED"].includes(s) },
  { label: "Ready to publish", match: (s) => ["APPROVED", "PUBLISH_READY"].includes(s) },
  { label: "Published", match: (s) => s === "EXPORTED" },
];

function ago(iso: string) {
  const mins = Math.round((Date.now() - new Date(iso + (iso.endsWith("Z") || iso.includes("+") ? "" : "Z")).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 1440) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} d ago`;
}

export default function Jobs() {
  const me = useMe();
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState(0);

  useEffect(() => { api<JobSummary[]>("/api/content-jobs").then(setJobs).catch((e) => setError(e.message)); }, []);
  const shown = useMemo(() => (jobs ?? []).filter((j) => FILTERS[filter].match(j.status)), [jobs, filter]);

  return (
    <div className="max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Content jobs</h1>
          <p className="text-ink-soft">{me?.role === "creator" ? "Your requests and where each one stands." : "Every request in the pipeline."}</p>
        </div>
        {(me?.role === "creator" || me?.role === "doc_lead" || me?.role === "admin") &&
          <Link href="/jobs/new" className="rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-white">New request</Link>}
      </div>

      <div className="mt-6 flex flex-wrap gap-2" role="tablist">
        {FILTERS.map((f, i) => (
          <button key={f.label} role="tab" aria-selected={filter === i} onClick={() => setFilter(i)}
            className={`rounded-full border px-3 py-1 text-sm ${filter === i ? "border-accent bg-accent-soft text-accent" : "border-line text-ink-soft hover:border-line-strong"}`}>
            {f.label} {jobs && <span className="text-ink-faint">{jobs.filter((j) => f.match(j.status)).length}</span>}
          </button>
        ))}
      </div>

      <div className="mt-4"><ErrorNote error={error} /></div>
      {jobs && shown.length === 0 && (
        <p className="mt-10 text-ink-soft">Nothing here yet. <Link className="text-accent underline" href="/jobs/new">Create a content request</Link> from a merge request, diff or API spec.</p>
      )}
      {shown.length > 0 && (
        <table className="mt-4 w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left text-ink-faint">
              <th className="py-2 pr-4 font-medium">Title</th>
              <th className="py-2 pr-4 font-medium">Type</th>
              <th className="hidden py-2 pr-4 font-medium md:table-cell">Area</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              <th className="hidden py-2 font-medium md:table-cell">Updated</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((j) => (
              <tr key={j.id} className="border-b border-line hover:bg-sheet">
                <td className="py-3 pr-4"><Link href={`/jobs/${j.id}`} className="font-medium text-ink hover:text-accent">{j.title}</Link></td>
                <td className="py-3 pr-4 text-ink-soft">{TYPE_LABEL[j.content_type]}</td>
                <td className="hidden py-3 pr-4 text-ink-soft md:table-cell">{j.product_area}</td>
                <td className="py-3 pr-4"><StatusPill status={j.status} /></td>
                <td className="hidden py-3 text-ink-faint md:table-cell">{ago(j.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
