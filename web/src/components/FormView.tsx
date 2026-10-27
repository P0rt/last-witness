import { useEffect, useState } from "react";
import { api } from "../api";
import type { Investigation, Meta } from "../types";

export default function FormView(props: {
  inv: Investigation; meta: Meta; setInv: (i: Investigation) => void; onCite: (a: string, s?: string) => void;
}) {
  const { inv, meta, setInv } = props;
  const [answers, setAnswers] = useState<Record<string, string>>(inv.form_player);
  const [progress, setProgress] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const closed = inv.status === "revealed";

  useEffect(() => { setAnswers(inv.form_player); }, [inv.form_player]);

  const choose = async (qid: string, opt: string) => {
    const next = { ...answers, [qid]: opt };
    setAnswers(next);
    setInv({ ...inv, form_player: next }); // the Reveal gate counts these
    await api.formPlayer(inv.id, next).catch((e) => setErr(e.message));
  };

  const askGemma = async () => {
    setErr(null);
    try {
      for (const [i, q] of meta.questions.entries()) {
        setProgress(`${meta.model} is answering ${i + 1}/${meta.questions.length}…`);
        await api.formAi(inv.id, q.id);
      }
      setInv(await api.get(inv.id));
    } catch (e) { setErr((e as Error).message); } finally { setProgress(null); }
  };

  const aiDone = Object.keys(inv.form_ai).length;
  return (
    <main className="page">
      <div className="page-head">
        <h2>Reconstruction</h2>
        <p className="dim">Answer what you can. “Cannot be determined” is a real answer, and sometimes the right one.
          The investigator fills in the same form from the same documents. Its answers stay sealed until Reveal,
          so it can't copy you, and you can't copy it.</p>
        {!closed && (
          <button className="primary" onClick={askGemma} disabled={!!progress}>
            {progress ?? (aiDone ? `Ask ${meta.model} again (${aiDone}/10 sealed)` : `Ask ${meta.model} to fill in the form`)}
          </button>
        )}
        {err && <p className="error">{err}</p>}
      </div>
      <ol className="form">
        {meta.questions.map((q) => (
          <li key={q.id} className="fq">
            <div className="fq-text"><span className="mono dim">{q.id}</span> {q.text}
              {inv.form_ai[q.id] && <span className="sealed" title="The investigator's answer is sealed until Reveal">● sealed</span>}
            </div>
            <div className="opts" role="radiogroup" aria-label={q.text}>
              {Object.entries(q.options).map(([k, label]) => (
                <label key={k} className={`opt ${answers[q.id] === k ? "on" : ""} ${k === "unknown" ? "unk" : ""}`}>
                  <input type="radio" name={q.id} disabled={closed} checked={answers[q.id] === k} onChange={() => choose(q.id, k)} />
                  {label}
                </label>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </main>
  );
}
