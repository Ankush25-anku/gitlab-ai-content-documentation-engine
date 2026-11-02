"use client";

import { useEffect, useMemo, useState } from "react";
import Markdown from "@/components/Markdown";
import { Button, ErrorNote, Pill, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import type { DraftFull, JobDetail } from "@/lib/types";
import ReviewPanel from "@/review-panel/ReviewPanel";

const RERUNS = [
  { stages: ["tone"], label: "Tone only" },
  { stages: ["structure"], label: "Structure only" },
  { stages: ["tech_review"], label: "Fact-check again" },
  { stages: ["draft", "tech_review", "tone", "structure"], label: "Redraft from facts" },
];
const STAGE_NAME: Record<string, string> = { draft: "Writer", tech_review: "Fact-check", tone: "Tone", structure: "Structure",
  human_edit: "Human edit", claim_removed: "Claim removed" };

function Score({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div className="min-w-[96px]">
      <p className={`text-lg font-semibold ${good ? "text-ink" : "text-bad"}`}>{value}</p>
      <p className="text-xs text-ink-faint">{label}</p>
    </div>
  );
}

export default function DraftEditor({ job, onChange }: { job: JobDetail; onChange: () => void }) {
  const [draftId, setDraftId] = useState(job.latest_draft?.id ?? null);
  const [draft, setDraft] = useState<DraftFull | null>(job.latest_draft);
  const [activeSource, setActiveSource] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [instructions, setInstructions] = useState("");
  const [compare, setCompare] = useState<string | null>(null);
  const [diff, setDiff] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setDraftId(job.latest_draft?.id ?? null); }, [job.latest_draft?.id]);
  useEffect(() => {
    if (!draftId) return;
    api<DraftFull>(`/api/drafts/${draftId}`).then(setDraft).catch((e) => setError(e.message));
  }, [draftId, job.updated_at]);

  const sources = job.context_pack?.sources ?? [];
  const validIds = useMemo(() => new Set(sources.map((s) => s.id)), [sources]);
  const isLatest = draft?.id === job.latest_draft?.id;
  const flagged = (draft?.claims ?? []).filter((c) => c.verdict === "unsupported" && !c.resolved).map((c) => c.claim);
  const q = draft?.quality_scores;
  const source = sources.find((s) => s.id === activeSource);

  async function saveEdit() {
    setError(null);
    try {
      await api(`/api/drafts/${draft!.id}/review`, { method: "POST", json: { action: "edit", content_md: text } });
      setEditing(false); onChange();
    } catch (e) { setError((e as Error).message); }
  }
  async function rerun(stages: string[]) {
    setError(null);
    try { await api(`/api/drafts/${draft!.id}/refine`, { method: "POST", json: { stages, instructions } }); setInstructions(""); onChange(); }
    catch (e) { setError((e as Error).message); }
  }
  async function showDiff(v: string) {
    setCompare(v);
    if (!v || !draft) { setDiff(null); return; }
    const r = await api<{ diff: string }>(`/api/drafts/${draft.id}/versions?compare=${v},${draft.version}`);
    setDiff(r.diff || "No differences.");
  }

  if (!draft) return <p className="text-ink-soft">No draft yet. The Documentation Writer creates one after the context is ready.</p>;

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_380px]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-3 border-b border-line pb-3 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-ink-faint">Version</span>
            <select className="rounded-md border border-line-strong bg-sheet px-2 py-1" value={draftId ?? ""} onChange={(e) => { setDraftId(e.target.value); setDiff(null); setCompare(null); }}>
              {job.drafts.slice().reverse().map((d) => <option key={d.id} value={d.id}>v{d.version} · {STAGE_NAME[d.stage] ?? d.stage}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2">
            <span className="text-ink-faint">Compare with</span>
            <select className="rounded-md border border-line-strong bg-sheet px-2 py-1" value={compare ?? ""} onChange={(e) => showDiff(e.target.value)}>
              <option value="">–</option>
              {job.drafts.filter((d) => d.version !== draft.version).map((d) => <option key={d.id} value={d.version}>v{d.version}</option>)}
            </select>
          </label>
          {draft.review_state === "approved" && <Pill tone="good">Approved</Pill>}
          {!isLatest && <Pill tone="warn">Older version</Pill>}
          <span className="ml-auto" />
          {isLatest && !editing && <Button variant="secondary" onClick={() => { setText(draft.content_md); setEditing(true); }}>Edit text</Button>}
        </div>

        {q && (
          <div className="flex flex-wrap gap-6 border-b border-line py-4">
            <Score label="Quality score" value={`${Math.round(q.overall)}`} good={q.overall >= 80} />
            <Score label="Claims supported" value={`${Math.round(q.claim_support_rate * 100)}%`} good={q.unsupported_claims === 0 || flagged.length === 0} />
            <Score label="Valid citations" value={`${Math.round(q.citation_validity * 100)}%`} good={q.citation_validity === 1} />
            <Score label="Source coverage" value={`${Math.round(q.source_coverage * 100)}%`} good={q.source_coverage >= 0.7} />
            <Score label="Template sections" value={`${Math.round(q.structure_compliance * 100)}%`} good={q.structure_compliance === 1} />
            <Score label="Open gaps" value={`${q.needs_source_markers}`} good={q.needs_source_markers === 0} />
          </div>
        )}

        <ErrorNote error={error} />
        {diff ? (
          <pre className="mt-4 overflow-auto rounded-md border border-line bg-sheet p-4 text-xs leading-relaxed">
            {diff.split("\n").map((l, i) => (
              <span key={i} className={`block ${l.startsWith("+") && !l.startsWith("+++") ? "bg-good-soft text-good" : l.startsWith("-") && !l.startsWith("---") ? "bg-bad-soft text-bad" : ""}`}>{l || " "}</span>
            ))}
          </pre>
        ) : editing ? (
          <div className="mt-4">
            <textarea className={`${inputClass} h-[60vh] font-mono text-xs leading-relaxed`} value={text} onChange={(e) => setText(e.target.value)} aria-label="Draft Markdown" />
            <div className="mt-3 flex gap-2">
              <Button onClick={saveEdit}>Save as new version</Button>
              <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <article className="mt-6 rounded-lg border border-line bg-sheet px-6 py-8 md:px-10">
            <Markdown markdown={draft.content_md} validIds={validIds} activeId={activeSource} onCite={setActiveSource} flagged={flagged} />
          </article>
        )}

        {isLatest && !editing && (
          <section className="mt-6 rounded-lg border border-line bg-sheet p-4">
            <h3 className="font-medium">Rerun a stage</h3>
            <p className="text-sm text-ink-soft">Only the stages you pick run again. Earlier outputs are reused.</p>
            <input className={`${inputClass} mt-3`} placeholder="Optional instruction, for example: more concise, neutral tone"
              value={instructions} onChange={(e) => setInstructions(e.target.value)} aria-label="Instruction for the rerun" />
            <div className="mt-3 flex flex-wrap gap-2">
              {RERUNS.map((r) => <Button key={r.label} variant="secondary" onClick={() => rerun(r.stages)}>{r.label}</Button>)}
            </div>
          </section>
        )}
      </div>

      <aside className="space-y-6 xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto">
        <section className="rounded-lg border border-line bg-sheet p-4">
          <h3 className="font-medium">Source</h3>
          {source ? (
            <>
              <p className="mt-1 text-sm font-medium">{source.id} · {source.title}</p>
              <p className="text-xs text-ink-faint">{source.chunk_id}{source.stale && " · possibly stale"}</p>
              <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-paper p-3 text-xs leading-relaxed">{source.text}</pre>
            </>
          ) : activeSource ? (
            <p className="mt-1 text-sm text-bad">{activeSource} does not exist in the context pack. This citation is invalid.</p>
          ) : (
            <p className="mt-1 text-sm text-ink-soft">Select a citation in the draft to see the exact text it comes from.</p>
          )}
        </section>
        <ReviewPanel job={job} draft={draft} isLatest={isLatest} onChange={onChange} onCite={setActiveSource} />
      </aside>
    </div>
  );
}
