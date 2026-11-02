"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, ErrorNote, Field, inputClass } from "@/components/ui";
import { API_URL, TYPE_LABEL, api, getToken } from "@/lib/api";

const TYPES = [
  { id: "release_note", channel: "release_notes", length: 300, use: "One entry for a release post: what changed, who it affects, how to start." },
  { id: "docs_page", channel: "docs", length: 600, use: "A task-based page with prerequisites, steps, options and troubleshooting." },
  { id: "blog", channel: "blog", length: 900, use: "A developer-facing story: the problem, what was built, how to try it." },
  { id: "api_reference", channel: "api_reference", length: 500, use: "Endpoint, parameters, examples and errors, without invented fields." },
  { id: "onboarding_guide", channel: "onboarding", length: 700, use: "Takes a new user from zero to a first success, step by step." },
];
const CHANNELS = [["docs", "Documentation site"], ["release_notes", "Release post"], ["blog", "Blog"],
  ["api_reference", "API reference"], ["onboarding", "Onboarding"]];
const KINDS = [["mr", "Merge request description"], ["diff", "Code diff"], ["api_spec", "API spec"],
  ["issue", "Issue discussion"], ["release_notes", "Release notes"], ["brief", "Product brief"], ["doc", "Existing doc"], ["notes", "Engineering notes"]];
const STEPS = ["Content type", "Audience and channel", "Sources", "Owner and review"];

export default function NewJob() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [type, setType] = useState(TYPES[0]);
  const [form, setForm] = useState({ title: "", audience: "", product_area: "Verify", target_channel: "release_notes",
    target_length: 300, reviewer_id: "", deadline: "" });
  const [files, setFiles] = useState<File[]>([]);
  const [paste, setPaste] = useState({ kind: "mr", filename: "mr-description.md", text: "" });
  const [users, setUsers] = useState<{ id: string; name: string; role: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api<typeof users>("/api/users").then(setUsers).catch(() => {}); }, []);
  const set = (k: string, v: string | number) => setForm((f) => ({ ...f, [k]: v }));

  const stepValid = [true, form.title.length >= 3 && form.audience.length >= 2 && form.product_area.length >= 2,
    files.length > 0 || paste.text.trim().length > 0, true][step];

  async function submit() {
    setBusy(true); setError(null);
    try {
      const job = await api<{ id: string }>("/api/content-jobs", { method: "POST", json: {
        ...form, content_type: type.id, target_length: Number(form.target_length),
        reviewer_id: form.reviewer_id || null, deadline: form.deadline || null,
        inputs: paste.text.trim() ? [paste] : [],
      } });
      if (files.length) {
        const fd = new FormData();
        files.forEach((f) => fd.append("files", f));
        const res = await fetch(`${API_URL}/api/content-jobs/${job.id}/inputs`, { method: "POST", body: fd,
          headers: { Authorization: `Bearer ${getToken()}` } });
        if (!res.ok) throw new Error((await res.json()).error?.message ?? "Upload failed");
      }
      await api("/api/agent-workflow/run", { method: "POST", json: { job_id: job.id } });
      router.push(`/jobs/${job.id}?tab=workflow`);
    } catch (e) {
      setError((e as Error).message); setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-semibold">New content request</h1>
      <p className="text-ink-soft">Tell the engine what to write and give it the technical sources to write from.</p>

      <ol className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-sm" aria-label="Steps">
        {STEPS.map((s, i) => (
          <li key={s} className={i === step ? "font-medium text-accent" : i < step ? "text-ink" : "text-ink-faint"}>
            {i + 1}. {s}
          </li>
        ))}
      </ol>

      <section className="mt-6 rounded-lg border border-line bg-sheet p-6">
        {step === 0 && (
          <fieldset>
            <legend className="sr-only">Content type</legend>
            <div className="divide-y divide-line">
              {TYPES.map((t) => (
                <label key={t.id} className="flex cursor-pointer gap-3 py-3">
                  <input type="radio" name="type" checked={type.id === t.id} className="mt-1 accent-[var(--color-accent)]"
                    onChange={() => { setType(t); set("target_channel", t.channel); set("target_length", t.length); }} />
                  <span><span className="block font-medium">{TYPE_LABEL[t.id]}</span><span className="block text-sm text-ink-soft">{t.use}</span></span>
                </label>
              ))}
            </div>
          </fieldset>
        )}

        {step === 1 && (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="md:col-span-2"><Field label="Working title"><input className={inputClass} value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="Pipeline cache analytics" /></Field></div>
            <div className="md:col-span-2"><Field label="Audience" hint="Who will read this, and what do they already know?"><input className={inputClass} value={form.audience} onChange={(e) => set("audience", e.target.value)} placeholder="Developers who maintain CI/CD pipelines" /></Field></div>
            <Field label="Product area"><input className={inputClass} value={form.product_area} onChange={(e) => set("product_area", e.target.value)} /></Field>
            <Field label="Channel">
              <select className={inputClass} value={form.target_channel} onChange={(e) => set("target_channel", e.target.value)}>
                {CHANNELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
            <Field label="Target length (words)"><input type="number" min={100} max={3000} className={inputClass} value={form.target_length} onChange={(e) => set("target_length", Number(e.target.value))} /></Field>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5">
            <Field label="Upload files" hint="Diffs, OpenAPI specs, Markdown notes. Text files up to 5 MB. Secrets are removed on upload.">
              <input type="file" multiple accept=".md,.txt,.diff,.patch,.yaml,.yml,.json,.graphql"
                className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-line-strong file:bg-sheet file:px-3 file:py-1.5"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
            </Field>
            {files.length > 0 && <ul className="text-sm text-ink-soft">{files.map((f) => <li key={f.name}>{f.name} ({Math.ceil(f.size / 1024)} KB)</li>)}</ul>}
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Or paste a source">
                <select className={inputClass} value={paste.kind} onChange={(e) => setPaste({ ...paste, kind: e.target.value })}>
                  {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </Field>
              <Field label="Name it"><input className={inputClass} value={paste.filename} onChange={(e) => setPaste({ ...paste, filename: e.target.value })} /></Field>
            </div>
            <textarea className={`${inputClass} h-48 font-mono text-xs`} value={paste.text} onChange={(e) => setPaste({ ...paste, text: e.target.value })}
              placeholder="Paste a merge request description, release summary or engineering notes" aria-label="Pasted source" />
          </div>
        )}

        {step === 3 && (
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Reviewer" hint="Who checks technical accuracy before approval">
              <select className={inputClass} value={form.reviewer_id} onChange={(e) => set("reviewer_id", e.target.value)}>
                <option value="">Any technical reviewer</option>
                {users.filter((u) => ["tech_reviewer", "doc_lead"].includes(u.role)).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
            </Field>
            <Field label="Deadline"><input type="date" className={inputClass} value={form.deadline} onChange={(e) => set("deadline", e.target.value)} /></Field>
            <dl className="md:col-span-2 grid grid-cols-[140px_1fr] gap-y-1 rounded-md bg-paper p-4 text-sm">
              <dt className="text-ink-faint">Type</dt><dd>{TYPE_LABEL[type.id]}</dd>
              <dt className="text-ink-faint">Title</dt><dd>{form.title}</dd>
              <dt className="text-ink-faint">Audience</dt><dd>{form.audience}</dd>
              <dt className="text-ink-faint">Sources</dt><dd>{[...files.map((f) => f.name), ...(paste.text ? [paste.filename] : [])].join(", ")}</dd>
            </dl>
          </div>
        )}
      </section>

      <div className="mt-4"><ErrorNote error={error} /></div>
      <div className="mt-4 flex justify-between">
        <Button variant="ghost" onClick={() => setStep((s) => s - 1)} disabled={step === 0}>Back</Button>
        {step < 3
          ? <Button onClick={() => setStep((s) => s + 1)} disabled={!stepValid}>Continue</Button>
          : <Button onClick={submit} disabled={busy}>{busy ? "Starting agents…" : "Create job and start drafting"}</Button>}
      </div>
    </div>
  );
}
