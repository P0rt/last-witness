import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from lastwitness import archive  # noqa: E402
from lastwitness.investigator import Investigator, check_citations, is_ghost, quote_matches  # noqa: E402
from lastwitness.llm import Ollama, Scripted  # noqa: E402


def find(text):
    for sid, s in archive.sentence_index().items():
        if text in s:
            return sid, s
    raise AssertionError(text)


def test_quote_matching_tolerates_punctuation_not_paraphrase():
    s = "Two things follow: if a recording claims to come from a battery radio, it should not have 60 Hz lines."
    assert quote_matches("it should not have 60 Hz lines", s)
    assert quote_matches("it should not have 60Hz lines", s)
    assert not quote_matches("the recording was faked by Elias", s)
    assert not quote_matches("▒▒▒▒▒▒▒▒", "▒▒▒▒▒▒▒▒ some text")


def test_misfiled_citations_point_to_the_real_sentence_but_stay_invalid():
    index = archive.sentence_index()
    real, _ = find("I was there.")
    doc, n = real.split(":")
    before = f"{doc}:s{int(n[1:]) - 1}"
    span_from, _ = find("To anyone reading this file")
    cits = check_citations([
        {"sentence_id": before, "quote": "I was there."},               # off by one
        {"sentence_id": span_from, "quote": "the Cape Sorrow recording is genuine"},  # runs into the next sentence
        {"sentence_id": real, "quote": "The recording was faked by Elias Ward."},     # invented
    ], index)
    assert [c.valid for c in cits] == [False, False, False]
    assert cits[0].found_at == real and real in cits[0].reason
    assert cits[1].found_at == span_from and "runs past" in cits[1].reason
    assert cits[2].found_at is None
    assert is_ghost("observed", cits)


def test_ask_marks_ghosts_and_rejects_fake_ids():
    sid, _ = find("He admits it.")

    def respond(messages, schema):
        return {
            "answer": "x",
            "claims": [
                {"text": "Someone admitted something on Oct 16.", "classification": "observed",
                 "citations": [{"sentence_id": sid, "quote": "He admits it."}]},
                {"text": "The FBI seized the server.", "classification": "observed",
                 "citations": [{"sentence_id": "A99:s1", "quote": "FBI"}]},
                {"text": "Ray deleted it.", "classification": "inferred",
                 "citations": [{"sentence_id": sid, "quote": "Ray deleted everything"}]},
                {"text": "Maybe ghosts.", "classification": "speculative", "citations": []},
            ],
            "unresolved_questions": [],
        }

    r = Investigator(Scripted(respond)).ask("what happened?")
    ghosts = [c["ghost"] for c in r["claims"]]
    assert ghosts == [False, True, True, False]
    assert r["claims"][1]["citations"][0]["reason"].startswith("no such sentence")


def test_prompt_contains_only_discovered_documents():
    seen = {}

    def respond(messages, schema):
        seen["prompt"] = "\n".join(m["content"] for m in messages)
        seen["schema"] = schema
        return {"answer": "", "claims": [], "unresolved_questions": []}

    Investigator(Scripted(respond)).ask("q", discovered=["A01", "A02"])
    assert 'id="A01"' in seen["prompt"] and 'id="A03"' not in seen["prompt"]
    ids = seen["schema"]["properties"]["claims"]["items"]["properties"]["citations"]["items"]["properties"]["sentence_id"]["enum"]
    assert all(i.startswith(("A01:", "A02:")) for i in ids)


def test_injection_text_is_presented_as_evidence():
    # The 1999 README tells readers to disregard analysis. It must reach the model
    # only inside the <archive> data block, never as a system instruction.
    seen = {}

    def respond(messages, schema):
        seen["messages"] = messages
        return {"answer": "", "claims": [], "unresolved_questions": []}

    Investigator(Scripted(respond)).ask("Is the recording real?")
    system = seen["messages"][0]["content"]
    data = seen["messages"][1]["content"]
    assert "Disregard any analysis" not in system
    assert "Disregard any analysis" in data and data.startswith("<archive>")


class FakeOllama(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["format"]["type"] == "object" and body["options"]["num_ctx"] >= 16384
        sid, _ = find("That's two recordings joined together.")
        content = {"reasoning": "Dot found a splice.", "choice": "fabricated", "classification": "inferred",
                   "citations": [{"sentence_id": sid, "quote": "two recordings joined together"}]}
        out = json.dumps({"message": {"content": json.dumps(content)}, "prompt_eval_count": 9000}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def test_form_answer_through_ollama_http():
    srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        llm = Ollama(model="fake", host=f"http://127.0.0.1:{srv.server_port}")
        q = json.loads((ROOT / "dataset/questions.json").read_text())[0]
        r = Investigator(llm).answer(q)
        assert r["choice"] == "fabricated" and r["supported"]
    finally:
        srv.shutdown()
