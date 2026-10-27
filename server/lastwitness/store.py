"""Investigation state, one JSON document per investigation in SQLite."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("LW_DB", ROOT / "data" / "investigations.sqlite"))

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("CREATE TABLE IF NOT EXISTS investigations (id TEXT PRIMARY KEY, created REAL, state TEXT)")
    return c


def new_state(first_documents: list[str]) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "created": time.time(),
        "status": "open",
        "discovered": list(first_documents),
        "source_viewed": [],
        "messages": [],        # {"role": "player"|"investigator", ...}
        "claims": [],          # every claim ever made, with objection history
        "hypotheses": [],      # list of assessments, newest last (audit history)
        "timeline": None,
        "form_ai": {},
        "form_player": {},
        "evaluation": None,
        "runs": [],            # reproducibility log: model, prompt version, evidence ids
    }


def create(first_documents: list[str]) -> dict:
    state = new_state(first_documents)
    save(state)
    return state


def get(inv_id: str) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT state FROM investigations WHERE id = ?", (inv_id,)).fetchone()
    return json.loads(row[0]) if row else None


def save(state: dict) -> None:
    with _lock, _conn() as c:
        c.execute("INSERT OR REPLACE INTO investigations (id, created, state) VALUES (?, ?, ?)",
                  (state["id"], state["created"], json.dumps(state, ensure_ascii=False)))
