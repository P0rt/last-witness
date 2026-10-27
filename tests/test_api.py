import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LW_DB", str(tmp_path / "t.sqlite"))
    from lastwitness import store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "t.sqlite")
    from fastapi.testclient import TestClient
    from lastwitness import app as appmod
    from lastwitness.llm import Scripted
    from lastwitness import archive

    idx = archive.sentence_index()
    sid = next(k for k, v in idx.items() if "He admits it." in v)

    def respond(messages, schema):
        props = schema["properties"]
        if "claims" in props:
            return {"answer": "Someone admitted something.", "unresolved_questions": ["who is E?"], "claims": [
                {"text": "An admission was made on Oct 16.", "classification": "observed",
                 "citations": [{"sentence_id": sid, "quote": "He admits it."}]},
                {"text": "The FBI took the server.", "classification": "observed", "citations": []}]}
        if "verdict" in props:
            return {"verdict": "withdrawn", "explanation": "Nothing says that.", "revised_text": "",
                    "classification": "unknown", "citations": []}
        if "choice" in props:
            opts = props["choice"]["enum"]
            return {"reasoning": "r", "choice": "unknown" if "unknown" in opts else opts[0],
                    "classification": "unknown", "citations": []}
        if "events" in props:
            return {"events": [{"date": "1999-10-16", "date_is_certain": True, "description": "admission",
                                "classification": "observed",
                                "citations": [{"sentence_id": sid, "quote": "He admits it."}]}]}
        if "hypotheses" in props:
            return {"hypotheses": [{"id": "H1", "status": "plausible", "reason": "r", "supporting": [],
                                    "contradicting": [], "would_falsify": "x"}]}
        raise AssertionError(schema)

    appmod.set_llm(Scripted(respond))
    return TestClient(appmod.app)


def test_full_loop_and_sealed_truth(client):
    truth = json.loads((ROOT / "world/truth.json").read_text())
    secret = truth["summary"][:60]

    inv = client.post("/api/investigations").json()
    iid = inv["id"]
    assert inv["discovered"]  # recovery notes are open from the start

    admin = next(a for a in client.get("/api/artifacts").json()["artifacts"] if a["path"] == "/forum/admin/thread_007.html")
    client.post(f"/api/investigations/{iid}/open", json={"artifact": admin["id"]})

    r = client.post(f"/api/investigations/{iid}/ask", json={"question": "what happened?"}).json()
    assert [c["ghost"] for c in r["claims"]] == [False, True]

    ghost = r["claims"][1]["id"]
    c = client.post(f"/api/investigations/{iid}/claims/{ghost}/objection").json()
    assert c["withdrawn"] and c["history"][0]["ghost"]

    assert client.post(f"/api/investigations/{iid}/timeline").status_code == 200
    assert client.post(f"/api/investigations/{iid}/hypotheses").status_code == 200
    assert client.post(f"/api/investigations/{iid}/form/ai/Q10").json()["choice"] == "unknown"
    client.put(f"/api/investigations/{iid}/form/player", json={"answers": {"Q1": "fabricated"}})

    # Nothing so far may contain the truth.
    assert client.get(f"/api/investigations/{iid}/evaluation").status_code == 403
    state = client.get(f"/api/investigations/{iid}").text
    assert secret not in state and "evaluation" not in client.get(f"/api/investigations/{iid}").json()

    ev = client.post(f"/api/investigations/{iid}/reveal").json()
    assert secret in ev["summary"]
    assert ev["ai"]["counts"].get("honest_unknown") == 1
    assert ev["player"]["rows"][0]["grade"] == "correct"
    assert ev["timeline"]["events"][0]["status"] == "confirmed"
    assert "It was never a signal" in ev["letter"]
    assert client.post(f"/api/investigations/{iid}/ask", json={"question": "x"}).status_code == 409


def test_bad_ids(client):
    assert client.get("/api/artifacts/..%2F..%2Fworld%2Ftruth.json").status_code in (400, 404)
    assert client.get("/api/artifacts/A99").status_code == 404
    r = client.get("/api/artifacts/../../etc/passwd")  # normalised away by the client; must not leak files
    assert "root:" not in r.text and "canonical" not in r.text
    iid = client.post("/api/investigations").json()["id"]
    assert client.post(f"/api/investigations/{iid}/open", json={"artifact": "../truth"}).status_code == 404
    assert client.put(f"/api/investigations/{iid}/form/player", json={"answers": {"Q1": "maybe"}}).status_code == 400


def test_search(client):
    res = client.get("/api/search", params={"q": "light is out"}).json()["results"]
    assert res and all(r["artifact"].startswith("A") for r in res)
