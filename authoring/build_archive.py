#!/usr/bin/env python3
"""Build the surviving archive from the authored world.

    world/source/*.lw  --(seeded controlled destruction)-->  dataset/archive.json

The output is the ONLY thing the investigator, the server and the browser ever
see. It carries neutral artifact ids (A01, A02, ...), never the authoring slugs,
roles or anything from world/truth.json. The slug -> id map is written to
world/build/id_map.json, on the sealed side, for the evaluator.

Usage:  python authoring/build_archive.py [--seed 1999]
Stdlib only, deterministic for a given seed.
"""
from __future__ import annotations

import argparse
import html
import json
import random
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "world" / "source"
DATASET = ROOT / "dataset" / "archive.json"
QUESTIONS = ROOT / "dataset" / "questions.json"
HYPOTHESES = ROOT / "dataset" / "hypotheses.json"
TRUTH = ROOT / "world" / "truth.json"
ID_MAP = ROOT / "world" / "build" / "id_map.json"

DAMAGE = "▒"
FLAVOR_SURVIVAL = 0.55       # chance a flavor artifact survives the tape
FLAVOR_CORRUPTION = 0.45     # chance a surviving plain-text flavor artifact is damaged
NEVER_SURVIVE = {"purged", "removed", "sealed"}
ALWAYS_SURVIVE = {"critical", "herring"}


@dataclass
class Authored:
    slug: str
    type: str
    title: str
    author: str
    date: str
    path: str
    role: str
    body: str
    links: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- parsing

def parse_lw(path: Path) -> list[Authored]:
    out: list[Authored] = []
    chunks = re.split(r"^@@@ ", path.read_text(encoding="utf-8"), flags=re.M)
    for chunk in chunks[1:]:
        slug, rest = chunk.split("\n", 1)
        header, body = rest.split("\n---\n", 1)
        meta = {}
        for line in header.splitlines():
            if line.strip():
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        links = [s.strip() for s in meta.get("links", "").split(",") if s.strip()]
        out.append(Authored(slug.strip(), meta["type"], meta["title"], meta["author"],
                            meta["date"], meta["path"], meta["role"], body.rstrip() + "\n", links))
    return out


def expand_braces(s: str) -> list[str]:
    m = re.search(r"\{(\d+)\.\.(\d+)\}", s)
    if not m:
        return [s]
    a, b = m.group(1), m.group(2)
    width = len(a)
    return [x for n in range(int(a), int(b) + 1)
            for x in expand_braces(s[:m.start()] + str(n).zfill(width) + s[m.end():])]


def parse_lost(path: Path) -> list[dict]:
    lost = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        p, title, author, date = [x.strip() for x in line.split("|")]
        for pp in expand_braces(p):
            lost.append({"path": pp, "title": title, "author": author, "date": date})
    return lost


# ---------------------------------------------------------------- text extraction

BLOCK_TAGS = {"p", "br", "li", "tr", "h1", "h2", "h3", "h4", "hr", "center", "pre", "ul", "ol",
              "table", "div", "title", "td", "th"}


class PageText(HTMLParser):
    """Visible text (what a 1999 browser shows) and the hidden layer (View Source)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible: list[str] = []
        self.hidden: list[str] = []
        self.hrefs: list[str] = []
        self._buf: list[str] = []
        self._in_title = False
        self._in_pre = False

    def _flush(self) -> None:
        text = "".join(self._buf)
        self._buf = []
        if self._in_pre:
            self.visible.extend(l.rstrip() for l in text.split("\n") if l.strip())
        else:
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                self.visible.append(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in BLOCK_TAGS:
            self._flush()
        if tag == "title":
            self._in_title = True
        if tag == "pre":
            self._in_pre = True
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        if tag == "img" and a.get("alt"):
            self.hidden.append(f'[image alt text] {a["alt"]}')
        if tag == "meta" and a.get("content"):
            self.hidden.append(f'[meta {a.get("name", "")}] {a["content"]}')

    def handle_endtag(self, tag):
        if tag in BLOCK_TAGS:
            self._flush()
        if tag == "title":
            self._in_title = False
        if tag == "pre":
            self._in_pre = False

    def handle_data(self, data):
        if self._in_title:
            return
        self._buf.append(data)

    def handle_comment(self, data):
        self.hidden.append(f"<!-- {data.strip()} -->")

    def close(self):
        super().close()
        self._flush()


def extract(a: Authored) -> tuple[list[str], list[str], list[str]]:
    """Return (visible lines, hidden lines, hrefs)."""
    if a.type == "html_page":
        p = PageText()
        p.feed(a.body)
        p.close()
        return p.visible, p.hidden, p.hrefs
    lines = unwrap(a.body) if a.type in PROSE_TYPES else [l.rstrip() for l in a.body.splitlines()]
    hrefs = [] if a.type in ("log", "file_stub") else re.findall(r"(/[~\w./-]+\.(?:html|wav|txt))", a.body)
    return [l for l in lines if l.strip()], [], hrefs


PROSE_TYPES = {"email", "mail_digest", "text_file"}
HEADER_RE = re.compile(r"^(From|To|Cc|Bcc|Date|Subject|Thread|Message|FILE|STATUS|Plan)\b.*:|^[A-Z][\w ]*:\s*$|^[-=*]{4,}|^[A-Z0-9 ,.:'-]{12,}$")
ITEM_RE = re.compile(r"^(\d+\.|-|\*|\[)\s")


def unwrap(body: str) -> list[str]:
    """Join hard-wrapped e-mail lines back into paragraphs; keep headers and list items apart."""
    out: list[str] = []
    joinable = False
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            joinable = False
            continue
        stripped = line.strip()
        if HEADER_RE.match(stripped) or stripped.startswith(("Today's Topics", "End of", "Volume")):
            out.append(stripped)
            joinable = False
        elif joinable and (raw.startswith(" ") or not ITEM_RE.match(stripped)):
            out[-1] = out[-1] + " " + stripped
        else:
            out.append(stripped)
            joinable = True
    return out


SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[A-Z0-9])")


def split_sentences(line: str, kind: str) -> list[str]:
    if kind in ("log", "file_stub") or len(line) < 60:
        return [line]
    parts = [s for s in SENT_RE.split(line) if s.strip()]
    merged: list[str] = []
    for p in parts:  # keep list markers ("1.") and stray fragments with what follows
        if merged and re.fullmatch(r"\(?\w{1,3}[.)]", merged[-1]):
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


# ---------------------------------------------------------------- destruction

def corrupt(lines: list[str], rng: random.Random) -> list[str]:
    """Overwrite one or two spans with unreadable bytes, or truncate the file."""
    lines = list(lines)
    if len(lines) < 4:
        return lines
    if rng.random() < 0.35:
        keep = rng.randint(max(2, len(lines) // 2), len(lines) - 1)
        return lines[:keep] + [f"{DAMAGE * 24} [file truncated: remaining bytes unreadable]"]
    for _ in range(rng.choice([1, 2])):
        i = rng.randrange(1, len(lines))
        line = lines[i]
        if len(line) < 12:
            lines[i] = DAMAGE * max(len(line), 8)
            continue
        a = rng.randrange(0, len(line) // 2)
        b = min(len(line), a + rng.randint(10, 40))
        lines[i] = line[:a] + DAMAGE * (b - a) + line[b:]
    return lines


def normalize(href: str, base: str) -> str | None:
    if href.startswith(("http:", "https:", "mailto:", "#")) or "cgi-bin" in href:
        return None
    if not href.startswith("/"):
        href = base.rsplit("/", 1)[0] + "/" + href
    if href.endswith("/"):
        href += "index.html"
    if href.startswith("/~") and href.count("/") == 1:
        href += "/index.html"
    return href


def folder_of(path: str) -> str:
    if path.startswith("/~"):
        return "users"
    if path.startswith("/colo/"):
        return "new-server"
    parts = path.strip("/").split("/")
    return parts[0] if len(parts) > 1 else "www"


def build(seed: int) -> dict:
    authored = [a for f in sorted(SOURCE.glob("*.lw")) for a in parse_lw(f)]
    lost = parse_lost(SOURCE / "lost.lw")
    rng = random.Random(seed)

    survivors: list[Authored] = []
    destroyed: list[Authored] = []
    for a in sorted(authored, key=lambda x: x.slug):
        if a.role in NEVER_SURVIVE:
            destroyed.append(a)
        elif a.role in ALWAYS_SURVIVE or rng.random() < FLAVOR_SURVIVAL:
            survivors.append(a)
        else:
            destroyed.append(a)

    occupied = {a.path for a in survivors}
    lost_paths = {l["path"] for l in lost}
    # Anything authored but destroyed becomes a missing entry, unless a tombstone holds its path.
    missing = [{"path": a.path, "title": a.title, "author": a.author, "date": a.date[:10]}
               for a in destroyed if a.path not in occupied and not a.path.startswith("/sealed/")]
    authored_paths = {a.path for a in authored}
    missing += [l for l in lost if l["path"] not in authored_paths]
    missing.sort(key=lambda m: m["path"])
    missing_paths = {m["path"] for m in missing}

    survivors.sort(key=lambda a: (folder_of(a.path), a.path))
    id_map = {a.slug: f"A{i + 1:02d}" for i, a in enumerate(survivors)}
    path_to_id = {a.path: id_map[a.slug] for a in survivors}

    artifacts = []
    for a in survivors:
        visible, hidden, hrefs = extract(a)
        integrity = "intact"
        raw = a.body
        if a.role == "flavor" and a.type != "html_page":
            arng = random.Random(f"{seed}:{a.slug}")
            if arng.random() < FLAVOR_CORRUPTION:
                visible = corrupt(visible, arng)
                raw = "\n".join(visible) + "\n"
        if any(DAMAGE * 3 in l for l in visible + hidden) or DAMAGE * 3 in raw:
            integrity = "partial"
        if a.type == "file_stub":
            integrity = "header_only"

        sentences = []
        n = 0
        for line in visible:
            for s in split_sentences(line, a.type):
                n += 1
                sentences.append({"id": f"s{n}", "text": s})
        for i, line in enumerate(hidden, 1):
            sentences.append({"id": f"h{i}", "text": line, "hidden": True})

        links = []
        seen = set()
        for href in list(a.links) + hrefs:
            target = normalize(href, a.path)
            if not target or target in seen or target == a.path:
                continue
            seen.add(target)
            if target in path_to_id:
                links.append({"href": target, "target": path_to_id[target], "status": "ok"})
            elif target in missing_paths:
                links.append({"href": target, "target": None, "status": "missing"})
            else:
                links.append({"href": target, "target": None, "status": "unknown"})

        artifacts.append({
            "id": id_map[a.slug],
            "type": a.type,
            "title": a.title,
            "author": a.author,
            "date": a.date,
            "path": a.path,
            "folder": folder_of(a.path),
            "integrity": integrity,
            "raw": raw,
            "sentences": sentences,
            "links": links,
        })

    originals = len([a for a in authored if a.role != "sealed"]) + len(
        [l for l in lost if l["path"] not in authored_paths])
    archive = {
        "meta": {
            "name": "The Lighthouse Network — recovered archive",
            "seed": seed,
            "originals": originals,
            "recovered": len(artifacts),
            "missing": len(missing),
            "lost_percent": round(100 * (1 - len(artifacts) / originals)),
        },
        "artifacts": artifacts,
        "missing": missing,
    }
    return {"archive": archive, "id_map": id_map, "authored": authored}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1999)
    args = ap.parse_args()
    out = build(args.seed)
    DATASET.parent.mkdir(parents=True, exist_ok=True)
    DATASET.write_text(json.dumps(out["archive"], ensure_ascii=False, indent=1), encoding="utf-8")
    ID_MAP.parent.mkdir(parents=True, exist_ok=True)
    ID_MAP.write_text(json.dumps(out["id_map"], indent=1, sort_keys=True), encoding="utf-8")
    # The reconstruction form without its answer key: what the player and the model fill in.
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    form = [{"id": q["id"], "text": q["text"], "options": q["options"]} for q in truth["questions"]]
    QUESTIONS.write_text(json.dumps(form, ensure_ascii=False, indent=1), encoding="utf-8")
    hyps = [{"id": h["id"], "title": h["public_title"]} for h in truth["hypotheses"]]
    HYPOTHESES.write_text(json.dumps(hyps, ensure_ascii=False, indent=1), encoding="utf-8")
    m = out["archive"]["meta"]
    print(f"seed {m['seed']}: {m['recovered']} recovered / {m['originals']} originals "
          f"({m['lost_percent']}% lost), {m['missing']} known-missing paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
