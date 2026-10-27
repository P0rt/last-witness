import { replay } from "./replay";
import type {
  Artifact, ArtifactSummary, Claim, Evaluation, FormAnswer, HypothesisAssessment, Investigation, Meta, Missing,
  TimelineEvent,
} from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not json */ }
    throw new Error(detail);
  }
  return r.json();
}

const post = <T,>(path: string, body?: unknown) =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const live = {
  isReplay: false as const,
  recordedQuestions: async () => [] as string[],
  reset: () => {},
  meta: () => call<Meta>("/meta"),
  artifacts: () => call<{ artifacts: ArtifactSummary[]; missing: Missing[] }>("/artifacts"),
  artifact: (id: string) => call<Artifact>(`/artifacts/${id}`),
  search: (q: string) =>
    call<{ results: Array<{ artifact: string; sentence: string; snippet: string }> }>(`/search?q=${encodeURIComponent(q)}`),

  create: () => post<Investigation>("/investigations"),
  get: (id: string) => call<Investigation>(`/investigations/${id}`),
  open: (id: string, artifact: string, source = false) =>
    post<{ discovered: string[]; source_viewed: string[] }>(`/investigations/${id}/open`, { artifact, source }),
  ask: (id: string, question: string) =>
    post<{ answer: string; claims: Claim[]; unresolved_questions: string[] }>(`/investigations/${id}/ask`, { question }),
  object: (id: string, claim: string) => post<Claim>(`/investigations/${id}/claims/${claim}/objection`),
  hypotheses: (id: string) =>
    post<Array<{ after_documents: number; hypotheses: HypothesisAssessment[] }>>(`/investigations/${id}/hypotheses`),
  timeline: (id: string) => post<TimelineEvent[]>(`/investigations/${id}/timeline`),
  formAi: (id: string, q: string) => post<FormAnswer>(`/investigations/${id}/form/ai/${q}`),
  formPlayer: (id: string, answers: Record<string, string>) =>
    call<Record<string, string>>(`/investigations/${id}/form/player`, { method: "PUT", body: JSON.stringify({ answers }) }),
  reveal: (id: string) => post<Evaluation>(`/investigations/${id}/reveal`),
};


export const IS_REPLAY = import.meta.env.MODE === "replay";
export const api: typeof live = IS_REPLAY ? (replay as unknown as typeof live) : live;
