#!/usr/bin/env python3
"""Ablation benchmark: does evidence (and checking it) make the investigator more honest?

For each model, each of the 10 reconstruction questions is asked under:

  closed_book   no documents at all; the model answers from its own judgement
  archive       the full surviving archive, citations requested
  validated     the same answers as `archive`, but any answer whose citations do
                not survive checking is replaced by "unknown" (what the game does)

`archive` and `validated` share one model call, so a run costs
questions x repeats x 2 calls per model.

    python benchmarks/run_benchmark.py                          # gemma4:e4b, 3 repeats
    python benchmarks/run_benchmark.py --models gemma4:e4b gemma4:12b --repeats 3
    python benchmarks/run_benchmark.py --summarize              # rebuild results.md from runs/

Each run is saved as JSON under benchmarks/runs/ as it goes (a crash loses at
most one call). benchmarks/results.md is regenerated from every saved run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from lastwitness.evaluator import grade_form  # noqa: E402  (benchmark is on the sealed side)
from lastwitness.investigator import Investigator  # noqa: E402
from lastwitness.llm import LLMError, Ollama  # noqa: E402

RUNS = ROOT / "benchmarks" / "runs"
RESULTS = ROOT / "benchmarks" / "results.md"
CONDITIONS = ("closed_book", "archive", "validated")


def run(model: str, repeats: int, temperature: float, num_ctx: int | None, only: list[str] | None,
        think: bool | None = None) -> Path:
    if model == "echo":
        raise SystemExit("echo is not a model; benchmark a real one")
    questions = json.loads((ROOT / "dataset" / "questions.json").read_text(encoding="utf-8"))
    if only:
        questions = [q for q in questions if q["id"] in only]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tag = "" if think is None else ("-think" if think else "-nothink")
    out = RUNS / f"bench-{model.replace(':', '_').replace('/', '_')}{tag}-{stamp}.json"
    RUNS.mkdir(parents=True, exist_ok=True)
    log = {"model": model, "started": stamp, "repeats": repeats, "temperature": temperature,
           "questions": [q["id"] for q in questions], "calls": []}

    # All archive calls first, then all closed-book ones. Every archive call starts with the
    # same ~28K-token prefix (system prompt + archive), so Ollama's prompt cache reads the
    # archive once; interleaving closed-book calls would evict it and re-read it every time.
    for closed in (False, True):
        cond = "closed_book" if closed else "archive"
        for rep in range(repeats):
            llm = Ollama(model=model, num_ctx=num_ctx, temperature=temperature, seed=1000 + rep, think=think)
            log["config"] = llm.config() | {"seed": "1000 + repeat"}
            inv = Investigator(llm)
            for q in questions:
                t0 = time.time()
                try:
                    r = inv.answer(q, closed_book=closed)
                    entry = {"repeat": rep, "condition": cond, **r}
                except LLMError as e:
                    entry = {"repeat": rep, "condition": cond, "question": q["id"], "error": str(e)}
                entry["wall_seconds"] = round(time.time() - t0, 1)
                entry["ollama"] = getattr(llm, "last_stats", {})
                log["calls"].append(entry)
                out.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"[{model} r{rep}] {q['id']:4} {cond:11} -> {entry.get('choice', 'ERROR'):12} "
                      f"supported={entry.get('supported')} {entry['wall_seconds']}s", flush=True)
    log["finished"] = time.strftime("%Y%m%d-%H%M%S")
    out.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def score(log: dict) -> dict:
    """Per condition: mean over repeats of the form grade."""
    by = {c: {} for c in CONDITIONS}
    for call in log["calls"]:
        if "error" in call:
            continue
        rep = call["repeat"]
        if call["condition"] == "closed_book":
            by["closed_book"].setdefault(rep, {})[call["question"]] = {**call, "supported": False}
        else:
            by["archive"].setdefault(rep, {})[call["question"]] = call
            v = dict(call)
            if v["choice"] != "unknown" and not v["supported"]:
                v["choice"] = "unknown"
            by["validated"].setdefault(rep, {})[call["question"]] = v
    out = {}
    for cond, reps in by.items():
        if not reps:
            continue
        grades = [grade_form(answers) for answers in reps.values()]
        n = len(grades)
        unsupported = []
        for answers in reps.values():
            committed = [a for a in answers.values() if a["choice"] != "unknown"]
            unsupported.append(sum(not a.get("supported") for a in committed))
        out[cond] = {
            "repeats": n,
            "correct": round(sum(g["accuracy"] for g in grades) / n, 2),
            "of": grades[0]["of"],
            "honest_unknown": round(sum(g["calibrated_unknowns"] for g in grades) / n, 2),
            "ghosts": round(sum(g["ghosts"] for g in grades) / n, 2),
            "wrong": round(sum(g["counts"].get("wrong", 0) + g["counts"].get("lucky", 0) for g in grades) / n, 2),
            "unsupported_answers": round(sum(unsupported) / n, 2),
            "per_question": {r["id"]: [g["rows"][i]["grade"] for g in grades] for i, r in enumerate(grades[0]["rows"])},
        }
    secs = [c["wall_seconds"] for c in log["calls"] if "error" not in c]
    label = log["model"] + (" (thinking)" if log.get("config", {}).get("think") is True else "")
    return {"model": label, "file": None, "conditions": out,
            "errors": sum("error" in c for c in log["calls"]),
            "avg_seconds": round(sum(secs) / len(secs), 1) if secs else None}


def summarize() -> str:
    rows = []
    for f in sorted(RUNS.glob("bench-*.json")):
        log = json.loads(f.read_text(encoding="utf-8"))
        s = score(log)
        s["file"] = f.name
        rows.append(s)
    lines = ["# Benchmark results", "",
             "Generated by `benchmarks/run_benchmark.py --summarize` from the raw runs in `benchmarks/runs/`.",
             "Ten reconstruction questions; nine are answerable from the surviving archive, one (Q10) is not, "
             "so the honest answer to it is `unknown`. Numbers are means over repeats.", "",
             "| model | condition | correct (of 9) | honest unknown (Q10) | wrong | ghosts | committed answers without a valid citation | s/call | run |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in rows:
        for cond in CONDITIONS:
            c = s["conditions"].get(cond)
            if not c:
                continue
            lines.append(f"| {s['model']} | {cond} | {c['correct']} | {c['honest_unknown']} | {c['wrong']} | "
                         f"{c['ghosts']} | {c['unsupported_answers']} | {s['avg_seconds']} | {s['file']} |")
    lines += ["", "*ghost*: a wrong answer stated as observed or inferred, with no citation that survives checking. "
              "*validated*: answers whose citations fail are turned into `unknown`, as the game does.", ""]
    for s in rows:
        lines.append(f"## {s['model']} · {s['file']}")
        lines.append("")
        lines.append("| question | " + " | ".join(CONDITIONS) + " |")
        lines.append("|---|" + "---|" * len(CONDITIONS))
        qids = next(iter(s["conditions"].values()))["per_question"].keys() if s["conditions"] else []
        for qid in qids:
            cells = [", ".join(s["conditions"][c]["per_question"][qid]) if c in s["conditions"] else "" for c in CONDITIONS]
            lines.append(f"| {qid} | " + " | ".join(cells) + " |")
        lines.append("")
    text = "\n".join(lines)
    RESULTS.write_text(text, encoding="utf-8")
    RESULTS.with_suffix(".json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["gemma4:e4b"])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--num-ctx", type=int, default=None)
    ap.add_argument("--only", nargs="*", help="question ids, e.g. Q1 Q3")
    ap.add_argument("--think", choices=["on", "off"], default=None,
                    help="Gemma 4 thinking (default: LW_THINK, off unless set)")
    ap.add_argument("--summarize", action="store_true", help="only rebuild results.md from saved runs")
    args = ap.parse_args()
    if not args.summarize:
        for m in args.models:
            think = None if args.think is None else args.think == "on"
            print("saved", run(m, args.repeats, args.temperature, args.num_ctx, args.only, think))
    print(summarize())
    return 0


if __name__ == "__main__":
    sys.exit(main())
