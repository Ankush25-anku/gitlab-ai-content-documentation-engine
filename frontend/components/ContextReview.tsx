"use client";

import { useState } from "react";
import { API_URL, api, getToken } from "@/lib/api";
import type { JobDetail } from "@/lib/types";
import { Button, ErrorNote, Pill, inputClass } from "./ui";

export default function ContextReview({ job, onChange }: { job: JobDetail; onChange: () => void }) {
  const cp = job.context_pack;
  const kb = cp?.sources.filter((s) => s.origin === "kb") ?? [];
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extra, setExtra] = useState("");
  const sourceTitle = (id: string) => cp?.sources.find((s) => s.id === id)?.title ?? id;
  const running = ["CONTEXT_PREPARING", "DRAFTING", "TECH_REVIEW", "TONE_OPTIMIZING", "STRUCTURE_OPTIMIZING"].includes(job.status);

  async function rebuild(thenRun: boolean) {
    setBusy(true); setError(null);
    try {
      if (extra.trim()) {
        const fd = new FormData();
        fd.append("text", extra); fd.append("kind", "notes"); fd.append("filename", "added-context.md");
        const r = await fetch(`${API_URL}/api/content-jobs/${job.id}/inputs`, { method: "POST", body: fd, headers: { Authorization: `Bearer ${getToken()}` } });
        if (!r.ok) throw new Error((await r.json()).error?.message);
        setExtra("");
      }
      const ids = [...excluded];
      if (thenRun) {
        if (ids.length) await api("/api/context-pack", { method: "POST", json: { job_id: job.id, excluded_chunk_ids: ids } });
        await api("/api/agent-workflow/run", { method: "POST", json: { job_id: job.id, from_stage: ids.length ? "draft" : "context" } });
      } else {
        await api("/api/context-pack", { method: "POST", json: { job_id: job.id, excluded_chunk_ids: ids } });
      }
      onChange();
    } catch (e) { setError((e as Error).message); }
    setBusy(false);
  }

  if (!cp?.pack) return <p className="text-ink-soft">The Context Reader has not run yet. Start the workflow to extract facts from the sources.</p>;
  const p = cp.pack;

  return (
    <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
      <section>
        {p.blocking_gaps.length > 0 && (
          <div className="mb-5 rounded-md border border-warn/40 bg-warn-soft p-4 text-sm">
            <p className="font-medium text-warn">Drafting is paused until these are answered</p>
            <ul className="mt-1 list-disc pl-5 text-ink">{p.blocking_gaps.map((g) => <li key={g}>{g}</li>)}</ul>
            <textarea className={`${inputClass} mt-3 h-28`} placeholder="Paste the missing details, for example the endpoint path and parameters"
              value={extra} onChange={(e) => setExtra(e.target.value)} aria-label="Missing details" />
          </div>
        )}
        <h2 className="text-lg font-semibold">Facts the writer may use</h2>
        <p className="text-sm text-ink-soft">{p.facts.length} facts extracted. Each one points to the source that states it.</p>
        <ol className="mt-3 space-y-2">
          {p.facts.map((f) => (
            <li key={f.id} className="rounded-md border border-line bg-sheet px-3 py-2 text-sm">
              <p>{f.text}</p>
              <p className="mt-1 text-xs text-ink-faint">{f.source_id} · {sourceTitle(f.source_id)} · {f.confidence} confidence</p>
            </li>
          ))}
        </ol>
      </section>

      <aside className="space-y-6">
        {(p.conflicts.length > 0 || p.gaps.length > 0 || cp.warnings.length > 0) && (
          <section>
            <h2 className="text-lg font-semibold">What to check</h2>
            <ul className="mt-2 space-y-2 text-sm">
              {p.conflicts.map((c) => <li key={c} className="rounded-md bg-bad-soft px-3 py-2 text-bad">Conflict: {c}</li>)}
              {p.gaps.map((g) => <li key={g} className="rounded-md bg-warn-soft px-3 py-2 text-warn">{g}</li>)}
              {cp.warnings.map((w) => <li key={w} className="rounded-md bg-paper px-3 py-2 text-ink-soft">{w}</li>)}
            </ul>
          </section>
        )}
        <section>
          <h2 className="text-lg font-semibold">Retrieved documentation</h2>
          <p className="text-sm text-ink-soft">Untick anything irrelevant or out of date, then rebuild.</p>
          <ul className="mt-3 divide-y divide-line rounded-md border border-line bg-sheet">
            {kb.map((s) => (
              <li key={s.chunk_id} className="flex gap-3 px-3 py-2.5 text-sm">
                <input type="checkbox" className="mt-1 accent-[var(--color-accent)]" checked={!excluded.has(s.chunk_id)}
                  aria-label={`Use ${s.title}`}
                  onChange={(e) => setExcluded((x) => { const n = new Set(x); e.target.checked ? n.delete(s.chunk_id) : n.add(s.chunk_id); return n; })} />
                <div className="min-w-0">
                  <p className="font-medium">{s.id} · {s.title}</p>
                  <p className="text-xs text-ink-faint">
                    Match {s.score?.toFixed(2)} · updated {s.updated_at} {s.stale && <Pill tone="warn">Possibly stale</Pill>}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h2 className="text-lg font-semibold">Job sources</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {job.inputs.map((i) => (
              <li key={i.id}>{i.filename} <span className="text-ink-faint">({i.kind})</span>
                {i.redactions.map((r) => <Pill key={r.type} tone={r.type === "prompt_injection_suspected" ? "bad" : "warn"}>
                  {r.type === "prompt_injection_suspected" ? "Instruction-like text ignored" : `${r.count} ${r.type.replace(/_/g, " ")} removed`}</Pill>)}
              </li>
            ))}
          </ul>
        </section>
        <ErrorNote error={error} />
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => rebuild(true)} disabled={busy || running}>{p.blocking_gaps.length ? "Add details and continue" : "Rebuild and redraft"}</Button>
          <Button variant="secondary" onClick={() => rebuild(false)} disabled={busy || running}>Rebuild context only</Button>
        </div>
      </aside>
    </div>
  );
}
