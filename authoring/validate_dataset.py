#!/usr/bin/env python3
"""Check that the destroyed archive is still a fair, solvable mystery.

Rebuilds the archive with the given seed and verifies, against world/truth.json:
  - enough survives: >= 40 artifacts, >= 10 broken links, >= 5 damaged files
  - every observable canonical event still has its evidence, word for word
  - every observable form question still has every artifact it relies on
  - every seeded contradiction has both sides intact
  - no sealed text, authoring slug or truth id leaks into dataset/archive.json
  - nobody posts before they joined, and thread timestamps run forward
  - every link either resolves or is a known-missing file
  - no single artifact gives away more than three answers

Exit code 0 = all checks pass.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_archive import ROOT, build  # noqa: E402

TRUTH = ROOT / "world" / "truth.json"

JOINED = {
    "keeper": "1997-03-14", "sysop_ray": "1997-08-01", "saltmarsh": "1998-02-01",
    "hvale": "1997-11-01", "eward": "1998-04-01", "qrp_anna": "1998-06-01",
    "dotmatrix": "1998-09-01", "junebug": "1999-01-01", "nightjar": "1999-09-05",
}
LEFT = {"hvale": "1999-09-24"}  # forum posts only; private mail is fine
POST_RE = re.compile(r"^\[(\w+) \| (\d\d/\d\d/\d\d \d\d:\d\d)\]")


def text_of(artifact: dict) -> str:
    return "\n".join(s["text"] for s in artifact["sentences"])


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def validate(seed: int) -> list[str]:
    out = build(seed)
    archive, id_map, authored = out["archive"], out["id_map"], out["authored"]
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    by_id = {a["id"]: a for a in archive["artifacts"]}
    errors: list[str] = []

    def surviving_text(slug: str) -> str | None:
        aid = id_map.get(slug)
        return norm(text_of(by_id[aid])) if aid else None

    # 1. volume
    arts = archive["artifacts"]
    broken = sum(1 for a in arts for l in a["links"] if l["status"] != "ok")
    damaged = sum(1 for a in arts if a["integrity"] != "intact")
    if len(arts) < 40:
        errors.append(f"only {len(arts)} artifacts survive (need >= 40)")
    if broken < 10:
        errors.append(f"only {broken} broken links (need >= 10)")
    if damaged < 5:
        errors.append(f"only {damaged} damaged artifacts (need >= 5)")

    # 2. canonical events
    for ev in truth["events"]:
        if not ev["observable"]:
            continue
        if not ev["evidence"]:
            errors.append(f"{ev['id']} is observable but lists no evidence")
        for slug, quote in ev["evidence"]:
            t = surviving_text(slug)
            if t is None:
                errors.append(f"{ev['id']}: evidence {slug} did not survive")
            elif norm(quote) not in t:
                errors.append(f"{ev['id']}: quote not found intact in {slug}: {quote!r}")

    # 3. questions
    for q in truth["questions"]:
        if q["answer"] not in q["options"] or "unknown" not in q["options"]:
            errors.append(f"{q['id']}: answer/unknown missing from options")
        if q["observable"]:
            for slug in q["evidence"]:
                if slug not in id_map:
                    errors.append(f"{q['id']}: evidence {slug} did not survive")

    # 4. contradictions
    for c in truth["contradictions"]:
        for side in ("a", "b"):
            slug, quote = c[side]
            t = surviving_text(slug)
            if t is None or norm(quote) not in t:
                errors.append(f"{c['id']}: side {side} ({slug}) not intact")

    # 5. leaks
    blob = json.dumps(archive, ensure_ascii=False)
    public_text = "\n".join(a.body for a in authored if a.role != "sealed")
    for a in authored:
        if re.search(rf"\b{re.escape(a.slug)}\b", blob):
            errors.append(f"authoring slug leaked into archive: {a.slug}")
        if a.role == "sealed":
            for line in a.body.splitlines():
                line = line.strip()
                if len(line) > 25 and line not in public_text and line in blob:
                    errors.append(f"sealed text leaked: {line[:40]!r}")
    for key in ('"role"', '"slug"', '"observable"', '"importance"'):
        if key in blob:
            errors.append(f"authoring field {key} leaked into archive")
    for ev in truth["events"]:
        if re.search(rf"\b{ev['id']}\b", blob):
            errors.append(f"truth id {ev['id']} appears in archive")

    # 6. chronology
    for a in arts:
        date = a["date"][:10]
        if not ("1997-01-01" <= date <= "1999-12-31") and a["path"] != "/RECOVERY_NOTES.txt":
            errors.append(f"{a['path']}: date {date} outside 1997-1999")
        if a["author"] in JOINED and date < JOINED[a["author"]]:
            errors.append(f"{a['path']}: {a['author']} writes before joining")
        if a["type"] == "forum_thread":
            prev = None
            for s in a["sentences"]:
                m = POST_RE.match(s["text"])
                if not m:
                    continue
                who, when = m.group(1), datetime.strptime(m.group(2), "%m/%d/%y %H:%M")
                d = when.strftime("%Y-%m-%d")
                if who in JOINED and d < JOINED[who]:
                    errors.append(f"{a['path']}: {who} posts on {d}, before joining")
                if who in LEFT and d > LEFT[who]:
                    errors.append(f"{a['path']}: {who} posts on {d}, after leaving")
                if prev and when < prev:
                    errors.append(f"{a['path']}: posts out of order at {m.group(0)}")
                prev = when

    # 7. links
    for a in arts:
        for l in a["links"]:
            if l["status"] == "unknown":
                errors.append(f"{a['path']}: link to {l['href']} is neither recovered nor known-missing")

    # 8. no single artifact solves the case
    uses = Counter(slug for q in truth["questions"] for slug in set(q["evidence"]))
    for slug, n in uses.items():
        if n > 3:
            errors.append(f"{slug} is evidence for {n} questions (max 3)")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1999)
    args = ap.parse_args()
    errors = validate(args.seed)
    for e in errors:
        print("FAIL", e)
    print(f"{len(errors)} problem(s)" if errors else "dataset OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
