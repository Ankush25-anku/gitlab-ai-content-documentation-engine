"use client";

import type { AgentRun, JobStatus } from "@/lib/types";

/** The pipeline graph: six agent stages plus the human gate, drawn like a CI pipeline. */
export const STAGES = [
  { key: "context", label: "Context Reader", status: "CONTEXT_PREPARING" },
  { key: "draft", label: "Documentation Writer", status: "DRAFTING" },
  { key: "tech_review", label: "Technical Reviewer", status: "TECH_REVIEW" },
  { key: "tone", label: "Tone Optimizer", status: "TONE_OPTIMIZING" },
  { key: "structure", label: "Structure Optimizer", status: "STRUCTURE_OPTIMIZING" },
  { key: "review", label: "Human review", status: "IN_REVIEW" },
  { key: "publish_prep", label: "Publishing Coordinator", status: "PUBLISH_PREPARING" },
] as const;

type State = "done" | "running" | "failed" | "waiting" | "blocked" | "pending";

const ORDER = ["INTAKE", "CONTEXT_PREPARING", "CONTEXT_READY", "NEEDS_INPUT", "DRAFTING", "TECH_REVIEW",
  "TONE_OPTIMIZING", "STRUCTURE_OPTIMIZING", "IN_REVIEW", "REVISION_REQUESTED", "REJECTED", "APPROVED",
  "PUBLISH_PREPARING", "PUBLISH_READY", "EXPORTED"];

function stateFor(key: string, status: JobStatus, current: string | null, runs: AgentRun[]): State {
  const lastRun = [...runs].reverse().find((r) => r.stage === key);
  if (status === "FAILED" && current === key) return "failed";
  const stage = STAGES.find((s) => s.key === key)!;
  if (status === stage.status && key !== "review") return "running";
  if (key === "review") {
    if (["IN_REVIEW", "REVISION_REQUESTED", "REJECTED"].includes(status)) return "waiting";
    if (ORDER.indexOf(status) > ORDER.indexOf("REJECTED")) return "done";
    return "pending";
  }
  if (key === "context" && status === "NEEDS_INPUT") return "blocked";
  if (lastRun?.status === "succeeded") return "done";
  return "pending";
}

const DOT: Record<State, string> = {
  done: "bg-good border-good text-white",
  running: "bg-accent-soft border-accent text-accent animate-pulse",
  failed: "bg-bad border-bad text-white",
  waiting: "bg-warn-soft border-warn text-warn",
  blocked: "bg-warn-soft border-warn text-warn",
  pending: "bg-sheet border-line-strong text-ink-faint",
};
const GLYPH: Record<State, string> = { done: "✓", running: "•", failed: "!", waiting: "?", blocked: "!", pending: "" };
const WORD: Record<State, string> = { done: "Done", running: "Running", failed: "Failed", waiting: "Waiting for you",
  blocked: "Needs input", pending: "Not started" };

export default function StageRail({ status, current, runs, onSelect, selected }: {
  status: JobStatus; current: string | null; runs: AgentRun[]; onSelect?: (key: string) => void; selected?: string | null;
}) {
  return (
    <ol className="flex w-full overflow-x-auto pb-1" aria-label="Workflow stages">
      {STAGES.map((s, i) => {
        const st = stateFor(s.key, status, current, runs);
        const run = [...runs].reverse().find((r) => r.stage === s.key && r.status === "succeeded");
        const isGate = s.key === "review";
        return (
          <li key={s.key} className="relative flex min-w-[118px] flex-1 flex-col items-center text-center">
            {i > 0 && <span aria-hidden className={`absolute top-[15px] right-1/2 h-[2px] w-full ${st === "pending" ? "bg-line" : "bg-good/60"}`} />}
            <button type="button" onClick={() => onSelect?.(s.key)} disabled={!onSelect}
              className={`relative z-10 flex h-8 w-8 items-center justify-center border-2 text-sm font-semibold ${isGate ? "rotate-45 rounded-sm" : "rounded-full"} ${DOT[st]} ${selected === s.key ? "ring-2 ring-accent ring-offset-2" : ""}`}
              aria-label={`${s.label}: ${WORD[st]}`}>
              <span className={isGate ? "-rotate-45" : ""}>{GLYPH[st]}</span>
            </button>
            <span className="mt-2 text-xs font-medium leading-tight text-ink">{s.label}</span>
            <span className="text-[11px] text-ink-faint">
              {st === "done" && run ? (run.latency_ms < 1000 ? `${run.latency_ms} ms` : `${(run.latency_ms / 1000).toFixed(1)} s`) : WORD[st]}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
