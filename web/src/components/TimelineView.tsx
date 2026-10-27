import { useState } from "react";
import { api } from "../api";
import type { Evaluation, Investigation, TimelineEvent } from "../types";
import { Badge, Cites } from "./Cite";

export default function TimelineView(props: {
  inv: Investigation; setInv: (i: Investigation) => void; onCite: (a: string, s?: string) => void;
  evaluation: Evaluation | null;
}) {
  const { inv, setInv, onCite, evaluation } = props;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "observed" | "inferred">("all");
  const events: TimelineEvent[] = evaluation?.timeline.events ?? inv.timeline ?? [];

  const build = async () => {
    setBusy(true); setErr(null);
    try { await api.timeline(inv.id); setInv(await api.get(inv.id)); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const shown = events.filter((e) => filter === "all" || e.classification === filter);
  return (
    <main className="page">
      <div className="page-head">
        <h2>Timeline</h2>
        <p className="dim">The investigator dates what it can from the {inv.discovered.length} documents you have opened.
          A <span className="mono">~</span> marks a date it had to estimate.</p>
        <div className="row">
          {inv.status === "open" && <button className="primary" onClick={build} disabled={busy}>
            {busy ? "Reconstructing…" : inv.timeline ? "Rebuild from current evidence" : "Reconstruct timeline"}</button>}
          <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} aria-label="Filter">
            <option value="all">all events</option><option value="observed">observed only</option><option value="inferred">inferred only</option>
          </select>
        </div>
        {err && <p className="error">{err}</p>}
      </div>
      <ol className="timeline">
        {shown.map((e, i) => (
          <li key={i} className={`tl ${e.status ?? ""} ${e.ghost ? "ghost" : ""}`}>
            <span className="tl-date mono">{e.date_is_certain ? "" : "~"}{e.date}</span>
            <span className="tl-dot" />
            <div className="tl-body">
              <div>{e.description}</div>
              <div className="tl-meta"><Badge k={e.classification} /> <Cites list={e.citations} onCite={onCite} />
                {e.status === "ghost" && <span className="ghost-tag">ghost: no surviving evidence</span>}
                {e.status === "confirmed" && <span className="ok-tag">confirmed</span>}
              </div>
            </div>
          </li>
        ))}
        {evaluation?.timeline.missed.map((m) => (
          <li key={m.id} className="tl missed">
            <span className="tl-date mono">{m.date}</span><span className="tl-dot" />
            <div className="tl-body">
              <div>{m.event}</div>
              <div className="tl-meta"><span className="missed-tag">missed</span>
                <span className="dim"> the evidence survived in </span>
                {m.evidence.map((a) => <button key={a} className="cite" onClick={() => onCite(a)}>{a}</button>)}
              </div>
            </div>
          </li>
        ))}
      </ol>
      {!events.length && !busy && <p className="dim center">No timeline yet.</p>}
    </main>
  );
}
