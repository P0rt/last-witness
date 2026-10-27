import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "authoring"))

from validate_dataset import validate  # noqa: E402


def test_default_seed_is_valid():
    assert validate(1999) == []


def test_other_seeds_stay_solvable():
    for seed in (1, 7, 31, 2026):
        assert validate(seed) == [], seed


def test_committed_archive_matches_build():
    from build_archive import build
    committed = json.loads((ROOT / "dataset/archive.json").read_text(encoding="utf-8"))
    assert committed == build(committed["meta"]["seed"])["archive"], "run: make data"


def test_public_side_never_reads_world():
    for f in (ROOT / "server").rglob("*.py"):
        src = f.read_text(encoding="utf-8")
        if f.name == "evaluator.py":
            continue
        assert "truth.json" not in src and "world/" not in src and '"world"' not in src, f


def test_questions_file_has_no_answers():
    qs = json.loads((ROOT / "dataset/questions.json").read_text(encoding="utf-8"))
    assert len(qs) == 10
    for q in qs:
        assert set(q) == {"id", "text", "options"}
        assert "unknown" in q["options"]
