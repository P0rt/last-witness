import { useState } from "react";
import { api } from "../api";
import type { Investigation, Meta } from "../types";
import { Cites } from "./Cite";

const LABEL: Record<string, string> = {
  strongly_supported: "strongly supported", plausible: "plausible", weakly_supported: "weakly supported",
  contradicted: "contradicted", insufficient_evidence: "insufficient evidence",
};

export default function HypothesesView(props: {
  inv: Investigation; meta: Meta; refresh: () => Promise<void>; onCite: (a: string, s?: string) => void;
}) {
  const { inv, meta, refresh, onCite } = props;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const history = inv.hypotheses;
  const current = history[history.length - 1];

  const assess = async () => {
    setBusy(true); setErr(null);
    try { await api.hypotheses(inv.id); await refresh(); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <main className="page">
      <div className="page-head">
        <h2>Competing explanations</h2>
        <p className="dim">Qualitative statuses only: a small model's “73% likely” would be a number it made up.
          Re-assess after you find something new, and watch what changes.</p>
        {inv.status === "open" && <button className="primary" onClick={assess} disabled={busy}>
          {busy ? "Weighing the evidence…" : `Re-assess with ${inv.discovered.length} documents`}</button>}
        {err && <p className="error">{err}</p>}
      </div>
      <div className="hyps">
        {meta.hypotheses.map((h) => {
          const a = current?.hypotheses.find((x) => x.id === h.id);
          const trail = history.map((s) => s.hypotheses.find((x) => x.id === h.id)?.status).filter(Boolean) as string[];
          return (
            <section key={h.id} className={`hyp ${a?.status ?? ""}`}>
              <header><span className="mono dim">{h.id}</span> {h.title}</header>
              {a ? (
                <>
                  <div className={`status ${a.status}`}>{LABEL[a.status] ?? a.status}</div>
                  <p>{a.reason}</p>
                  <div className="evid"><span className="dim">for:</span> <Cites list={a.supporting} onCite={onCite} /></div>
                  <div className="evid"><span className="dim">against:</span> <Cites list={a.contradicting} onCite={onCite} /></div>
                  <p className="dim small">Would be falsified by: {a.would_falsify}</p>
                  {trail.length > 1 && <p className="trail mono small">history: {trail.map((t) => LABEL[t] ?? t).join(" → ")}</p>}
                </>
              ) : <p className="dim">not assessed yet</p>}
            </section>
          );
        })}
      </div>
    </main>
  );
}
