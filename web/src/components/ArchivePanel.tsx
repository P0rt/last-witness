import { useMemo, useState } from "react";
import { api } from "../api";
import type { ArtifactSummary, Investigation, Missing } from "../types";
import type { Focus } from "../App";

const FOLDERS: Array<[string, string]> = [
  ["www", "/ (site root)"], ["forum", "/forum"], ["logbook", "/logbook"], ["signals", "/signals"],
  ["users", "/~users"], ["guestbook", "/guestbook"], ["mail", "/mail"], ["logs", "/logs"], ["new-server", "/colo (new server)"],
];

function folderOf(path: string) {
  if (path.startsWith("/~")) return "users";
  if (path.startsWith("/colo/")) return "new-server";
  const parts = path.replace(/^\//, "").split("/");
  return parts.length > 1 ? parts[0] : "www";
}

export default function ArchivePanel(props: {
  list: ArtifactSummary[]; missing: Missing[]; inv: Investigation; focus: Focus | null;
  onOpen: (id: string, sentence?: string) => void;
}) {
  const { list, missing, inv, focus, onOpen } = props;
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Array<{ artifact: string; sentence: string; snippet: string }> | null>(null);
  const [showMissing, setShowMissing] = useState(false);
  const [open, setOpen] = useState<Record<string, boolean>>({ www: true });

  const grouped = useMemo(() => {
    const g: Record<string, Array<{ kind: "file"; a: ArtifactSummary } | { kind: "missing"; m: Missing }>> = {};
    for (const a of list) (g[a.folder] ??= []).push({ kind: "file", a });
    if (showMissing) for (const m of missing) (g[folderOf(m.path)] ??= []).push({ kind: "missing", m });
    for (const k of Object.keys(g)) g[k].sort((x, y) =>
      (x.kind === "file" ? x.a.path : x.m.path).localeCompare(y.kind === "file" ? y.a.path : y.m.path));
    return g;
  }, [list, missing, showMissing]);

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!q.trim()) { setResults(null); return; }
    setResults((await api.search(q)).results);
  };
  const byId = Object.fromEntries(list.map((a) => [a.id, a]));

  return (
    <aside className="panel archive" aria-label="Recovered archive">
      <form onSubmit={search} className="search">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="grep the tape…" aria-label="Search the archive" />
      </form>
      {results && (
        <div className="results">
          <div className="results-head"><span>{results.length} hits</span><button className="link" onClick={() => setResults(null)}>clear</button></div>
          {results.map((r, i) => (
            <button key={i} className="hit" onClick={() => onOpen(r.artifact, r.sentence === "title" ? undefined : r.sentence)}>
              <span className="mono dim">{byId[r.artifact]?.path}</span>
              <span dangerouslySetInnerHTML={{ __html: escape(r.snippet).replace(/\[/g, "<mark>").replace(/\]/g, "</mark>") }} />
            </button>
          ))}
        </div>
      )}
      <div className="tree">
        {FOLDERS.filter(([k]) => grouped[k]).map(([k, label]) => (
          <div key={k} className="folder">
            <button className="folder-name" aria-expanded={!!open[k]} onClick={() => setOpen({ ...open, [k]: !open[k] })}>
              {open[k] ? "▾" : "▸"} {label} <span className="dim">{grouped[k].filter((x) => x.kind === "file").length}</span>
            </button>
            {open[k] && grouped[k].map((x) => x.kind === "file" ? (
              <button key={x.a.id} className={`file ${focus?.artifact === x.a.id ? "on" : ""} ${inv.discovered.includes(x.a.id) ? "seen" : ""}`}
                onClick={() => onOpen(x.a.id)} title={x.a.title}>
                <span className="fname">{shortName(x.a.path, k)}</span>
                {x.a.integrity !== "intact" && <span className="dmg" title={x.a.integrity}>▒</span>}
                {!inv.discovered.includes(x.a.id) && <span className="new" aria-label="unopened">•</span>}
              </button>
            ) : (
              <div key={x.m.path} className="file missing" title="Not recovered">
                <span className="fname">{shortName(x.m.path, k)}</span><span className="dim">404</span>
              </div>
            ))}
          </div>
        ))}
      </div>
      <label className="toggle">
        <input type="checkbox" checked={showMissing} onChange={(e) => setShowMissing(e.target.checked)} />
        show {missing.length} files that were not recovered
      </label>
    </aside>
  );
}

function shortName(path: string, folder: string) {
  const parts = path.split("/").filter(Boolean);
  if (folder === "users") return parts.join("/");
  if (folder === "forum" || folder === "mail") return parts.slice(1).join("/");
  return parts.slice(-1)[0] || path;
}

function escape(s: string) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
}
