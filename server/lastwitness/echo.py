"""`echo`: a no-AI stand-in so the game can be clicked through without Ollama.

It is NOT a model and never pretends to be one: it quotes the sentences that
share the most words with the question and labels everything "observed". Use it
for UI development (LW_MODEL=echo). Benchmarks refuse to run on it.
"""
from __future__ import annotations

import re

from .llm import LLM

WORD = re.compile(r"[a-z0-9']+")
STOP = set("the a an and or of to in on at is was were be it this that what who why which when how did do does i you "
           "he she they we for with from by as about any there their his her".split())


def _words(s: str) -> set[str]:
    return {w for w in WORD.findall(s.lower()) if w not in STOP and len(w) > 2}


def _sentences(messages: list[dict]) -> list[tuple[str, str]]:
    text = "\n".join(m["content"] for m in messages)
    return re.findall(r"^\[(A\d\d:[sh]\d+)\](?: \(page source\))? (.+)$", text, flags=re.M)


class Echo(LLM):
    model_id = "echo (no AI: quotes matching sentences)"

    def chat(self, messages: list[dict], schema: dict) -> dict:
        question = messages[-1]["content"].split("</archive>")[-1]
        q = _words(question)
        ranked = sorted(_sentences(messages), key=lambda s: -len(q & _words(s[1])))
        top = [s for s in ranked[:3] if q & _words(s[1])]
        cite = lambda s: {"sentence_id": s[0], "quote": s[1][:80]}  # noqa: E731
        props = schema["properties"]
        if "claims" in props:
            return {"answer": "These are the sentences that share the most words with your question. "
                              "(echo mode: no model is running.)",
                    "claims": [{"text": s[1], "classification": "observed", "citations": [cite(s)]} for s in top],
                    "unresolved_questions": ["Everything that requires reasoning: start Ollama for a real investigator."]}
        if "choice" in props:
            out = {"reasoning": "echo mode cannot reason", "choice": "unknown", "classification": "unknown"}
            if "citations" in props:
                out["citations"] = []
            return out
        if "verdict" in props:
            return {"verdict": "withdrawn", "explanation": "echo mode cannot defend claims", "revised_text": "",
                    "classification": "unknown", "citations": []}
        if "events" in props:
            dated = [s for s in _sentences(messages) if re.search(r"\b(19\d\d|\d\d/\d\d/99)\b", s[1])][:12]
            events = []
            for s in dated:
                m = re.search(r"\b(199\d)-(\d\d)-(\d\d)\b", s[1]) or re.search(r"\b(\d\d)/(\d\d)/(99)\b", s[1])
                if not m:
                    continue
                g = m.groups()
                date = f"{g[0]}-{g[1]}-{g[2]}" if len(g[0]) == 4 else f"1999-{g[0]}-{g[1]}"
                events.append({"date": date, "date_is_certain": True, "description": s[1][:120],
                               "classification": "observed", "citations": [cite(s)]})
            return {"events": events}
        if "hypotheses" in props:
            return {"hypotheses": [{"id": h, "status": "insufficient_evidence", "reason": "echo mode cannot weigh evidence",
                                    "supporting": [], "contradicting": [], "would_falsify": "-"}
                                   for h in props["hypotheses"]["items"]["properties"]["id"]["enum"]]}
        return {}
