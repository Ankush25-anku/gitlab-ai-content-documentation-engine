export type Role = "creator" | "tech_reviewer" | "doc_lead" | "publisher" | "admin";

export type JobStatus =
  | "INTAKE" | "CONTEXT_PREPARING" | "CONTEXT_READY" | "NEEDS_INPUT" | "DRAFTING" | "TECH_REVIEW"
  | "TONE_OPTIMIZING" | "STRUCTURE_OPTIMIZING" | "IN_REVIEW" | "REVISION_REQUESTED" | "REJECTED"
  | "APPROVED" | "PUBLISH_PREPARING" | "PUBLISH_READY" | "EXPORTED" | "FAILED";

export interface Me { id: string; name: string; email: string; role: Role; llm_provider: string; auth_mode: string }

export interface JobSummary {
  id: string; title: string; content_type: string; audience: string; product_area: string;
  target_channel: string; target_length: number; owner_id: string; reviewer_id: string | null;
  deadline: string | null; status: JobStatus; current_stage: string | null;
  last_error: { code: string; stage?: string; message: string; retryable?: boolean } | null;
  created_at: string; updated_at: string;
}

export interface Source {
  id: string; chunk_id: string; origin: "input" | "kb"; title: string; text: string;
  score: number | null; updated_at: string | null; stale: boolean;
}

export interface Fact { id: string; source_id: string; text: string; confidence: "high" | "medium" | "low" }

export interface ContextPack {
  id: string; version: number; sources: Source[]; warnings: string[];
  pack: { summary: string; facts: Fact[]; gaps: string[]; blocking_gaps: string[]; conflicts: string[];
    terminology: string[] } | null;
}

export interface Claim {
  id: string; claim: string; verdict: "supported" | "partial" | "unsupported"; source_ids: string[];
  fix: string | null; resolved: boolean; resolved_by: string | null; resolution_note: string | null;
}

export interface QualityScores {
  overall: number; source_coverage: number; citation_validity: number; invalid_citations: string[];
  claim_support_rate: number; unsupported_claims: number; needs_source_markers: number;
  structure_compliance: number; missing_headings: string[]; readability_avg_sentence_words: number;
  word_count: number; risk_flags?: string[]; reviewer_questions?: string[];
}

export interface DraftFull {
  id: string; job_id: string; version: number; parent_version: number | null; stage: string; created_by: string;
  content_md: string; draft: { title: string; summary: string; sections: { heading: string; body_markdown: string }[];
    reviewer_notes: string[]; change_log: string[] };
  quality_scores: QualityScores | null; review_state: string; created_at: string; claims: Claim[];
  reviews?: { id: string; reviewer_id: string; action: string; comment: string | null; created_at: string }[];
}

export interface AgentRun {
  id: string; stage: string; agent: string; status: string; attempt: number; model: string;
  prompt_version: string | null; latency_ms: number; tokens_in: number; tokens_out: number; error: string | null;
  output?: unknown; started_at: string; finished_at: string | null;
}

export interface JobDetail extends JobSummary {
  owner: { id: string; name: string } | null;
  inputs: { id: string; kind: string; filename: string; redacted: boolean; redactions: { type: string; count: number }[];
    chars: number; text: string }[];
  context_pack: ContextPack | null;
  drafts: { id: string; version: number; stage: string; created_by: string; review_state: string; created_at: string }[];
  latest_draft: DraftFull | null;
  runs: AgentRun[];
}
