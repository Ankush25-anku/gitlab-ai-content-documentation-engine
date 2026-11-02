"use client";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "ce_token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token: string | null) {
  try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number, public details?: unknown) { super(message); }
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`${API_URL}${path}`, { ...init, headers, body });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = data?.error ?? {};
    if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/me")) {
      window.location.href = "/login";
    }
    throw new ApiError(e.code ?? "HTTP_" + res.status, e.message ?? res.statusText, res.status, e.details);
  }
  return data as T;
}

/** Server-Sent Events over fetch, so the bearer token can be sent as a header. */
export async function streamEvents(path: string, onEvent: (event: string, data: any) => void, signal: AbortSignal) {
  const res = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${getToken()}` }, signal });
  if (!res.ok || !res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const event = /event: (.*)/.exec(raw)?.[1] ?? "message";
      const data = /data: (.*)/.exec(raw)?.[1];
      if (data) onEvent(event, JSON.parse(data));
    }
  }
}

export const ROLE_LABEL: Record<string, string> = {
  creator: "Content creator", tech_reviewer: "Technical reviewer", doc_lead: "Documentation lead",
  publisher: "Publisher", admin: "Administrator",
};

export const TYPE_LABEL: Record<string, string> = {
  release_note: "Release note", docs_page: "Documentation page", blog: "Developer blog",
  api_reference: "API reference", onboarding_guide: "Onboarding guide",
};

export const STATUS_LABEL: Record<string, string> = {
  INTAKE: "New", CONTEXT_PREPARING: "Reading sources", CONTEXT_READY: "Context ready", NEEDS_INPUT: "Needs input",
  DRAFTING: "Drafting", TECH_REVIEW: "Fact-checking", TONE_OPTIMIZING: "Adjusting tone",
  STRUCTURE_OPTIMIZING: "Structuring", IN_REVIEW: "In review", REVISION_REQUESTED: "Revision requested",
  REJECTED: "Rejected", APPROVED: "Approved", PUBLISH_PREPARING: "Preparing to publish",
  PUBLISH_READY: "Ready to publish", EXPORTED: "Published", FAILED: "Failed",
};
