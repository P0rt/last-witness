# Last Witness

> The internet forgets. The evidence doesn't.

In October 1999 a small online community of radio listeners, **the Lighthouse
Network**, went offline. Twenty-seven years later a damaged backup tape turns up.
You get what could be read from it, and a local open-weight AI investigator
that has never been told what happened.

Last Witness is a digital-archaeology game and an experiment: a fictional
community with a **known, sealed history**, an archive that was **deliberately
destroyed** with a seeded process, and an investigator that has to separate what
the evidence shows from what merely sounds plausible. When you press **Reveal**,
every claim the model made is checked against the truth. The ones nothing in
the archive supports are the ghosts.

> Built for the DEV Hacktoberfest 2026 Open-Source AI Challenge, Week 4:
> *Ghost in the Machine*. Work in progress; started October 27, 2026.

## Status

| Part | State |
|---|---|
| Canonical story, characters, 10-question reconstruction form | done (`world/`, spoilers) |
| ~70 authored artifacts: 1999 HTML pages, forum, mail, guestbook, logs | done |
| Seeded controlled destruction + dataset validation | done |
| Investigator core: sentence-id citations, quote checking, ghost detection | done |
| Local model check (`scripts/spike.py`) | ready to run |
| FastAPI server (investigation state, Objection, hypotheses, timeline, form, Reveal) | done |
| Archive UI | in progress |
| Ablation benchmark (`benchmarks/run_benchmark.py`) | ready to run |
| Static replay on GitHub Pages | next |

## How it works

```
world/source/*.lw  ──build_archive.py (seed 1999)──▶  dataset/archive.json  ──▶  investigator (Gemma 4 via Ollama)
  (sealed: every                                     (58 of 151 files                      │
   original file)                                      survive, ids A01…)                   ▼
world/truth.json  ─────────────────────────────────────────────────────────────▶  evaluator, only after Reveal
```

* **Citations are sentence ids plus a verbatim quote**, e.g. `A36:s12 "That's two
  recordings joined together."` The id is constrained by the JSON schema handed
  to Ollama, so the model cannot cite a sentence that does not exist. The quote is
  then checked against that sentence. A claim stated as fact with no citation that
  holds up is marked as a **ghost**.
* **The investigator only sees the archive.** `server/` never reads `world/`; a test
  enforces it. The archive carries neutral ids and no authoring metadata;
  `validate_dataset.py` checks for leaks.
* **The destruction is controlled, not random noise.** Files that carry the story
  always survive; everything else survives with probability 0.55 and may be
  damaged. The validator proves, for any seed, that every observable event still
  has word-for-word evidence, every contradiction has both sides, and no single
  file gives away more than three answers.

## Quick start

Requires Python 3.11+ and, for real runs, [Ollama](https://ollama.com).

```bash
make data          # rebuild dataset/archive.json from world/source (seed 1999)
make validate      # check the archive is still a fair, solvable mystery
make test

ollama pull gemma4:e4b
python scripts/spike.py                     # 6 questions, prints citation validity and ghosts
python scripts/spike.py --model gemma4:12b  # compare a larger model
python benchmarks/run_benchmark.py --models gemma4:e4b --repeats 3   # ablation -> benchmarks/results.md

pip install -r requirements.txt
uvicorn lastwitness.app:app --app-dir server --port 8000   # API (+ the built UI from web/dist)
```

`LW_MODEL`, `LW_NUM_CTX` (default 32768; the whole archive is about 16K tokens)
and `OLLAMA_HOST` override the defaults.

## Repository map

```
world/        SPOILERS. truth.json (canon + answer key) and source/ (undamaged originals)
authoring/    build_archive.py (destruction), validate_dataset.py (fairness checks)
dataset/      archive.json and questions.json: everything the investigator may see
server/       investigator core (Python); API next
scripts/      spike.py: local model check
tests/        pytest
```

## License

MIT. The Lighthouse Network, its members and every document in this repository
are fiction, written for this project. Any resemblance to real people is
coincidental. Host names and IP addresses use reserved example ranges.
