import { useEffect, useRef, useState } from "react";
import { api, IS_REPLAY } from "../api";
import type { ArtifactSummary, Claim, Investigation } from "../types";
import { Badge, Cites } from "./Cite";

const STARTERS = [
  "Why did the Lighthouse Network disappear?",
  "What is the Cape Sorrow recording?",
  "Which documents contradict each other?",
  "Who had administrator access?",
];

export default function InvestigatorPanel(props: {
  inv: Investigation; setInv: (i: Investigation) => void; byId: Record<string, ArtifactSummary>;
  onCite: (a: string, s?: string) => void; revealed: boolean;
}) {
  const { inv, setInv, onCite, revealed } = props;
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const claims = Object.fromEntries(inv.claims.map((c) => [c.id, c]));

  const [recorded, setRecorded] = useState<string[]>([]);
  useEffect(() => { if (IS_REPLAY) api.recordedQuestions().then(setRecorded); }, []);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [inv.messages.length, busy]);
  const asked = new Set(inv.messages.flatMap((m) => (m.role === "player" ? [m.text] : [])));

  const ask = async (text: string) => {
    if (!text.trim() || busy) return;
    setBusy("Reading the evidence…"); setErr(null); setQ("");
    try {
      await api.ask(inv.id, text);
      setInv(await api.get(inv.id));
    } catch (e) {
      setErr((e as Error).message); setQ(text);
    } finally { setBusy(null); }
  };

  const object = async (c: Claim) => {
    setBusy(`Objection to “${c.text.slice(0, 40)}…”`); setErr(null);
    try {
      await api.object(inv.id, c.id);
      setInv(await api.get(inv.id));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };

  return (
    <aside className="panel investigator" aria-label="Investigator">
      <div className="inv-head">
        <span>INVESTIGATOR</span>
        <span className="dim mono">sees {inv.discovered.length} document{inv.discovered.length === 1 ? "" : "s"}
          {inv.source_viewed.length ? ` + ${inv.source_viewed.length} page source` : ""}</span>
      </div>
      <div className="chat">
        {inv.messages.length === 0 && (
          <div className="hint">
            <p>I only know what you have opened. Open files on the left, then ask me about them.</p>
            <p>Every claim I make cites the exact sentence it rests on. If you doubt one, press <b>Objection</b>.</p>
          </div>
        )}
        {inv.messages.map((m, i) => m.role === "player" ? (
          <div key={i} className="msg player">{m.text}</div>
        ) : (
          <div key={i} className="msg ai">
            <p className="answer">{m.answer}</p>
            <ul className="claims">
              {m.claims.map((cid) => claims[cid]).filter(Boolean).map((c) => (
                <ClaimRow key={c.id} c={c} onCite={onCite} onObject={revealed || IS_REPLAY ? undefined : () => object(c)} />
              ))}
            </ul>
            {m.unresolved_questions.length > 0 && (
              <div className="open-q"><span className="dim">still open:</span> {m.unresolved_questions.join(" · ")}</div>
            )}
          </div>
        ))}
        {busy && <div className="msg ai busy"><span className="blink">▌</span> {busy}</div>}
        {err && <div className="msg error">The investigator could not answer: {err}</div>}
        <div ref={end} />
      </div>
      {!revealed && IS_REPLAY && (
        <div className="starters replay-qs">
          <div className="dim small">Questions from the recorded run:</div>
          {recorded.filter((t) => !asked.has(t)).map((t) => <button key={t} onClick={() => ask(t)} disabled={!!busy}>{t}</button>)}
        </div>
      )}
      {!revealed && !IS_REPLAY && (
        <>
          {inv.messages.length === 0 && (
            <div className="starters">{STARTERS.map((s) => <button key={s} onClick={() => ask(s)}>{s}</button>)}</div>
          )}
          <form className="ask" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about what you've found…"
              aria-label="Question for the investigator" disabled={!!busy} />
            <button type="submit" disabled={!!busy || !q.trim()}>Ask</button>
          </form>
        </>
      )}
    </aside>
  );
}

function ClaimRow({ c, onCite, onObject }: { c: Claim; onCite: (a: string, s?: string) => void; onObject?: () => void }) {
  const last = c.history[c.history.length - 1];
  return (
    <li className={`claim ${c.ghost ? "ghost" : ""} ${c.withdrawn ? "withdrawn" : ""}`}>
      <Badge k={c.withdrawn ? "withdrawn" : c.classification} />
      <span className="ctext">{c.text}</span>
      <span className="cites"><Cites list={c.citations} onCite={onCite} /></span>
      {c.ghost && <span className="ghost-tag" title="Stated as fact, but no citation survives checking">ghost?</span>}
      {last && <div className="objection-note dim">Objection → {last.objection}. {last.explanation}</div>}
      {onObject && !c.withdrawn && c.classification !== "unknown" && (
        <button className="objection" onClick={onObject}>Objection!</button>
      )}
    </li>
  );
}
