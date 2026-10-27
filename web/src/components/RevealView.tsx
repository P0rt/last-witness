import { useState } from "react";
import type { ArtifactSummary, Evaluation, GradeRow, Investigation } from "../types";
import { Cites } from "./Cite";

const GRADE: Record<GradeRow["grade"], [string, string]> = {
  correct: ["✓", "correct"], honest_unknown: ["✓", "honest: this cannot be known from the archive"],
  missed: ["–", "said unknown, but the evidence survived"], lucky: ["?", "right, but nothing in the archive supports it"],
  wrong: ["✗", "wrong"], blank: ["·", "not answered"],
};

export default function RevealView(props: {
  inv: Investigation; evaluation: Evaluation | null; byId: Record<string, ArtifactSummary>;
  onCite: (a: string, s?: string) => void; onReveal: () => Promise<void>;
}) {
  const { inv, evaluation: ev, onCite, onReveal } = props;
  const [busy, setBusy] = useState(false);

  if (!ev) {
    const mine = Object.keys(inv.form_player).length;
    const ai = Object.keys(inv.form_ai).length;
    return (
      <main className="page reveal-gate">
        <h2>Reveal the truth</h2>
        <p>The canonical history of the Lighthouse Network has been sealed since before the archive was destroyed.
          The investigator has never seen it. Once you open it, this investigation closes.</p>
        <ul className="mono">
          <li>your reconstruction: {mine}/10 answered</li>
          <li>investigator's reconstruction: {ai}/10 answered{ai < 10 ? " (fill it in from the Reconstruction tab)" : ""}</li>
          <li>claims made in conversation: {inv.claims.length}</li>
          <li>timeline: {inv.timeline ? `${inv.timeline.length} events` : "not built"}</li>
        </ul>
        <button className="primary big" disabled={busy} onClick={async () => { setBusy(true); await onReveal(); setBusy(false); }}>
          {busy ? "Unsealing…" : "Reveal"}
        </button>
      </main>
    );
  }

  const ai = Object.fromEntries(ev.ai.rows.map((r) => [r.id, r]));
  const ghosts = ev.claims.ghosts;
  return (
    <main className="page reveal">
      <section className="truth">
        <p className="mono dim">SEALED 1999 · OPENED {new Date().getFullYear()}</p>
        <h2>What actually happened</h2>
        <p className="summary">{ev.summary}</p>
      </section>

      <section className="score">
        <div><b>{ev.player.accuracy}/{ev.player.of}</b><span>you</span></div>
        <div><b>{ev.ai.accuracy}/{ev.ai.of}</b><span>investigator</span></div>
        <div><b>{ev.ai.calibrated_unknowns}/1</b><span>honest “unknown”</span></div>
        <div className="g"><b>{ghosts.length + ev.ai.ghosts + ev.timeline.events.filter((e) => e.status === "ghost").length}</b><span>ghosts</span></div>
      </section>

      <section>
        <h3>Truth, you, and the machine</h3>
        <table className="three">
          <thead><tr><th>question</th><th>truth</th><th>you</th><th>investigator</th></tr></thead>
          <tbody>
            {ev.player.rows.map((r) => {
              const a = ai[r.id];
              return (
                <tr key={r.id}>
                  <td><span className="mono dim">{r.id}</span> {r.text}
                    {!r.observable && <div className="dim small">The archive does not record this. The only honest answer was “cannot be determined”.</div>}</td>
                  <td className="t">{r.options[r.answer]}</td>
                  <Cell r={r} />
                  <Cell r={a} ai />
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section>
        <h3>The ghosts</h3>
        <p className="dim">Things the investigator stated as fact that nothing in the surviving archive says.
          They sounded right. That's what makes them ghosts.</p>
        {ghosts.length === 0 && ev.ai.ghosts === 0 && <p>None. Every factual claim it made could be traced to a sentence.</p>}
        <ul className="ghosts">
          {ghosts.map((c) => (
            <li key={c.id} className="ghost">“{c.text}” <span className="dim small">· <Cites list={c.citations} onCite={onCite} /></span></li>
          ))}
          {ev.ai.rows.filter((r) => r.ghost).map((r) => (
            <li key={r.id} className="ghost">{r.id}: “{r.options[r.choice ?? ""]}” <span className="dim small">· answered as fact, no surviving citation</span></li>
          ))}
        </ul>
        {ev.timeline.missed.length > 0 && (
          <>
            <h4>What it missed</h4>
            <ul className="missed-list">
              {ev.timeline.missed.map((m) => (
                <li key={m.id}><span className="mono dim">{m.date}</span> {m.event}{" "}
                  {m.evidence.map((a) => <button key={a} className="cite" onClick={() => onCite(a)}>{a}</button>)}</li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section>
        <h3>The explanations</h3>
        <div className="hyps">
          {ev.hypotheses.map((h) => (
            <div key={h.id} className={`hyp verdict-${h.verdict.replace(" ", "-")}`}>
              <header><span className="mono dim">{h.id}</span> {h.public_title}</header>
              <div className="status">{h.verdict}</div>
              <p>{h.why}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="memoriam">
        <div className="gb">
          <center>
            <h2>In memoriam</h2>
            <i>The Lighthouse Network, March 14, 1997 – October 22, 1999</i>
          </center>
          <p>Honouring the dead means not putting words in their mouths. Here is who they were, and what they actually did.</p>
          {ev.characters.filter((c) => c.epitaph).map((c) => (
            <div key={c.id} className="gb-entry">
              <b>{c.name}</b>{c.handle && <> (<code>{c.handle}</code>)</>} &mdash; {c.role}
              <div className="ep">{c.epitaph}</div>
              <div className="small">{c.truth}</div>
            </div>
          ))}
        </div>
      </section>

      {ev.letter && (
        <section className="letter">
          <h3>The letter, undamaged</h3>
          <p className="dim">The archive held this message as a few readable fragments between ▒▒▒. This is how it was written.</p>
          <pre>{ev.letter}</pre>
        </section>
      )}

      <p className="closing">AI can reconstruct the past.<br />But can it recognize what it doesn't know?</p>
    </main>
  );
}

function Cell({ r, ai }: { r?: GradeRow; ai?: boolean }) {
  if (!r || !r.choice) return <td className="dim">—</td>;
  const [mark, title] = GRADE[r.grade];
  return (
    <td className={`g-${r.grade} ${r.ghost ? "ghost" : ""}`} title={title}>
      <span className="mark">{mark}</span> {r.options[r.choice]}
      {ai && r.ghost && <div className="small">ghost</div>}
    </td>
  );
}
