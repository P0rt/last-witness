# The promo video

Everything in the video is made from this repository: the title cards are
`cards.html`, the game footage is the static replay of a real Gemma run, the
score is synthesized by `sound.py`, and the narration is `script.json`.

```bash
(cd web && npm run build:replay)
LW_VOICE_DIR=path/to/voice/bm_george node video/make_promo.mjs
# -> video/out/last-witness-promo.mp4, plus explore.gif, ask.gif, verdict.gif for the post
node video/make_promo.mjs ask verdict    # re-record single scenes while tuning
```

Each scene lasts as long as its line of narration, plus a little air. Without
`LW_VOICE_DIR`, scenes are timed from the script and the video has no voice.

## Narration

`script.json` was read by [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)
v1.0 (Apache-2.0), an open-weight text-to-speech model, through
[kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) 0.6.1 (MIT) with the
`kokoro-v1.0.onnx` and `voices-v1.0.bin` files from its `model-files-v1.0`
release. Phonemes come from espeak-ng (GPL-3.0), via espeakng-loader. Voices:
`bm_george` (en-gb), with `am_michael` and `af_heart` (en-us) as alternates.
One mono 24 kHz WAV per line, named `<scene id>.wav`. The audio is not
committed.

## Fonts

See `fonts/README.md`. All are open-licensed.
