import type { Citation, Klass } from "../types";

export function Cite({ c, onCite }: { c: Citation; onCite: (artifact: string, sentence?: string) => void }) {
  const [artifact, sentence] = c.sentence_id.split(":");
  if (!c.valid) {
    const bad = (
      <span className="cite bad" title={`${c.reason}: “${c.quote}”`}>
        <s>{c.sentence_id}</s>
      </span>
    );
    if (!c.found_at || c.found_at === c.sentence_id) return bad;
    // Real words under the wrong id: a misfiled pointer, still not valid evidence.
    const [fa, fs] = c.found_at.split(":");
    return (
      <>{bad}<button className="cite misfiled" title={`misfiled: the quote is really at ${c.found_at}`}
        onClick={() => onCite(fa, fs)}>→{c.found_at}</button></>
    );
  }
  return (
    <button className="cite" title={`“${c.quote}”`} onClick={() => onCite(artifact, sentence)}>
      {c.sentence_id}
    </button>
  );
}

export function Badge({ k }: { k: Klass | string }) {
  return <span className={`badge ${k}`}>{k}</span>;
}

export function Cites({ list, onCite }: { list: Citation[]; onCite: (a: string, s?: string) => void }) {
  if (!list.length) return <span className="dim nocite">no citation</span>;
  return <>{list.map((c, i) => <Cite key={i} c={c} onCite={onCite} />)}</>;
}
