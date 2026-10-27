import type { Citation, Klass } from "../types";

export function Cite({ c, onCite }: { c: Citation; onCite: (artifact: string, sentence?: string) => void }) {
  const [artifact, sentence] = c.sentence_id.split(":");
  if (!c.valid) {
    return (
      <span className="cite bad" title={`${c.reason}: “${c.quote}”`}>
        <s>{c.sentence_id}</s>
      </span>
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
