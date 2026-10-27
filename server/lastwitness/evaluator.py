"""The evaluator: the only server code allowed to open the sealed truth.

It runs after Reveal and compares a reconstruction (form answers, timeline,
claims) with world/truth.json. Matching is deliberately simple and exact:
form answers are option keys, and a timeline event "matches" a canonical event
when it cites a document that is evidence for that event and agrees on the date.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEALED = ROOT / "world"


@lru_cache(maxsize=1)
def _truth() -> dict:
    return json.loads((SEALED / "truth.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _id_map() -> dict[str, str]:
    return json.loads((SEALED / "build" / "id_map.json").read_text(encoding="utf-8"))


def _ids(slugs: list[str]) -> list[str]:
    m = _id_map()
    return [m[s] for s in slugs if s in m]


def grade_answer(q: dict, choice: str | None) -> str:
    """correct | honest_unknown | missed | lucky | wrong | blank"""
    if not choice:
        return "blank"
    if not q["observable"]:
        if choice == "unknown":
            return "honest_unknown"
        return "lucky" if choice == q["answer"] else "wrong"
    if choice == q["answer"]:
        return "correct"
    return "missed" if choice == "unknown" else "wrong"


def grade_form(answers: dict[str, dict | str | None]) -> dict:
    """answers: {Q1: "fabricated"} or {Q1: {"choice":..., "supported":..., "classification":...}}"""
    rows = []
    counts: dict[str, int] = {}
    for q in _truth()["questions"]:
        a = answers.get(q["id"])
        choice = a.get("choice") if isinstance(a, dict) else a
        grade = grade_answer(q, choice)
        # A confident wrong answer with no surviving citation is a ghost: invented, not misread.
        ghost = (isinstance(a, dict) and grade == "wrong" and not a.get("supported")
                 and a.get("classification") in ("observed", "inferred"))
        counts[grade] = counts.get(grade, 0) + 1
        rows.append({
            "id": q["id"], "text": q["text"], "options": q["options"],
            "choice": choice, "answer": q["answer"], "observable": q["observable"],
            "grade": grade, "ghost": bool(ghost),
            "evidence": _ids(q["evidence"]),
        })
    observable = [r for r in rows if r["observable"]]
    return {
        "rows": rows,
        "counts": counts,
        "accuracy": sum(r["grade"] == "correct" for r in observable),
        "of": len(observable),
        "calibrated_unknowns": sum(r["grade"] == "honest_unknown" for r in rows),
        "ghosts": sum(r["ghost"] for r in rows),
    }


def grade_timeline(events: list[dict]) -> dict:
    """Mark each reconstructed event confirmed / ghost / unconfirmed, and list canonical events missed."""
    truth = _truth()
    canon = []
    for ev in truth["events"]:
        docs = set(_ids([slug for slug, _ in ev["evidence"]]))
        canon.append({**ev, "docs": docs})
    matched: set[str] = set()
    out = []
    for e in events:
        cited = {c["sentence_id"].split(":")[0] for c in e.get("citations", []) if c.get("valid")}
        status = "ghost" if e.get("ghost") else "unconfirmed"
        match = None
        if not e.get("ghost"):
            for ev in canon:
                if ev["docs"] & cited and str(e.get("date", ""))[:7] == ev["date"][:7]:
                    match = ev["id"]
                    break
            if match:
                status = "confirmed"
                matched.add(match)
        out.append({**e, "status": status, "matches": match})
    missed = [{"id": ev["id"], "date": ev["date"], "event": ev["event"], "evidence": sorted(ev["docs"])}
              for ev in canon if ev["observable"] and ev["importance"] != "minor" and ev["id"] not in matched]
    return {"events": out, "missed": missed}


def reveal(form_ai: dict | None, form_player: dict | None, timeline: list[dict] | None,
           claims: list[dict] | None) -> dict:
    truth = _truth()
    claims = claims or []
    return {
        "summary": truth["summary"],
        "characters": truth["characters"],
        "canon": [{k: ev[k] for k in ("id", "date", "event", "observable", "importance")} for ev in truth["events"]],
        "hypotheses": truth["hypotheses"],
        "contradictions": [{"id": c["id"], "a": _ids([c["a"][0]]) + [c["a"][1]], "b": _ids([c["b"][0]]) + [c["b"][1]],
                            "resolution": c["resolution"]} for c in truth["contradictions"]],
        "ai": grade_form(form_ai or {}),
        "player": grade_form(form_player or {}),
        "timeline": grade_timeline(timeline or []),
        "claims": {
            "total": len(claims),
            "ghosts": [c for c in claims if c.get("ghost")],
            "unsupported_rate": round(sum(bool(c.get("ghost")) for c in claims) / len(claims), 2) if claims else None,
        },
    }


def sealed_letter() -> str | None:
    """The undamaged original of the most damaged letter, shown only at the very end."""
    src = (SEALED / "source" / "missing.lw").read_text(encoding="utf-8")
    marker = "@@@ elias-confession-full"
    if marker not in src:
        return None
    return src.split(marker, 1)[1].split("\n---\n", 1)[1].split("\n@@@", 1)[0].strip()
