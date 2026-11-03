"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { JobDetail } from "@/lib/types";
import StageRail from "./StageRail";
import { Button, ErrorNote, Pill } from "./ui";

export default function WorkflowMonitor({ job, onChange }: { job: JobDetail; onChange: () => void }) {
  const [selected, setSelected] = useState<string | null>("draft");
  const [error, setError] = useState<string | null>(null);
  const runs = job.runs.filter((r) => r.stage === selected);
  const totals = job.runs.reduce((a, r) => ({ ms: a.ms + r.latency_ms, tin: a.tin + r.tokens_in, tout: a.tout + r.tokens_out }), { ms: 0, tin: 0, tout: 0 });

  async function retry(simulate?: string) {
    setError(null);
    try { await api("/api/agent-workflow/run", { method: "POST", json: { job_id: job.id, ...(simulate ? { simulate_failure: simulate } : {}) } }); onChange(); }
    catch (e) { setError((e as Error).message); }
  }

  return (
    <div>
      <div className="rounded-lg border border-line bg-sheet px-4 py-6">
        <StageRail status={job.status} current={job.current_stage} runs={job.runs} onSelect={setSelected} selected={selected} />
      </div>

      {job.status !== "FAILED" && job.last_error?.code === "MODEL_BUSY" && (
        <p role="status" aria-live="polite" className="mt-4 rounded-md border border-warn/30 bg-warn-soft px-4 py-3 text-sm text-warn">
          <strong>{job.last_error.message}</strong> The {job.last_error.stage} stage will continue automatically.
        </p>
      )}
      {job.status === "FAILED" && job.last_error && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-bad/30 bg-bad-soft px-4 py-3 text-sm">
          <p className="text-bad"><strong>{job.last_error.stage} stage failed.</strong> {job.last_error.message} Earlier outputs are kept.</p>
          <Button variant="danger" onClick={() => retry()}>Retry from {job.last_error.stage}</Button>
        </div>
      )}
      <div className="mt-2"><ErrorNote error={error} /></div>

      <p className="mt-4 text-sm text-ink-faint">
        {job.runs.length} agent runs · {(totals.ms / 1000).toFixed(1)} s total · {totals.tin.toLocaleString()} tokens in, {totals.tout.toLocaleString()} out
      </p>

      <section className="mt-6">
        <h2 className="text-lg font-semibold">{selected ? `Output of ${runs[0]?.agent ?? selected}` : "Select a stage"}</h2>
        {selected === "review" && <p className="text-sm text-ink-soft">Human review happens on the Draft tab.</p>}
        {runs.length === 0 && selected !== "review" && <p className="text-sm text-ink-soft">This stage has not run yet.</p>}
        {runs.slice().reverse().map((r) => (
          <details key={r.id} open={r === runs[runs.length - 1]} className="mt-3 rounded-md border border-line bg-sheet">
            <summary className="flex cursor-pointer flex-wrap items-center gap-3 px-4 py-3 text-sm">
              <Pill tone={r.status === "succeeded" ? "good" : r.status === "failed" ? "bad" : "accent"}>{r.status}</Pill>
              <span>{new Date(r.started_at + (r.started_at.endsWith("Z") || r.started_at.includes("+") ? "" : "Z")).toLocaleTimeString()}</span>
              {r.prompt_version && <span className="text-ink-soft">prompt {r.prompt_version}</span>}
              <span className="text-ink-soft">model {r.model}</span>
              <span className="text-ink-faint">{r.latency_ms} ms · {r.tokens_in}/{r.tokens_out} tokens</span>
            </summary>
            {r.error && <p className="px-4 pb-3 text-sm text-bad">{r.error}</p>}
            {r.output != null && (
              <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap break-words border-t border-line bg-paper px-4 py-3 text-xs leading-relaxed">
                {JSON.stringify(r.output, null, 2)}
              </pre>
            )}
          </details>
        ))}
      </section>

      {process.env.NODE_ENV !== "production" && job.status === "IN_REVIEW" && (
        <p className="mt-8 text-xs text-ink-faint">
          Demo: <button className="underline" onClick={() => retry("tone")}>rerun with a simulated failure in the tone stage</button>
        </p>
      )}
    </div>
  );
}
