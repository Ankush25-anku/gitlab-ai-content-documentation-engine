"use client";

import { ButtonHTMLAttributes, ReactNode } from "react";
import { STATUS_LABEL } from "@/lib/api";

const TONE: Record<string, string> = {
  good: "bg-good-soft text-good", warn: "bg-warn-soft text-warn", bad: "bg-bad-soft text-bad",
  accent: "bg-accent-soft text-accent", quiet: "bg-paper text-ink-soft border border-line",
};

export function statusTone(status: string): keyof typeof TONE {
  if (["EXPORTED", "APPROVED", "PUBLISH_READY"].includes(status)) return "good";
  if (["NEEDS_INPUT", "REVISION_REQUESTED", "IN_REVIEW"].includes(status)) return "warn";
  if (["FAILED", "REJECTED"].includes(status)) return "bad";
  if (["INTAKE", "CONTEXT_READY"].includes(status)) return "quiet";
  return "accent";
}

export function Pill({ tone = "quiet", children }: { tone?: keyof typeof TONE; children: ReactNode }) {
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${TONE[tone]}`}>{children}</span>;
}

export function StatusPill({ status }: { status: string }) {
  return <Pill tone={statusTone(status)}>{STATUS_LABEL[status] ?? status}</Pill>;
}

export function Button({ variant = "primary", className = "", ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const styles = {
    primary: "bg-accent text-white hover:bg-[#3f37b0] disabled:bg-line-strong",
    secondary: "bg-sheet text-ink border border-line-strong hover:border-ink-faint disabled:text-ink-faint",
    danger: "bg-sheet text-bad border border-bad/40 hover:bg-bad-soft",
    ghost: "text-ink-soft hover:text-ink hover:bg-paper",
  }[variant];
  return <button className={`inline-flex items-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed ${styles} ${className}`} {...rest} />;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-ink">{label}</span>
      {hint && <span className="block text-xs text-ink-faint mb-1">{hint}</span>}
      <span className="mt-1 block">{children}</span>
    </label>
  );
}

export const inputClass = "w-full rounded-md border border-line-strong bg-sheet px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none";

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return <p role="alert" className="rounded-md border border-bad/30 bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>;
}

export function Percent({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-ink-faint">–</span>;
  return <>{Math.round(value * 100)}%</>;
}
