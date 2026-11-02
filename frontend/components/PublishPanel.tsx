"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { JobDetail } from "@/lib/types";
import { useMe } from "./Shell";
import { Button, ErrorNote } from "./ui";

interface Prepared { package: { file_path: string; mr_title: string; mr_description: string; labels: string[];
  front_matter: Record<string, unknown>; approved_by: string[] }; markdown_preview: string }
interface AuditRow { id: string; actor_id: string | null; event: string; details: Record<string, unknown>; created_at: string }

const FORMATS = [
  { id: "gitlab_mr", label: "Open a merge request", hint: "Commits the page to a branch in the docs project and opens an MR." },
  { id: "markdown", label: "Markdown file", hint: "Front matter and body, ready for a docs repository." },
  { id: "cms_json", label: "CMS payload", hint: "Structured JSON blocks for a content management system." },
];

export default function PublishPanel({ job, onChange }: { job: JobDetail; onChange: () => void }) {
  const me = useMe();
  const draft = job.latest_draft;
  const approved = draft?.review_state === "approved" && ["APPROVED", "PUBLISH_READY", "EXPORTED", "PUBLISH_PREPARING"].includes(job.status);
  const canPublish = !!me && ["publisher", "doc_lead", "admin"].includes(me.role);
  const [prep, setPrep] = useState<Prepared | null>(null);
  const [format, setFormat] = useState("markdown");
  const [result, setResult] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditRow[]>([]);

  useEffect(() => {
    if (me && ["tech_reviewer", "doc_lead", "admin"].includes(me.role))
      api<AuditRow[]>(`/api/audit-logs?job_id=${job.id}`).then(setAudit).catch(() => {});
  }, [me, job.id, job.updated_at]);

  async function prepare() {
    setError(null);
    try { setPrep(await api<Prepared>("/api/publish/prepare", { method: "POST", json: { draft_id: draft!.id } })); onChange(); }
    catch (e) { setError((e as Error).message); }
  }
  async function exportIt() {
    setError(null); setResult(null);
    try { setResult(await api("/api/publish/export", { method: "POST", json: { draft_id: draft!.id, format } })); onChange(); }
    catch (e) { setError((e as Error).message); }
  }
  function download() {
    const blob = new Blob([format === "cms_json" ? JSON.stringify(result?.payload, null, 2) : result?.content ?? ""], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = format === "cms_json" ? "content.json" : (result?.file_path ?? "content.md").split("/").pop();
    a.click();
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_1fr]">
      <section>
        <h2 className="text-lg font-semibold">Publish</h2>
        {!approved ? (
          <p className="mt-2 rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">
            Publishing unlocks after a technical reviewer approves the latest version. The server refuses exports of unapproved drafts.
          </p>
        ) : (
          <>
            <p className="mt-1 text-sm text-ink-soft">Approved. The Publishing Coordinator prepares metadata, file path and merge request text.</p>
            {!prep && <Button className="mt-4" onClick={prepare} disabled={!canPublish && me?.role !== "tech_reviewer"}>Prepare for publishing</Button>}
            {prep && (
              <div className="mt-4 space-y-4">
                <dl className="grid grid-cols-[120px_1fr] gap-y-1 text-sm">
                  <dt className="text-ink-faint">File</dt><dd><code>{prep.package.file_path}</code></dd>
                  <dt className="text-ink-faint">MR title</dt><dd>{prep.package.mr_title}</dd>
                  <dt className="text-ink-faint">Labels</dt><dd>{prep.package.labels.join(", ")}</dd>
                  <dt className="text-ink-faint">Approved by</dt><dd>{prep.package.approved_by.join(", ")}</dd>
                </dl>
                <fieldset className="space-y-2">
                  <legend className="text-sm font-medium">Export as</legend>
                  {FORMATS.map((f) => (
                    <label key={f.id} className="flex gap-3 text-sm">
                      <input type="radio" name="format" checked={format === f.id} onChange={() => setFormat(f.id)} className="mt-1 accent-[var(--color-accent)]" />
                      <span><span className="block font-medium">{f.label}</span><span className="text-ink-soft">{f.hint}</span></span>
                    </label>
                  ))}
                </fieldset>
                <Button onClick={exportIt} disabled={!canPublish}>{format === "gitlab_mr" ? "Open merge request" : "Export"}</Button>
                {!canPublish && <p className="text-xs text-ink-faint">Sign in as a publisher or documentation lead to export.</p>}
              </div>
            )}
          </>
        )}
        <div className="mt-3"><ErrorNote error={error} /></div>
        {result && (
          <div className="mt-4 rounded-md border border-good/40 bg-good-soft p-4 text-sm">
            <p className="font-medium text-good">Published as {FORMATS.find((f) => f.id === result.format)?.label.toLowerCase()}.</p>
            {result.mr_url && <p className="mt-1"><a className="text-accent underline" href={result.mr_url} target="_blank" rel="noreferrer">{result.mr_url}</a></p>}
            {(result.content || result.payload) && <button className="mt-2 text-accent underline" onClick={download}>Download file</button>}
          </div>
        )}
        {prep && (
          <>
            <h3 className="mt-8 font-medium">Exported Markdown preview</h3>
            <pre className="mt-2 max-h-[420px] overflow-auto rounded-md border border-line bg-sheet p-4 text-xs leading-relaxed whitespace-pre-wrap">{prep.markdown_preview}</pre>
          </>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold">Audit trail</h2>
        {audit.length === 0 ? <p className="mt-2 text-sm text-ink-soft">Visible to reviewers and documentation leads.</p> : (
          <ol className="mt-3 border-l border-line pl-4 text-sm">
            {audit.map((a) => (
              <li key={a.id} className="mb-3">
                <p><span className="font-medium">{a.event}</span> <span className="text-ink-faint">by {a.actor_id ?? "system"}</span></p>
                <p className="text-xs text-ink-faint">
                  {new Date(a.created_at + (a.created_at.endsWith("Z") || a.created_at.includes("+") ? "" : "Z")).toLocaleString()}
                  {a.details?.new ? ` · ${a.details.old} to ${a.details.new}` : ""}
                  {a.details?.comment ? ` · “${a.details.comment}”` : ""}
                </p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
