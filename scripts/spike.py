#!/usr/bin/env python3
"""Day-1 model check: can a small local Gemma cite the archive honestly?

    ollama pull gemma4:e4b
    python scripts/spike.py                      # default model
    python scripts/spike.py --model gemma4:12b   # compare a bigger one

Runs 3 free-form questions and 3 form questions against the full surviving
archive, then prints: valid JSON rate, citation validity, ghosts (claims stated
as fact with no citation that survives checking), and seconds per call.
The full transcript is saved under benchmarks/runs/ so it can be inspected and
committed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from lastwitness.investigator import Investigator  # noqa: E402
from lastwitness.llm import LLMError, Ollama  # noqa: E402

FREE = [
    "Why did the Lighthouse Network disappear?",
    "Who is nightjar?",
    "What happened on October 16 and 17, 1999?",
]
FORM = ["Q1", "Q3", "Q10"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--num-ctx", type=int, default=None)
    ap.add_argument("--think", choices=["on", "off"], default=None,
                    help="force the model's thinking on or off (default: the model's own default)")
    args = ap.parse_args()

    llm = Ollama(model=args.model, num_ctx=args.num_ctx,
                 think=None if args.think is None else args.think == "on")
    inv = Investigator(llm)
    questions = {q["id"]: q for q in json.loads((ROOT / "dataset/questions.json").read_text())}
    log: dict = {"model": llm.model_id, "config": llm.config(), "free": [], "form": [], "errors": []}

    calls = ok = 0
    cits = valid = ghosts = claims = 0
    seconds = []
    for q in FREE:
        calls += 1
        print(f"\n>>> {q}")
        try:
            r = inv.ask(q)
        except LLMError as e:
            print("   ERROR", e)
            log["errors"].append({"question": q, "error": str(e)})
            continue
        ok += 1
        seconds.append(r["meta"]["seconds"])
        log["free"].append({"question": q, **r, "ollama": llm.last_stats})
        print("   ", r["answer"][:300])
        for c in r["claims"]:
            claims += 1
            ghosts += c["ghost"]
            for x in c["citations"]:
                cits += 1
                valid += x["valid"]
            mark = "GHOST " if c["ghost"] else ""
            ids = ", ".join(f"{x['sentence_id']}{'' if x['valid'] else '✗'}" for x in c["citations"])
            print(f"    - {mark}[{c['classification']}] {c['text'][:120]}  ({ids})")

    for qid in FORM:
        calls += 1
        q = questions[qid]
        print(f"\n>>> {qid}: {q['text']}")
        try:
            r = inv.answer(q)
        except LLMError as e:
            print("   ERROR", e)
            log["errors"].append({"question": qid, "error": str(e)})
            continue
        ok += 1
        seconds.append(r["meta"]["seconds"])
        log["form"].append({**r, "ollama": llm.last_stats})
        for x in r["citations"]:
            cits += 1
            valid += x["valid"]
        print(f"    choice={r['choice']} [{r['classification']}] supported={r['supported']}")
        print(f"    {r['reasoning'][:300]}")

    summary = {
        "valid_json": f"{ok}/{calls}",
        "citation_validity": f"{valid}/{cits}" + (f" ({100 * valid // cits}%)" if cits else ""),
        "ghost_claims": f"{ghosts}/{claims}",
        "avg_seconds_per_call": round(sum(seconds) / len(seconds), 1) if seconds else None,
    }
    log["summary"] = summary
    out = ROOT / "benchmarks" / "runs" / f"spike-{llm.model_id.replace(':', '_')}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(log, ensure_ascii=False, indent=1))
    print("\n=== summary ===")
    for k, v in summary.items():
        print(f"{k:24} {v}")
    print(f"saved {out.relative_to(ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
