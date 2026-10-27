// Static replay: the whole game from files, no server and no model.
// Every investigator answer was recorded from a real local model run
// (scripts/record_replay.py). The truth ships in this bundle; the live game keeps it sealed.
import type {
  Artifact, ArtifactSummary, Claim, Evaluation, FormAnswer, GradeRow, Investigation, Meta, Missing,
} from "./types";

interface Sealed {
  evaluation: Evaluation;
  key: Record<string, { answer: string; observable: boolean; evidence: string[] }>;
}
interface Local { discovered: string[]; source_viewed: string[]; asked: number; form_player: Record<string, string>; revealed: boolean }

const KEY = "lw.replay";
const cache: Record<string, Promise<any>> = {};
const file = <T,>(name: string): Promise<T> =>
  (cache[name] ??= fetch(`replay/${name}`).then((r) => {
    if (!r.ok) throw new Error(`replay/${name} is missing`);
    return r.json();
  }));

function local(): Local {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? "");
    if (s && Array.isArray(s.discovered)) return s;
  } catch { /* fresh */ }
  return { discovered: [], source_viewed: [], asked: 0, form_player: {}, revealed: false };
}
function save(s: Local) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* private mode */ } }

async function session(): Promise<Investigation> { return file<Investigation>("session.json"); }

async function view(): Promise<Investigation> {
  const rec = await session();
  const s = local();
  if (!s.discovered.length) {
    const arch = await file<{ artifacts: Artifact[] }>("artifacts.json");
    s.discovered = [arch.artifacts.find((a) => a.path === "/RECOVERY_NOTES.txt")!.id];
    save(s);
  }
  const msgs = rec.messages.slice(0, s.asked * 2);
  const shownClaims = new Set(msgs.flatMap((m) => (m.role === "investigator" ? m.claims : [])));
  return {
    ...rec,
    id: "replay",
    status: s.revealed ? "revealed" : "open",
    discovered: s.discovered,
    source_viewed: s.source_viewed,
    messages: msgs,
    claims: rec.claims.filter((c) => shownClaims.has(c.id)),
    form_player: s.form_player,
  };
}

function grade(key: Sealed["key"][string], choice: string | undefined): GradeRow["grade"] {
  if (!choice) return "blank";
  if (!key.observable) return choice === "unknown" ? "honest_unknown" : choice === key.answer ? "lucky" : "wrong";
  if (choice === key.answer) return "correct";
  return choice === "unknown" ? "missed" : "wrong";
}

export const replay = {
  isReplay: true as const,
  recordedQuestions: async () => {
    const rec = await session();
    return rec.messages.filter((m) => m.role === "player").map((m) => (m as { text: string }).text);
  },
  meta: () => file<Meta & { recorded: { model: string; at: string; minutes: number } }>("meta.json"),
  artifacts: async () => {
    const a = await file<{ artifacts: Artifact[]; missing: Missing[] }>("artifacts.json");
    const list: ArtifactSummary[] = a.artifacts.map(({ raw: _r, sentences: _s, links: _l, ...rest }) => rest);
    return { artifacts: list, missing: a.missing };
  },
  artifact: async (id: string) => {
    const a = await file<{ artifacts: Artifact[] }>("artifacts.json");
    const found = a.artifacts.find((x) => x.id === id);
    if (!found) throw new Error("not recovered");
    return found;
  },
  search: async (q: string) => {
    const a = await file<{ artifacts: Artifact[] }>("artifacts.json");
    const terms = q.toLowerCase().split(/\W+/).filter(Boolean);
    const results = [];
    for (const art of a.artifacts) for (const s of art.sentences) {
      if (s.hidden) continue;
      const t = s.text.toLowerCase();
      if (terms.every((w) => t.includes(w))) {
        let snip = s.text;
        for (const w of terms) snip = snip.replace(new RegExp(`(${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "ig"), "[$1]");
        results.push({ artifact: art.id, sentence: s.id, snippet: snip });
      }
    }
    return { results: results.slice(0, 50) };
  },
  create: view,
  get: (_id: string) => view(),
  open: async (_id: string, artifact: string, source = false) => {
    const s = local();
    if (!s.discovered.includes(artifact)) s.discovered.push(artifact);
    if (source && !s.source_viewed.includes(artifact)) s.source_viewed.push(artifact);
    save(s);
    return { discovered: s.discovered, source_viewed: s.source_viewed };
  },
  ask: async (_id: string, question: string) => {
    const rec = await session();
    const players = rec.messages.filter((m) => m.role === "player");
    const idx = players.findIndex((m) => (m as { text: string }).text === question);
    if (idx < 0) throw new Error("In the replay you can only ask the questions from the recorded run.");
    const s = local();
    s.asked = Math.max(s.asked, idx + 1);
    save(s);
    await new Promise((r) => setTimeout(r, 900)); // the tape spins
    const m = rec.messages[idx * 2 + 1] as Extract<Investigation["messages"][number], { role: "investigator" }>;
    return { answer: m.answer, claims: rec.claims.filter((c) => m.claims.includes(c.id)), unresolved_questions: m.unresolved_questions };
  },
  object: async (_id: string, claim: string): Promise<Claim> => {
    const rec = await session();
    return rec.claims.find((c) => c.id === claim)!;
  },
  hypotheses: async (_id: string) => (await session()).hypotheses,
  timeline: async (_id: string) => (await session()).timeline ?? [],
  formAi: async (_id: string, q: string): Promise<FormAnswer> => (await session()).form_ai[q],
  formPlayer: async (_id: string, answers: Record<string, string>) => {
    const s = local(); s.form_player = answers; save(s); return answers;
  },
  reveal: async (_id: string): Promise<Evaluation> => {
    const sealed = await file<Sealed>("sealed.json");
    const s = local(); s.revealed = true; save(s);
    const rows: GradeRow[] = sealed.evaluation.ai.rows.map((r) => {
      const choice = s.form_player[r.id] ?? null;
      return { ...r, choice, grade: grade(sealed.key[r.id], choice ?? undefined), ghost: false };
    });
    const observable = rows.filter((r) => r.observable);
    const player = {
      rows, of: observable.length,
      accuracy: observable.filter((r) => r.grade === "correct").length,
      calibrated_unknowns: rows.filter((r) => r.grade === "honest_unknown").length, ghosts: 0,
    };
    return { ...sealed.evaluation, player };
  },
  reset: () => { try { localStorage.removeItem(KEY); } catch { /* ignore */ } },
};
