"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorNote, Percent } from "@/components/ui";
import { STATUS_LABEL, api } from "@/lib/api";

interface Metrics {
  totals: Record<string, number>;
  jobs_by_status: Record<string, number>;
  rework_rate: number;
  avg_approval_cycle_hours: number | null;
  avg_time_to_first_draft_minutes: number | null;
  avg_revision_requests_per_job: number;
  stage_latency_ms: Record<string, { avg: number; runs: number }>;
  model_error_rate: number;
  tokens: { in: number; out: number };
  quality: Record<string, number | null>;
  quality_by_writer_prompt: Record<string, { jobs: number; avg_overall: number | null; avg_unsupported_claims: number | null }>;
  review_issue_categories: Record<string, number>;
  weekly_throughput: { week: string; created: number; in_review: number; exported: number }[];
  recent_exports: { draft_id: string; format: string; target: string; mr_url: string | null; created_at: string }[];
}

const STAGE = { context: "Context Reader", draft: "Writer", tech_review: "Tech Reviewer", tone: "Tone", structure: "Structure", publish_prep: "Publishing" } as Record<string, string>;
const C = { accent: "#4f46c8", soft: "#a9a4e8", good: "#1d7a52", grid: "#dde1e8", ink: "#4a5468" };

function Stat({ value, label, note }: { value: React.ReactNode; label: string; note?: string }) {
  return (
    <div className="border-l-2 border-line pl-4">
      <p className="text-2xl font-semibold">{value}</p>
      <p className="text-sm text-ink-soft">{label}</p>
      {note && <p className="text-xs text-ink-faint">{note}</p>}
    </div>
  );
}

export default function Dashboard() {
  const [m, setM] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api<Metrics>("/api/metrics").then(setM).catch((e) => setError(e.message)); }, []);
  if (error) return <ErrorNote error={error} />;
  if (!m) return <p className="text-ink-soft">Loading metrics…</p>;

  const latency = Object.entries(m.stage_latency_ms).map(([k, v]) => ({ stage: STAGE[k] ?? k, seconds: +(v.avg / 1000).toFixed(2) }));
  const statusRows = Object.entries(m.jobs_by_status).sort((a, b) => b[1] - a[1]);
  const maxStatus = Math.max(1, ...statusRows.map(([, n]) => n));

  return (
    <div className="max-w-6xl">
      <h1 className="text-2xl font-semibold">Pipeline health</h1>
      <p className="text-ink-soft">
        {m.totals.backlog} jobs are waiting on someone. {m.totals.in_review} need a reviewer and {m.totals.needs_input + m.totals.failed} need the author.
      </p>

      <div className="mt-8 grid grid-cols-2 gap-6 md:grid-cols-4">
        <Stat value={m.avg_time_to_first_draft_minutes != null ? `${m.avg_time_to_first_draft_minutes.toFixed(1)} min` : "–"} label="Request to review-ready draft" />
        <Stat value={m.avg_approval_cycle_hours != null ? `${m.avg_approval_cycle_hours.toFixed(1)} h` : "–"} label="Review to approval" />
        <Stat value={<Percent value={m.rework_rate} />} label="Drafts sent back for rework" />
        <Stat value={m.totals.exported} label="Published" note={`${m.totals.jobs} jobs in total`} />
      </div>

      <div className="mt-10 grid gap-10 lg:grid-cols-2">
        <section>
          <h2 className="font-semibold">Where jobs are now</h2>
          <ul className="mt-3 space-y-2">
            {statusRows.map(([s, n]) => (
              <li key={s} className="grid grid-cols-[150px_1fr_32px] items-center gap-3 text-sm">
                <span className="text-ink-soft">{STATUS_LABEL[s] ?? s}</span>
                <span className="h-2 rounded-full bg-accent" style={{ width: `${(n / maxStatus) * 100}%`, opacity: ["FAILED", "NEEDS_INPUT"].includes(s) ? 0.45 : 1 }} />
                <span className="text-right font-medium">{n}</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h2 className="font-semibold">Draft quality</h2>
          <dl className="mt-3 grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-ink-soft">Average quality score</dt><dd className="font-medium">{m.quality.avg_overall ?? "–"}</dd>
            <dt className="text-ink-soft">Claims backed by a source</dt><dd className="font-medium"><Percent value={m.quality.avg_claim_support_rate} /></dd>
            <dt className="text-ink-soft">Citations that resolve</dt><dd className="font-medium"><Percent value={m.quality.avg_citation_validity} /></dd>
            <dt className="text-ink-soft">Source facts used</dt><dd className="font-medium"><Percent value={m.quality.avg_source_coverage} /></dd>
            <dt className="text-ink-soft">Model error rate</dt><dd className="font-medium"><Percent value={m.model_error_rate} /></dd>
          </dl>
          <h3 className="mt-6 text-sm font-medium">Writer prompt versions compared</h3>
          <table className="mt-2 w-full text-sm">
            <thead><tr className="border-b border-line text-left text-ink-faint"><th className="py-1 font-medium">Prompt</th><th className="font-medium">Jobs</th><th className="font-medium">Quality</th><th className="font-medium">Unsupported claims</th></tr></thead>
            <tbody>{Object.entries(m.quality_by_writer_prompt).map(([pv, v]) => (
              <tr key={pv} className="border-b border-line"><td className="py-1.5">{pv}</td><td>{v.jobs}</td><td>{v.avg_overall}</td><td>{v.avg_unsupported_claims}</td></tr>
            ))}</tbody>
          </table>
        </section>

        <section>
          <h2 className="font-semibold">Weekly throughput</h2>
          <div className="mt-3 h-64">
            <ResponsiveContainer>
              <BarChart data={m.weekly_throughput}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="week" tick={{ fill: C.ink, fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fill: C.ink, fontSize: 12 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="created" name="Requested" fill={C.soft} />
                <Bar dataKey="in_review" name="Reached review" fill={C.accent} />
                <Bar dataKey="exported" name="Published" fill={C.good} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section>
          <h2 className="font-semibold">Average time per agent</h2>
          <div className="mt-3 h-64">
            <ResponsiveContainer>
              <BarChart data={latency} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid stroke={C.grid} horizontal={false} />
                <XAxis type="number" unit=" s" tick={{ fill: C.ink, fontSize: 12 }} />
                <YAxis type="category" dataKey="stage" width={110} tick={{ fill: C.ink, fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="seconds" fill={C.accent} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-ink-faint">{m.tokens.in.toLocaleString()} tokens in, {m.tokens.out.toLocaleString()} out across all runs.</p>
        </section>

        <section>
          <h2 className="font-semibold">What reviewers flag</h2>
          {Object.keys(m.review_issue_categories).length === 0 ? <p className="mt-2 text-sm text-ink-soft">No categorised review issues yet.</p> : (
            <ul className="mt-3 space-y-1 text-sm">{Object.entries(m.review_issue_categories).map(([k, v]) => <li key={k}>{k.replace("_", " ")}: <strong>{v}</strong></li>)}</ul>
          )}
        </section>

        <section>
          <h2 className="font-semibold">Recent exports</h2>
          {m.recent_exports.length === 0 ? <p className="mt-2 text-sm text-ink-soft">Nothing published yet.</p> : (
            <ul className="mt-3 space-y-1 text-sm">{m.recent_exports.map((e) => (
              <li key={e.created_at}><code>{e.target}</code> <span className="text-ink-faint">as {e.format}</span>
                {e.mr_url && <a className="ml-2 text-accent underline" href={e.mr_url} target="_blank" rel="noreferrer">merge request</a>}</li>
            ))}</ul>
          )}
        </section>
      </div>
    </div>
  );
}
