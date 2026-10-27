"""Read-only access to the surviving archive (dataset/archive.json).

This module must never read the sealed side of the repo: the investigator side of
the system only knows what survived.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_PATH = ROOT / "dataset" / "archive.json"


@lru_cache(maxsize=1)
def load(path: str | None = None) -> dict:
    return json.loads(Path(path or ARCHIVE_PATH).read_text(encoding="utf-8"))


def artifacts() -> list[dict]:
    return load()["artifacts"]


def by_id() -> dict[str, dict]:
    return {a["id"]: a for a in artifacts()}


def _show_hidden(include_hidden: bool | set[str], artifact_id: str) -> bool:
    return include_hidden if isinstance(include_hidden, bool) else artifact_id in include_hidden


def sentence_index(ids: list[str] | None = None, include_hidden: bool | set[str] = True) -> dict[str, str]:
    """Map 'A07:s3' -> sentence text for the given artifacts (default: all).

    include_hidden: True/False for all artifacts, or the set of artifact ids whose
    page source the player has opened (View Source).
    """
    idx = {}
    wanted = set(ids) if ids is not None else None
    for a in artifacts():
        if wanted is not None and a["id"] not in wanted:
            continue
        for s in a["sentences"]:
            if s.get("hidden") and not _show_hidden(include_hidden, a["id"]):
                continue
            idx[f"{a['id']}:{s['id']}"] = s["text"]
    return idx


def render_for_prompt(ids: list[str] | None = None, include_hidden: bool | set[str] = True) -> str:
    """The archive as the model sees it: one line per sentence, each with its citation id."""
    blocks = []
    wanted = set(ids) if ids is not None else None
    for a in artifacts():
        if wanted is not None and a["id"] not in wanted:
            continue
        head = (f'<document id="{a["id"]}" path="{a["path"]}" type="{a["type"]}" '
                f'author="{a["author"]}" date="{a["date"]}" integrity="{a["integrity"]}">')
        lines = [head, f"title: {a['title']}"]
        for s in a["sentences"]:
            if s.get("hidden") and not _show_hidden(include_hidden, a["id"]):
                continue
            tag = " (page source)" if s.get("hidden") else ""
            lines.append(f"[{a['id']}:{s['id']}]{tag} {s['text']}")
        lines.append("</document>")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
