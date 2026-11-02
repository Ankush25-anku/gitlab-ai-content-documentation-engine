"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Button, ErrorNote, Field, inputClass } from "@/components/ui";
import { api, setToken } from "@/lib/api";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

const DEMO = [
  { role: "creator", name: "Priya", does: "Requests content and uploads technical sources" },
  { role: "tech_reviewer", name: "Arjun", does: "Checks claims against sources and approves drafts" },
  { role: "doc_lead", name: "Meera", does: "Owns style, reviews and watches pipeline health" },
  { role: "publisher", name: "Rahul", does: "Exports approved drafts as Markdown or merge requests" },
];

export default function Login() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function demo(role: string) {
    setToken(`demo:${role}`);
    try { await api("/api/me"); router.push("/jobs"); }
    catch (e) { setToken(null); setError(`Could not sign in as a demo user: ${(e as Error).message}`); }
  }

  async function supabaseLogin(ev: FormEvent) {
    ev.preventDefault();
    setError(null);
    const res = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
      method: "POST", headers: { apikey: SUPABASE_KEY!, "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) { setError(data.error_description || data.msg || "Sign-in failed. Check your email and password."); return; }
    setToken(data.access_token);
    router.push("/jobs");
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6 py-12">
      <h1 className="text-3xl font-semibold leading-tight">Turn merge requests into reviewed documentation</h1>
      <p className="mt-3 max-w-[60ch] text-ink-soft">
        Upload a diff, an API spec or release notes. Six agents draft and fact-check the content, and nothing is
        published until a reviewer approves it.
      </p>

      {SUPABASE_URL ? (
        <form onSubmit={supabaseLogin} className="mt-10 max-w-sm space-y-4">
          <Field label="Email"><input className={inputClass} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Password"><input className={inputClass} type="password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <ErrorNote error={error} />
          <Button type="submit">Sign in</Button>
        </form>
      ) : (
        <section className="mt-10">
          <h2 className="text-sm font-medium text-ink-soft">Sign in as a demo user</h2>
          <ul className="mt-3 divide-y divide-line rounded-lg border border-line bg-sheet">
            {DEMO.map((d) => (
              <li key={d.role}>
                <button onClick={() => demo(d.role)} className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left hover:bg-paper">
                  <span>
                    <span className="block font-medium">{d.name}</span>
                    <span className="block text-sm text-ink-soft">{d.does}</span>
                  </span>
                  <span className="text-sm text-accent">Sign in</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-4"><ErrorNote error={error} /></div>
        </section>
      )}
    </div>
  );
}
