#!/usr/bin/env python3
"""Record a real investigation for the static replay (GitHub Pages).

Plays the game through the real API with a real local model: opens every
recovered document (and every page source), asks a fixed list of questions,
objects to every claim that came back as a ghost, re-assesses the hypotheses,
builds the timeline and fills in the form. Then it reveals, and writes:

  web/public/replay/meta.json        archive meta, questions, hypotheses, model
  web/public/replay/artifacts.json   the surviving archive (same as dataset/)
  web/public/replay/session.json     the recorded investigation, verbatim
  web/public/replay/sealed.json      the evaluation of that investigation, plus the
                                     answer key so a visitor's own form can be graded

The replay is honest about what it is: every answer in it was produced by the
model named in meta.json, and the truth ships in the bundle (it has to, there is
no server). The live game keeps it sealed.

    python scripts/record_replay.py --model gemma4:e4b
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
OUT = ROOT / "web" / "public" / "replay"

QUESTIONS = [
    "Why did the Lighthouse Network disappear?",
    "What is the Cape Sorrow recording, and is it genuine?",
    "Who is nightjar?",
    "What happened on October 16 and 17, 1999?",
    "Who deleted the Cape Sorrow threads, and why?",
    "Was the server migration a reaction to the scandal?",
    "Who downloaded the recording dozens of times on October 15?",
    "Which documents contradict each other?",
    "Whose voice is on the recording?",
    "What happened to Elias Ward after 1999?",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("LW_MODEL", "gemma4:e4b"))
    args = ap.parse_args()
    os.environ["LW_MODEL"] = args.model
    os.environ["LW_DB"] = str(Path(tempfile.mkdtemp()) / "replay.sqlite")

    from fastapi.testclient import TestClient
    from lastwitness import app as appmod
    from lastwitness import archive, store
    store.DB_PATH = Path(os.environ["LW_DB"])
    if args.model == "echo":
        from lastwitness.echo import Echo
        appmod.set_llm(Echo())
    c = TestClient(appmod.app)

    def ok(r):
        if r.status_code >= 400:
            raise SystemExit(f"{r.request.url}: {r.status_code} {r.text[:300]}")
        return r.json()

    t0 = time.time()
    inv = ok(c.post("/api/investigations"))
    iid = inv["id"]
    for a in archive.artifacts():
        ok(c.post(f"/api/investigations/{iid}/open",
                  json={"artifact": a["id"], "source": a["type"] == "html_page"}))
    for q in QUESTIONS:
        print(">>", q, flush=True)
        r = ok(c.post(f"/api/investigations/{iid}/ask", json={"question": q}))
        for cl in r["claims"]:
            if cl["ghost"]:
                print("   objection:", cl["text"][:80], flush=True)
                ok(c.post(f"/api/investigations/{iid}/claims/{cl['id']}/objection"))
    print(">> hypotheses", flush=True)
    ok(c.post(f"/api/investigations/{iid}/hypotheses"))
    print(">> timeline", flush=True)
    ok(c.post(f"/api/investigations/{iid}/timeline"))
    meta = ok(c.get("/api/meta"))
    for q in meta["questions"]:
        print(">> form", q["id"], flush=True)
        ok(c.post(f"/api/investigations/{iid}/form/ai/{q['id']}"))
    session = ok(c.get(f"/api/investigations/{iid}"))
    evaluation = ok(c.post(f"/api/investigations/{iid}/reveal"))

    truth = json.loads((ROOT / "world" / "truth.json").read_text(encoding="utf-8"))
    key = {q["id"]: {"answer": q["answer"], "observable": q["observable"], "evidence": row["evidence"]}
           for q, row in zip(truth["questions"], evaluation["ai"]["rows"])}

    OUT.mkdir(parents=True, exist_ok=True)
    meta["recorded"] = {"model": args.model, "at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                        "minutes": round((time.time() - t0) / 60, 1), "questions": QUESTIONS,
                        "config": appmod.get_llm().config()}
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    (OUT / "artifacts.json").write_text(json.dumps(archive.load(), ensure_ascii=False))
    (OUT / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=1))
    (OUT / "sealed.json").write_text(json.dumps({"evaluation": evaluation, "key": key}, ensure_ascii=False, indent=1))
    print(f"replay written to {OUT.relative_to(ROOT)} in {meta['recorded']['minutes']} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
