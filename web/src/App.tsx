import { useCallback, useEffect, useMemo, useState } from "react";
import { api, IS_REPLAY } from "./api";
import type { ArtifactSummary, Evaluation, Investigation, Meta, Missing } from "./types";
import ArchivePanel from "./components/ArchivePanel";
import Viewer from "./components/Viewer";
import InvestigatorPanel from "./components/InvestigatorPanel";
import TimelineView from "./components/TimelineView";
import HypothesesView from "./components/HypothesesView";
import FormView from "./components/FormView";
import RevealView from "./components/RevealView";
import Intro from "./components/Intro";

export type Tab = "investigate" | "timeline" | "hypotheses" | "reconstruct" | "reveal";
export interface Focus { artifact: string; sentence?: string }

const KEY = "lw.investigation";

function load(): string | null {
  try { return localStorage.getItem(KEY); } catch { return null; }
}
function remember(id: string | null) {
  try { id ? localStorage.setItem(KEY, id) : localStorage.removeItem(KEY); } catch { /* private mode */ }
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [list, setList] = useState<ArtifactSummary[]>([]);
  const [missing, setMissing] = useState<Missing[]>([]);
  const [inv, setInv] = useState<Investigation | null>(null);
  const [focus, setFocus] = useState<Focus | null>(null);
  const [tab, setTab] = useState<Tab>("investigate");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState<boolean>(!!load());

  useEffect(() => {
    Promise.all([api.meta(), api.artifacts()])
      .then(([m, a]) => { setMeta(m); setList(a.artifacts); setMissing(a.missing); })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  const begin = useCallback(async () => {
    const saved = load();
    let state: Investigation | null = null;
    if (saved) state = await api.get(saved).catch(() => null);
    if (!state) state = await api.create();
    remember(state.id);
    setInv(state);
    setStarted(true);
    setFocus({ artifact: state.discovered[0] });
    if (state.status === "revealed") {
      setEvaluation(await api.reveal(state.id));
      setTab("reveal");
    }
  }, []);

  useEffect(() => { if (started && !inv) begin().catch((e) => setError(e.message)); }, [started, inv, begin]);

  const refresh = useCallback(async () => { if (inv) setInv(await api.get(inv.id)); }, [inv]);

  const openArtifact = useCallback(async (artifact: string, sentence?: string) => {
    setFocus({ artifact, sentence });
    setTab("investigate");
    if (inv && !inv.discovered.includes(artifact)) {
      const r = await api.open(inv.id, artifact);
      setInv({ ...inv, ...r });
    }
  }, [inv]);

  const viewSource = useCallback(async (artifact: string) => {
    if (inv && !inv.source_viewed.includes(artifact)) {
      const r = await api.open(inv.id, artifact, true);
      setInv({ ...inv, ...r });
    }
  }, [inv]);

  const restart = useCallback(async () => {
    if (!confirm("Start a new investigation? The current one stays on the server but you will lose your place.")) return;
    remember(null);
    api.reset();
    setInv(null); setEvaluation(null); setTab("investigate"); setFocus(null);
  }, []);

  const byId = useMemo(() => Object.fromEntries(list.map((a) => [a.id, a])), [list]);

  if (error) return <div className="fatal">The archive could not be opened: {error}</div>;
  if (!meta) return <div className="fatal dim">Mounting tape BEACON FULL 17-OCT-99…</div>;
  if (!started) return <Intro meta={meta} onStart={() => setStarted(true)} />;
  if (!inv) return <div className="fatal dim">Opening case file…</div>;

  const revealed = inv.status === "revealed";
  const tabs: Array<[Tab, string]> = [
    ["investigate", "Investigate"], ["timeline", "Timeline"], ["hypotheses", "Hypotheses"],
    ["reconstruct", "Reconstruction"], ["reveal", revealed ? "The truth" : "Reveal"],
  ];

  return (
    <div className="app">
      <header className="top">
        <div className="brand">LAST WITNESS<span className="sub">the Lighthouse Network, 1997–1999</span></div>
        <nav className="tabs" role="tablist">
          {tabs.map(([t, label]) => (
            <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="status">
          <span title="Documents the investigator can see">{inv.discovered.length}/{meta.meta.recovered} opened</span>
          <span className="model" title="Local open-weight model">{meta.model}</span>
          <button className="link" onClick={restart}>new case</button>
        </div>
      </header>

      {IS_REPLAY && (
        <div className="replay-bar">
          Replay of a recorded run: every investigator answer here was produced by <b>{meta.model}</b> running locally
          {(meta as Meta & { recorded?: { at: string } }).recorded ? ` (${(meta as Meta & { recorded: { at: string } }).recorded.at})` : ""}.
          This static version ships the truth in its files. <a href="https://github.com/P0rt/last-witness">Run it yourself</a> to ask your own questions. <a href="https://youtu.be/cc44d7dajxM" target="_blank" rel="noreferrer">Watch the video</a>.
        </div>
      )}
      {tab === "investigate" && (
        <main className="workspace">
          <ArchivePanel list={list} missing={missing} inv={inv} focus={focus} onOpen={openArtifact} />
          <Viewer focus={focus} byId={byId} inv={inv} onOpen={openArtifact} onViewSource={viewSource} missing={missing} />
          <InvestigatorPanel inv={inv} setInv={setInv} byId={byId} onCite={openArtifact} revealed={revealed} />
        </main>
      )}
      {tab === "timeline" && <TimelineView inv={inv} setInv={setInv} onCite={openArtifact} evaluation={evaluation} />}
      {tab === "hypotheses" && <HypothesesView inv={inv} meta={meta} refresh={refresh} onCite={openArtifact} />}
      {tab === "reconstruct" && <FormView inv={inv} meta={meta} setInv={setInv} onCite={openArtifact} />}
      {tab === "reveal" && (
        <RevealView inv={inv} evaluation={evaluation} byId={byId} onCite={openArtifact}
          onReveal={async () => { const ev = await api.reveal(inv.id); setEvaluation(ev); await refresh(); }} />
      )}
    </div>
  );
}
