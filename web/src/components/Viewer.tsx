import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Artifact, ArtifactSummary, Investigation, Missing } from "../types";
import type { Focus } from "../App";

type Mode = "page" | "text" | "source";

export default function Viewer(props: {
  focus: Focus | null; byId: Record<string, ArtifactSummary>; inv: Investigation; missing: Missing[];
  onOpen: (id: string, sentence?: string) => void; onViewSource: (id: string) => void;
}) {
  const { focus, inv, onOpen, onViewSource, missing } = props;
  const [doc, setDoc] = useState<Artifact | null>(null);
  const [mode, setMode] = useState<Mode>("text");
  const [notFound, setNotFound] = useState<string | null>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  const hl = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!focus) return;
    setNotFound(null);
    api.artifact(focus.artifact).then((a) => {
      setDoc(a);
      setMode(a.type === "html_page" && !focus.sentence ? "page" : "text");
    });
  }, [focus]);

  useEffect(() => { hl.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }, [doc, mode, focus]);

  const follow = (href: string) => {
    const link = doc?.links.find((l) => l.href === href);
    if (link?.target) onOpen(link.target);
    else setNotFound(href);
  };

  // 1999 pages render in a sandboxed frame (no scripts); we intercept their links.
  const wire = () => {
    const d = frame.current?.contentDocument;
    if (!d || !doc) return;
    d.querySelectorAll("a").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        const raw = a.getAttribute("href") ?? "";
        let target = raw.startsWith("/") ? raw : doc.path.replace(/[^/]*$/, "") + raw;
        if (target.endsWith("/")) target += "index.html";
        if (/^\/~[^/]+$/.test(target)) target += "/index.html";
        follow(target);
      });
    });
    d.querySelectorAll("img").forEach((img) => {
      const box = d.createElement("span");
      box.textContent = `[image not recovered${img.alt ? `: ${img.alt}` : ""}]`;
      box.setAttribute("style", "display:inline-block;border:1px dashed #888;padding:4px 8px;font:12px monospace;opacity:.7;margin:2px");
      img.replaceWith(box);
    });
  };

  if (!focus || !doc) return <section className="panel viewer empty">Pick a file from the tape.</section>;

  const visible = doc.sentences.filter((s) => !s.hidden);
  const hidden = doc.sentences.filter((s) => s.hidden);
  const sourceSeen = inv.source_viewed.includes(doc.id);
  const missingHit = notFound ? missing.find((m) => m.path === notFound) : null;

  return (
    <section className="panel viewer" aria-label="Document viewer">
      <div className="doc-head">
        <div className="doc-path mono">{doc.path}</div>
        <div className="doc-title">{doc.title}</div>
        <div className="doc-meta mono dim">
          <span>{doc.id}</span><span>{doc.type.replace("_", " ")}</span>
          <span>by {doc.author}</span><span>{doc.date.slice(0, 16).replace("T", " ")}</span>
          <span className={`integrity ${doc.integrity}`}>{doc.integrity.replace("_", " ")}</span>
        </div>
        <div className="modes" role="tablist">
          {doc.type === "html_page" && <button className={mode === "page" ? "on" : ""} onClick={() => setMode("page")}>Page</button>}
          <button className={mode === "text" ? "on" : ""} onClick={() => setMode("text")}>Text</button>
          {doc.type === "html_page" && (
            <button className={mode === "source" ? "on" : ""} onClick={() => { setMode("source"); onViewSource(doc.id); }}>
              View source{hidden.length > 0 && sourceSeen ? ` (${hidden.length})` : ""}
            </button>
          )}
        </div>
      </div>

      {notFound && (
        <div className="notfound mono" role="alert">
          <b>404 Not Found</b> — {notFound}
          <div className="dim">{missingHit ? `Known from the backup log${missingHit.title && !missingHit.title.startsWith("(") ? `: “${missingHit.title}”` : ""}. Its contents were not recovered.` : "Nothing on the tape matches this address."}</div>
          <button className="link" onClick={() => setNotFound(null)}>close</button>
        </div>
      )}

      <div className="doc-body">
        {mode === "page" && (
          <iframe ref={frame} title={doc.title} className="page1999" sandbox="allow-same-origin" srcDoc={doc.raw} onLoad={wire} />
        )}
        {mode === "text" && (
          <div className="sentences">
            {visible.map((s) => (
              <span key={s.id} ref={focus.sentence === s.id ? hl : undefined}
                className={`s ${focus.sentence === s.id ? "hl" : ""}`} data-sid={`${doc.id}:${s.id}`}>
                <span className="sid">{s.id}</span>{s.text}
              </span>
            ))}
            {hidden.length > 0 && sourceSeen && (
              <div className="hidden-layer">
                <div className="dim mono">page source</div>
                {hidden.map((s) => (
                  <span key={s.id} ref={focus.sentence === s.id ? hl : undefined} className={`s src ${focus.sentence === s.id ? "hl" : ""}`}>
                    <span className="sid">{s.id}</span>{s.text}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
        {mode === "source" && (
          <>
            <p className="note">{hidden.length
              ? `You found ${hidden.length} line${hidden.length > 1 ? "s" : ""} a browser never shows. The investigator can now read ${hidden.length > 1 ? "them" : "it"} too.`
              : "Nothing hidden in this page's source."}</p>
            <pre className="source">{highlightSource(doc.raw)}</pre>
          </>
        )}
      </div>

      {doc.links.length > 0 && (
        <div className="links">
          <span className="dim mono">links:</span>
          {doc.links.map((l) => (
            <button key={l.href} className={`lnk ${l.status}`} onClick={() => follow(l.href)}>
              {l.href}{l.status !== "ok" && <span className="dim"> · 404</span>}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function highlightSource(raw: string) {
  const parts = raw.split(/(<!--[\s\S]*?-->|alt="[^"]*"|content="[^"]*")/g);
  return parts.map((p, i) => (i % 2 ? <mark key={i} className="srcmark">{p}</mark> : p));
}
