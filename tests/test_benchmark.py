import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


def test_benchmark_scoring(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("bench", ROOT / "benchmarks/run_benchmark.py")
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    monkeypatch.setattr(bench, "RUNS", tmp_path)
    monkeypatch.setattr(bench, "RESULTS", tmp_path / "results.md")
    monkeypatch.setattr(bench, "ROOT", ROOT)

    from lastwitness import archive
    from lastwitness.llm import Ollama
    sid = next(k for k, v in archive.sentence_index().items() if "That's two recordings joined together." in v)

    def chat(self, messages, schema):
        has_docs = "<archive>" in messages[-1]["content"]
        if not has_docs:  # closed book: confidently wrong, no citations possible
            return {"reasoning": "", "choice": [o for o in schema["properties"]["choice"]["enum"] if o != "unknown"][0],
                    "classification": "observed"}
        if "Q1:" in messages[-1]["content"]:
            return {"reasoning": "", "choice": "fabricated", "classification": "inferred",
                    "citations": [{"sentence_id": sid, "quote": "two recordings joined together"}]}
        return {"reasoning": "", "choice": "elias" if "elias" in schema["properties"]["choice"]["enum"] else "unknown",
                "classification": "inferred", "citations": [{"sentence_id": sid, "quote": "made up words"}]}

    monkeypatch.setattr(Ollama, "chat", chat)
    monkeypatch.setattr(bench, "ROOT", ROOT)
    f = bench.run("fake", repeats=1, temperature=0.0, num_ctx=None, only=None)
    s = bench.score(json.loads(f.read_text()))["conditions"]
    assert s["archive"]["correct"] >= 2           # Q1 (cited) + Q2 (elias, uncited)
    assert s["validated"]["correct"] == 1         # only the cited answer survives validation
    assert s["validated"]["honest_unknown"] == 1  # Q10
    assert s["closed_book"]["ghosts"] > 0
    md = bench.summarize()
    assert "| fake | validated |" in md
