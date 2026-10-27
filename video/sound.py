#!/usr/bin/env python3
"""The promo's score, synthesized: tape hiss, a low radio drone, Morse, and a
thump on the big cards. No samples, so nothing to license.

    python3 video/sound.py video/out/cues.json video/out/score.wav
"""
import json
import sys
import wave

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


def drone(n, t):
    out = np.zeros(n)
    for f, g in [(55.0, .5), (55.4, .35), (82.41, .3), (110.0, .18), (130.81, .12), (164.81, .06)]:
        lfo = .65 + .35 * np.sin(2 * np.pi * (0.05 + f / 4000) * t + f)
        out += g * lfo * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28))
    return out / 1.5


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

    # hiss louder on title cards, quieter under the game footage
    card_level = np.full(n, .35)
    for c in cues["cues"]:
        i, j = int(c["start"] * SR), int((c["start"] + c["dur"]) * SR)
        card_level[i:j] = 1.0 if c["card"] else .45
    card_level = np.convolve(card_level, np.ones(SR // 2) / (SR // 2), mode="same")
    hiss = lowpass(rng.standard_normal(n) * .6 + brown(n) * .4, 3200) * card_level * .10

    pad = drone(n, t) * env(n, 4.0, 5.0) * .22
    # the drone opens up for the second half
    pad *= np.clip(.55 + t / total, 0, 1.2)

    left = hiss + pad
    right = hiss * .9 + np.roll(pad, int(.012 * SR))

    radio = morse("LW LW")
    place(left, radio, .6, .10)
    place(right, radio, .6, .10)
    for c in cues["cues"]:
        if c["name"] in ("tape", "reveal", "numbers", "end"):
            th = thump()
            place(left, th, c["start"] + .15, .55)
            place(right, th, c["start"] + .15, .55)
        if c["name"] == "partner":
            place(left, morse("CS"), c["start"] + .3, .06)

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
