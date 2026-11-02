"use client";

import { useState } from "react";
import { useMe } from "@/components/Shell";
import { Button, ErrorNote, Pill, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import type { DraftFull, JobDetail } from "@/lib/types";

const VERDICT_TONE = { supported: "good", partial: "warn", unsupported: "bad" } as const;
const CATEGORIES = ["accuracy", "unsupported_claim", "tone", "structure", "terminology", "missing_info", "other"];

export default function ReviewPanel({ job, draft, isLatest, onChange, onCite }: {
  job: JobDetail; draft: DraftFull; isLatest: boolean; onChange: () => void; onCite: (id: string) => void;
}) {
  const me = useMe();
  const [comment, setComment] = useState("");
  const [category, setCategory] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [show, setShow] = useState<"open" | "all">("open");
  const isReviewer = !!me && ["tech_reviewer", "doc_lead", "admin"].includes(me.role);
  const open = draft.claims.filter((c) => c.verdict === "unsupported" && !c.resolved);
  const listed = show === "open" ? draft.claims.filter((c) => c.verdict !== "supported" || !c.resolved) : draft.claims;
  const q = draft.quality_scores;

  async function act(json: Record<string, unknown>) {
    setError(null);
    try {
      await api(`/api/drafts/${draft.id}/review`, { method: "POST", json: { comment: comment || undefined, issue_category: category || undefined, ...json } });
      setComment(""); setCategory(""); onChange();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <section className="rounded-lg border border-line bg-sheet p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-medium">Review</h3>
        <div className="flex gap-1 text-xs">
          {(["open", "all"] as const).map((s) => (
            <button key={s} onClick={() => setShow(s)} className={`rounded px-2 py-0.5 ${show === s ? "bg-accent-soft text-accent" : "text-ink-soft"}`}>
              {s === "open" ? "Needs attention" : `All ${draft.claims.length} claims`}
            </button>
          ))}
        </div>
      </div>

      {open.length > 0 && (
        <p className="mt-2 rounded-md bg-bad-soft px-3 py-2 text-sm text-bad">
          {open.length} unsupported claim{open.length > 1 ? "s" : ""} must be removed or overridden before approval.
        </p>
      )}

      <ul className="mt-3 space-y-2">
        {listed.length === 0 && <li className="text-sm text-ink-soft">Every claim is backed by a source.</li>}
        {listed.map((c) => (
          <li key={c.id} className="rounded-md border border-line px-3 py-2 text-sm">
            <div className="flex items-start gap-2">
              <Pill tone={c.resolved && c.verdict === "unsupported" ? "quiet" : VERDICT_TONE[c.verdict]}>{c.resolved && c.verdict === "unsupported" ? "resolved" : c.verdict}</Pill>
              <p className="min-w-0">{c.claim}</p>
            </div>
            <p className="mt-1 text-xs text-ink-faint">
              {c.source_ids.map((s) => <button key={s} className="mr-1 text-accent underline" onClick={() => onCite(s)}>{s}</button>)}
              {c.fix && <span>{c.fix}</span>}
              {c.resolution_note && <span> {c.resolution_note}</span>}
            </p>
            {c.verdict === "unsupported" && !c.resolved && isReviewer && isLatest && (
              <div className="mt-2 flex gap-2">
                <Button variant="danger" className="!px-2 !py-1 text-xs" onClick={() => act({ action: "resolve_claim", claim_id: c.id, resolution: "remove" })}>Remove from draft</Button>
                <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={() => {
                  if (!comment.trim()) { setError("Write why this claim is correct in the comment box, then override."); return; }
                  act({ action: "resolve_claim", claim_id: c.id, resolution: "override" });
                }}>Keep, with justification</Button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {(q?.risk_flags?.length || q?.reviewer_questions?.length) ? (
        <div className="mt-4 text-sm">
          <h4 className="font-medium">Flags from the Technical Reviewer</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-ink-soft">
            {q?.risk_flags?.map((r) => <li key={r}>{r}</li>)}
            {q?.reviewer_questions?.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </div>
      ) : null}

      {draft.reviews && draft.reviews.length > 0 && (
        <div className="mt-4 text-sm">
          <h4 className="font-medium">Activity on this version</h4>
          <ul className="mt-1 space-y-1 text-ink-soft">
            {draft.reviews.map((r) => <li key={r.id}><span className="text-ink">{r.action.replace("_", " ")}</span>{r.comment && `: ${r.comment}`}</li>)}
          </ul>
        </div>
      )}

      {isLatest && (
        <div className="mt-4 space-y-2 border-t border-line pt-4">
          <textarea className={`${inputClass} h-20`} placeholder="Comment for the author" value={comment} onChange={(e) => setComment(e.target.value)} aria-label="Review comment" />
          <select className={inputClass} value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Issue category">
            <option value="">Issue category (optional)</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
          </select>
          <ErrorNote error={error} />
          <div className="flex flex-wrap gap-2">
            {isReviewer && job.status === "IN_REVIEW" && (
              <Button onClick={() => act({ action: "approve" })} disabled={open.length > 0}
                title={open.length ? "Resolve unsupported claims first" : undefined}>Approve</Button>
            )}
            {isReviewer && ["IN_REVIEW", "APPROVED", "PUBLISH_READY"].includes(job.status) && (
              <Button variant="secondary" onClick={() => act({ action: "request_revision", revision_stages: category === "tone" ? ["tone"] : category === "structure" ? ["structure"] : undefined })}>
                Request revision</Button>
            )}
            {isReviewer && job.status === "IN_REVIEW" && <Button variant="danger" onClick={() => act({ action: "reject" })}>Reject</Button>}
            <Button variant="ghost" onClick={() => comment.trim() && act({ action: "comment" })} disabled={!comment.trim()}>Comment</Button>
          </div>
          {!isReviewer && <p className="text-xs text-ink-faint">Only technical reviewers and documentation leads can approve.</p>}
        </div>
      )}
    </section>
  );
}
