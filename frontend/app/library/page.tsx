"use client";

import { useEffect, useState } from "react";
import { ErrorNote, Pill, inputClass } from "@/components/ui";
import { TYPE_LABEL, api } from "@/lib/api";

interface Library { content_types: Record<string, { required_headings: string[]; guidance: string; description: string }>;
  tone_rules: Record<string, string[]>; glossary: { term: string; avoid: string[] }[] }
interface Doc { id: string; title: string; kind: string; product_area: string; updated_at: string; chunks: number }
interface Prompt { id: string; agent: string; version: number; file_hash: string; body: string }
interface Hit { chunk_id: string; title: string; heading: string; text: string; score: number; stale: boolean }

const SECTIONS = ["Templates", "Tone by channel", "Glossary", "Knowledge base", "Prompts"];

export default function LibraryPage() {
  const [lib, setLib] = useState<Library | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [section, setSection] = useState(0);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Library>("/api/library").then(setLib).catch((e) => setError(e.message));
    api<Doc[]>("/api/kb/documents").then(setDocs).catch(() => {});
    api<Prompt[]>("/api/prompts").then(setPrompts).catch(() => {});
  }, []);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (q.trim()) setHits(await api<Hit[]>(`/api/kb/search?q=${encodeURIComponent(q)}`));
  }

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-semibold">Style and knowledge</h1>
      <p className="text-ink-soft">The rules and reference material every agent works from.</p>
      <ErrorNote error={error} />
      <nav className="mt-6 flex flex-wrap gap-1 border-b border-line">
        {SECTIONS.map((s, i) => (
          <button key={s} onClick={() => setSection(i)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${section === i ? "border-accent font-medium text-accent" : "border-transparent text-ink-soft"}`}>{s}</button>
        ))}
      </nav>

      {lib && section === 0 && (
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          {Object.entries(lib.content_types).map(([k, t]) => (
            <section key={k}>
              <h2 className="font-semibold">{TYPE_LABEL[k]}</h2>
              <p className="text-sm text-ink-soft">{t.guidance}</p>
              <ol className="mt-2 list-decimal pl-5 text-sm">{t.required_headings.map((h) => <li key={h}>{h}</li>)}</ol>
            </section>
          ))}
        </div>
      )}
      {lib && section === 1 && (
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          {Object.entries(lib.tone_rules).map(([c, rules]) => (
            <section key={c}><h2 className="font-semibold capitalize">{c.replace("_", " ")}</h2>
              <ul className="mt-1 list-disc pl-5 text-sm text-ink-soft">{rules.map((r) => <li key={r}>{r}</li>)}</ul></section>
          ))}
        </div>
      )}
      {lib && section === 2 && (
        <table className="mt-6 w-full text-sm">
          <thead><tr className="border-b border-line text-left text-ink-faint"><th className="py-2 font-medium">Use</th><th className="font-medium">Instead of</th></tr></thead>
          <tbody>{lib.glossary.map((g) => <tr key={g.term} className="border-b border-line"><td className="py-2 font-medium">{g.term}</td><td className="text-ink-soft">{g.avoid.join(", ")}</td></tr>)}</tbody>
        </table>
      )}
      {section === 3 && (
        <div className="mt-6">
          <form onSubmit={search} className="flex gap-2">
            <input className={inputClass} placeholder="Try a retrieval query, for example: cache key fallback" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search the knowledge base" />
          </form>
          {hits && (
            <ul className="mt-4 space-y-2">{hits.map((h) => (
              <li key={h.chunk_id} className="rounded-md border border-line bg-sheet p-3 text-sm">
                <p className="font-medium">{h.title} › {h.heading} <span className="font-normal text-ink-faint">match {h.score.toFixed(2)}</span> {h.stale && <Pill tone="warn">Possibly stale</Pill>}</p>
                <p className="mt-1 line-clamp-3 text-ink-soft">{h.text}</p>
              </li>))}
            </ul>
          )}
          <table className="mt-6 w-full text-sm">
            <thead><tr className="border-b border-line text-left text-ink-faint"><th className="py-2 font-medium">Document</th><th className="font-medium">Kind</th><th className="font-medium">Area</th><th className="font-medium">Updated</th><th className="font-medium">Chunks</th></tr></thead>
            <tbody>{docs.map((d) => <tr key={d.id} className="border-b border-line"><td className="py-2">{d.title}</td><td>{d.kind}</td><td>{d.product_area}</td><td>{d.updated_at}</td><td>{d.chunks}</td></tr>)}</tbody>
          </table>
        </div>
      )}
      {section === 4 && (
        <div className="mt-6 space-y-3">
          {prompts.map((p) => (
            <details key={p.id} className="rounded-md border border-line bg-sheet">
              <summary className="cursor-pointer px-4 py-3 text-sm"><span className="font-medium">{p.agent}</span> version {p.version} <span className="text-ink-faint">hash {p.file_hash}</span></summary>
              <pre className="overflow-auto border-t border-line bg-paper p-4 text-xs whitespace-pre-wrap">{p.body}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
