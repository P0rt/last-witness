"""HTTP API and static file server.

    uvicorn lastwitness.app:app --app-dir server --port 8000

The investigator side (everything except /reveal and /evaluation) only reads
dataset/. The evaluator is imported lazily, inside the reveal handler, so that
the sealed truth is not even loaded before the player asks for it.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import archive, store
from .investigator import Investigator
from .llm import LLM, LLMError, Ollama

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset"
WEB = ROOT / "web" / "dist"
ART_ID = re.compile(r"^A\d\d$")

app = FastAPI(title="Last Witness")
_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        if os.environ.get("LW_MODEL") == "echo":
            from .echo import Echo
            _llm = Echo()
        else:
            _llm = Ollama()
    return _llm


def set_llm(llm: LLM) -> None:
    """Swap the model backend (tests, offline demo)."""
    global _llm
    _llm = llm


def _json(name: str):
    return json.loads((DATASET / name).read_text(encoding="utf-8"))


QUESTIONS = {q["id"]: q for q in _json("questions.json")}
HYPOTHESES = _json("hypotheses.json")

# Full-text search over visible sentences (page source is not searchable: you have to look).
_fts = sqlite3.connect(":memory:", check_same_thread=False)
_fts.execute("CREATE VIRTUAL TABLE s USING fts5(aid UNINDEXED, sid UNINDEXED, text)")
for _a in archive.artifacts():
    _fts.executemany("INSERT INTO s VALUES (?, ?, ?)",
                     [(_a["id"], x["id"], x["text"]) for x in _a["sentences"] if not x.get("hidden")])
    _fts.execute("INSERT INTO s VALUES (?, ?, ?)", (_a["id"], "title", _a["title"]))


def _summary(a: dict) -> dict:
    return {k: a[k] for k in ("id", "type", "title", "author", "date", "path", "folder", "integrity")}


def _inv(inv_id: str) -> dict:
    state = store.get(inv_id)
    if not state:
        raise HTTPException(404, "no such investigation")
    return state


def _public(state: dict) -> dict:
    out = dict(state)
    if state["status"] != "revealed":
        out.pop("evaluation", None)
    return out


def _evidence(state: dict) -> tuple[list[str], set[str]]:
    return state["discovered"], set(state["source_viewed"])


def _run(state: dict, kind: str, meta: dict) -> None:
    state["runs"].append({"kind": kind, **meta})


def _model_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LLMError as e:
        raise HTTPException(503, f"investigator unavailable: {e}") from e


# ---------------------------------------------------------------- archive

@app.get("/api/meta")
def meta():
    a = archive.load()
    return {"meta": a["meta"], "questions": list(QUESTIONS.values()), "hypotheses": HYPOTHESES,
            "model": get_llm().model_id}


@app.get("/api/artifacts")
def list_artifacts():
    a = archive.load()
    return {"artifacts": [_summary(x) for x in a["artifacts"]], "missing": a["missing"]}


@app.get("/api/artifacts/{aid}")
def get_artifact(aid: str):
    if not ART_ID.match(aid):
        raise HTTPException(400, "bad artifact id")
    a = archive.by_id().get(aid)
    if not a:
        raise HTTPException(404, "not recovered")
    return a


@app.get("/api/search")
def search(q: str = Query(..., min_length=1, max_length=200)):
    terms = re.findall(r"[\w']+", q)
    if not terms:
        return {"results": []}
    query = " ".join(f'"{t}"*' for t in terms)
    rows = _fts.execute("SELECT aid, sid, snippet(s, 2, '[', ']', '…', 12) FROM s WHERE s MATCH ? "
                        "ORDER BY rank LIMIT 50", (query,)).fetchall()
    return {"results": [{"artifact": r[0], "sentence": r[1], "snippet": r[2]} for r in rows]}


# ---------------------------------------------------------------- investigation

class Open(BaseModel):
    artifact: str
    source: bool = False


class Ask(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class PlayerForm(BaseModel):
    answers: dict[str, str]


@app.post("/api/investigations")
def create_investigation():
    notes = next(a["id"] for a in archive.artifacts() if a["path"] == "/RECOVERY_NOTES.txt")
    return store.create([notes])


@app.get("/api/investigations/{inv_id}")
def get_investigation(inv_id: str):
    return _public(_inv(inv_id))


@app.post("/api/investigations/{inv_id}/open")
def open_artifact(inv_id: str, body: Open):
    state = _inv(inv_id)
    if body.artifact not in archive.by_id():
        raise HTTPException(404, "not recovered")
    if body.artifact not in state["discovered"]:
        state["discovered"].append(body.artifact)
    if body.source and body.artifact not in state["source_viewed"]:
        state["source_viewed"].append(body.artifact)
    store.save(state)
    return {"discovered": state["discovered"], "source_viewed": state["source_viewed"]}


@app.post("/api/investigations/{inv_id}/ask")
def ask(inv_id: str, body: Ask):
    state = _inv(inv_id)
    if state["status"] == "revealed":
        raise HTTPException(409, "the investigation is closed")
    history = []
    for m in state["messages"][-6:]:
        role = "user" if m["role"] == "player" else "assistant"
        history.append({"role": role, "content": m.get("text") or m.get("answer", "")})
    discovered, src = _evidence(state)
    r = _model_call(Investigator(get_llm()).ask, body.question, discovered, history, src)
    base = len(state["claims"])
    for i, c in enumerate(r["claims"]):
        c["id"] = f"c{base + i + 1}"
        c["history"] = []
    state["claims"].extend(r["claims"])
    state["messages"].append({"role": "player", "text": body.question})
    state["messages"].append({"role": "investigator", "answer": r["answer"],
                              "claims": [c["id"] for c in r["claims"]],
                              "unresolved_questions": r["unresolved_questions"]})
    _run(state, "ask", r["meta"])
    store.save(state)
    return {"answer": r["answer"], "claims": r["claims"], "unresolved_questions": r["unresolved_questions"]}


@app.post("/api/investigations/{inv_id}/claims/{cid}/objection")
def objection(inv_id: str, cid: str):
    state = _inv(inv_id)
    claim = next((c for c in state["claims"] if c["id"] == cid), None)
    if not claim:
        raise HTTPException(404, "no such claim")
    discovered, src = _evidence(state)
    r = _model_call(Investigator(get_llm()).object_to, claim, discovered, src)
    claim["history"].append({k: claim[k] for k in ("text", "classification", "citations", "ghost")} |
                            {"objection": r["verdict"], "explanation": r["explanation"]})
    if r["verdict"] == "withdrawn":
        claim["withdrawn"] = True
        claim["ghost"] = False
    else:
        if r["verdict"] == "revised" and r["revised_text"]:
            claim["text"] = r["revised_text"]
        claim["classification"] = r["classification"]
        claim["citations"] = r["citations"]
        claim["ghost"] = r["ghost"]
    _run(state, "objection", r["meta"])
    store.save(state)
    return claim


@app.post("/api/investigations/{inv_id}/hypotheses")
def hypotheses(inv_id: str):
    state = _inv(inv_id)
    discovered, src = _evidence(state)
    r = _model_call(Investigator(get_llm()).assess_hypotheses, HYPOTHESES, discovered, src)
    state["hypotheses"].append({"after_documents": len(discovered), "hypotheses": r["hypotheses"]})
    _run(state, "hypotheses", r["meta"])
    store.save(state)
    return state["hypotheses"]


@app.post("/api/investigations/{inv_id}/timeline")
def timeline(inv_id: str):
    state = _inv(inv_id)
    discovered, src = _evidence(state)
    r = _model_call(Investigator(get_llm()).extract_timeline, discovered, src)
    state["timeline"] = r["events"]
    _run(state, "timeline", r["meta"])
    store.save(state)
    return r["events"]


@app.post("/api/investigations/{inv_id}/form/ai/{qid}")
def form_ai(inv_id: str, qid: str):
    state = _inv(inv_id)
    if qid not in QUESTIONS:
        raise HTTPException(404, "no such question")
    discovered, src = _evidence(state)
    r = _model_call(Investigator(get_llm()).answer, QUESTIONS[qid], discovered, False, src)
    state["form_ai"][qid] = r
    _run(state, "form", r["meta"])
    store.save(state)
    return r


@app.put("/api/investigations/{inv_id}/form/player")
def form_player(inv_id: str, body: PlayerForm):
    state = _inv(inv_id)
    if state["status"] == "revealed":
        raise HTTPException(409, "the investigation is closed")
    for qid, choice in body.answers.items():
        if qid not in QUESTIONS or choice not in QUESTIONS[qid]["options"]:
            raise HTTPException(400, f"bad answer {qid}={choice}")
    state["form_player"] = body.answers
    store.save(state)
    return state["form_player"]


@app.post("/api/investigations/{inv_id}/reveal")
def reveal(inv_id: str):
    state = _inv(inv_id)
    if state["status"] != "revealed":
        from . import evaluator  # the sealed side, loaded only now
        state["evaluation"] = evaluator.reveal(state["form_ai"], state["form_player"],
                                               state["timeline"], state["claims"])
        state["evaluation"]["letter"] = evaluator.sealed_letter()
        state["status"] = "revealed"
        store.save(state)
    return state["evaluation"]


@app.get("/api/investigations/{inv_id}/evaluation")
def evaluation(inv_id: str):
    state = _inv(inv_id)
    if state["status"] != "revealed":
        raise HTTPException(403, "the truth stays sealed until you press Reveal")
    return state["evaluation"]


# ---------------------------------------------------------------- web

if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        f = WEB / path
        if path and f.is_file() and WEB in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(WEB / "index.html")
