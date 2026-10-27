# world/ — SPOILERS

This folder is the **sealed side** of Last Witness: the canonical history of the
Lighthouse Network and the complete, undamaged archive it left behind.

If you want to play, stop here and open the game instead.

- `truth.json` — characters, the canonical timeline, and the 10-question
  reconstruction form with its answer key. Only the evaluator reads it, and only
  after the player presses **Reveal**.
- `source/*.lw` — every original artifact, before the archive was destroyed.
  `authoring/build_archive.py` runs a seeded "controlled destruction" over these
  files and writes the only thing the investigator ever sees:
  `dataset/archive.json`.

The investigator (the local model) never receives anything from this folder.
That boundary is enforced in code and covered by tests, but it is not a secret:
this is an open-source repository and the answer key is right here. The game is
honest about that, the same way a crossword prints its solution on another page.
