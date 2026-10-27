#!/usr/bin/env python3
"""The promo's soundtrack: the voice-over, a Morse call sign on the cold open
and, with LW_BED=music, tape hiss and the music from music.py underneath.
No samples, so nothing to license.

    python3 video/sound.py video/out/cues.json video/out/score.wav
"""
import json
import os
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
rng = np.random.default_rng(1999)


def env(n, attack, release):
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def lowpass(x, cutoff):
    """First-order low-pass, applied in the frequency domain."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(spec / np.sqrt(1 + (f / cutoff) ** 2), n=len(x))


def brown(n):
    w = rng.standard_normal(n)
    b = np.cumsum(w)
    b -= np.convolve(b, np.ones(4410) / 4410, mode="same")  # remove drift
    return b / (np.abs(b).max() + 1e-9)


MORSE = {"L": ".-..", "W": ".--", "C": "-.-.", "S": "..."}


def morse(text, wpm=18, f=760):
    dot = 1.2 / wpm
    parts = []
    for ch in text:
        if ch == " ":
            parts.append(np.zeros(int(SR * dot * 4)))
            continue
        for sym in MORSE[ch]:
            d = dot * (3 if sym == "-" else 1)
            tt = np.arange(int(SR * d)) / SR
            parts.append(np.sin(2 * np.pi * f * tt) * env(len(tt), .004, .006))
            parts.append(np.zeros(int(SR * dot)))
        parts.append(np.zeros(int(SR * dot * 2)))
    return np.concatenate(parts)


def thump(dur=1.6):
    tt = np.arange(int(SR * dur)) / SR
    f = 38 + 90 * np.exp(-tt * 9)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-tt * 3.2)


def read_voice(path):
    """A mono WAV, resampled to SR and peak-normalized."""
    with wave.open(path) as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype="<i2").astype(float).reshape(-1, ch).mean(axis=1)
    x = np.interp(np.arange(int(len(x) * SR / sr)) * sr / SR, np.arange(len(x)), x)
    return x / (np.abs(x).max() + 1e-9)


def place(buf, sig, at, gain):
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += gain * sig[: j - i]


def main():
    cues = json.load(open(sys.argv[1]))
    total = cues["total"]
    n = int(SR * total)
    t = np.arange(n) / SR

    # LW_BED=music lays the tape hiss and the music from music.py under the voice;
    # the default is the voice alone, with only the Morse call sign on the cold open
    left, right = np.zeros(n), np.zeros(n)
    if os.environ.get("LW_BED", "none") == "music":
        sys.path.insert(0, str(Path(__file__).parent))
        from music import score
        m_left, m_right, m_start = score(n, cues["cues"])
        peak = max(np.abs(m_left).max(), np.abs(m_right).max(), 1e-9)
        hiss_level = np.clip(1 - (t - m_start) / 5.0, 0.1, 1.0)
        hiss = lowpass(rng.standard_normal(n) * .6 + brown(n) * .4, 3200)
        hiss = hiss / (np.sqrt((hiss ** 2).mean()) + 1e-9) * .09 * hiss_level
        left, right = hiss + m_left / peak, hiss * .95 + m_right / peak
        for c in cues["cues"]:
            if c["name"] == "tape":
                place(left, thump(), c["start"] + .15, .5)
                place(right, thump(), c["start"] + .15, .5)

    # the voice-over sits on top; the music ducks under it
    voice = np.zeros(n)
    duck = np.ones(n)
    for c in cues["cues"]:
        if not c.get("vo"):
            continue
        v = read_voice(c["vo"])
        place(voice, v, c["vo_at"], 1.0)
        i, j = int((c["vo_at"] - .25) * SR), int((c["vo_at"] + len(v) / SR + .3) * SR)
        duck[max(0, i):j] = .45
    k = int(.25 * SR)
    duck = np.convolve(duck, np.ones(k) / k, mode="same")
    bed_peak = max(np.abs(left).max(), np.abs(right).max(), 1e-9)
    left, right = left / bed_peak * .55 * duck, right / bed_peak * .55 * duck
    left, right = left + voice * .9, right + voice * .9
    radio = morse("LW LW")
    place(left, radio, .6, .14)
    place(right, radio, .6, .14)

    fade = env(n, .8, 3.5)
    st = np.stack([left * fade, right * fade], axis=1)
    st /= max(1e-9, np.abs(st).max()) / .89
    pcm = (st * 32767).astype("<i2")
    with wave.open(sys.argv[2], "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"score: {total:.1f} s")


if __name__ == "__main__":
    main()
