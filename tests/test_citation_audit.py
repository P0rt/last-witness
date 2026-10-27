import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from lastwitness import archive  # noqa: E402


def _audit():
    spec = importlib.util.spec_from_file_location("audit", ROOT / "benchmarks/citation_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sid(text):
    return next(k for k, v in archive.sentence_index().items() if v == text)


def test_rejected_citations_are_classified_by_where_the_quote_lives():
    audit, index = _audit(), archive.sentence_index()
    authentic, there = _sid("This recording is authentic."), _sid("I was there.")
    assert audit.classify(authentic, "I was there.", index) == "neighbour"
    doc, s = there.split(":")
    nxt = f"{doc}:s{int(s[1:]) + 1}"
    assert audit.classify(there, "I was there. " + index[nxt], index) == "spans"
    assert audit.classify(authentic, "The FBI seized the server in a midnight raid.", index) == "not_in_archive"
