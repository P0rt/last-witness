export type Klass = "observed" | "inferred" | "speculative" | "unknown";

export interface Sentence { id: string; text: string; hidden?: boolean }
export interface Link { href: string; target: string | null; status: "ok" | "missing" | "unknown" }

export interface ArtifactSummary {
  id: string; type: string; title: string; author: string; date: string;
  path: string; folder: string; integrity: "intact" | "partial" | "header_only";
}
export interface Artifact extends ArtifactSummary { raw: string; sentences: Sentence[]; links: Link[] }
export interface Missing { path: string; title: string; author: string; date: string }

export interface Question { id: string; text: string; options: Record<string, string> }
export interface Hypothesis { id: string; title: string }

export interface Citation { sentence_id: string; quote: string; valid: boolean; reason: string; found_at?: string | null }
export interface Claim {
  id: string; text: string; classification: Klass; citations: Citation[]; ghost: boolean;
  withdrawn?: boolean; history: Array<Partial<Claim> & { objection: string; explanation: string }>;
}
export type Message =
  | { role: "player"; text: string }
  | { role: "investigator"; answer: string; claims: string[]; unresolved_questions: string[] };

export interface TimelineEvent {
  date: string; date_is_certain: boolean; description: string; classification: Klass;
  citations: Citation[]; ghost: boolean; status?: "confirmed" | "ghost" | "unconfirmed"; matches?: string | null;
}
export interface HypothesisAssessment {
  id: string; status: string; reason: string; supporting: Citation[]; contradicting: Citation[]; would_falsify: string;
}
export interface FormAnswer {
  question: string; choice: string; classification: Klass; reasoning: string; citations: Citation[]; supported: boolean;
}

export interface Investigation {
  id: string; status: "open" | "revealed";
  discovered: string[]; source_viewed: string[];
  messages: Message[]; claims: Claim[];
  hypotheses: Array<{ after_documents: number; hypotheses: HypothesisAssessment[] }>;
  timeline: TimelineEvent[] | null;
  form_ai: Record<string, FormAnswer>; form_player: Record<string, string>;
}

export interface GradeRow {
  id: string; text: string; options: Record<string, string>; choice: string | null; answer: string;
  observable: boolean; grade: "correct" | "honest_unknown" | "missed" | "lucky" | "wrong" | "blank";
  ghost: boolean; evidence: string[];
}
export interface FormGrade { rows: GradeRow[]; accuracy: number; of: number; calibrated_unknowns: number; ghosts: number }
export interface Evaluation {
  summary: string;
  characters: Array<{ id: string; name: string; handle: string | null; role: string; truth: string; epitaph: string | null }>;
  canon: Array<{ id: string; date: string; event: string; observable: boolean; importance: string }>;
  hypotheses: Array<{ id: string; title: string; public_title: string; verdict: string; why: string }>;
  ai: FormGrade; player: FormGrade;
  timeline: { events: TimelineEvent[]; missed: Array<{ id: string; date: string; event: string; evidence: string[] }> };
  claims: { total: number; ghosts: Claim[]; unsupported_rate: number | null };
  letter: string | null;
}

export interface Meta {
  meta: { name: string; seed: number; originals: number; recovered: number; missing: number; lost_percent: number };
  questions: Question[]; hypotheses: Hypothesis[]; model: string;
}
