"""The promo's music, written as code: a slow piece in A minor for felt piano,
string pad and a little bass, laid out on the video's scene cues.

    Am(add9) | Fmaj7 | C(add9) | G6/B      70 bpm, one chord per bar

The piano carries a four-bar motif that rises over A minor and falls back over
F. Layers enter with the story: pad and piano once the game appears, a soft
arpeggio while the investigator reasons, bass under the Reveal, and the motif
alone at the end, ringing out on the first chord.
"""
import numpy as np

SR = 44100
BPM = 70
BEAT = 60 / BPM
BAR = 4 * BEAT
rng = np.random.default_rng(47)

CHORDS = [  # MIDI voicings, root first
    [45, 52, 60, 64, 71],  # Am(add9)
    [41, 48, 57, 64, 67],  # Fmaj7(9)
    [48, 55, 62, 64, 72],  # C(add9)
    [47, 55, 62, 64, 67],  # G6/B
]
# the motif: (bar in phrase, beat, midi, beats held)
MOTIF = [
    (0, 0, 76, 1.5), (0, 1.5, 72, 1), (0, 2.5, 71, 1.5),
    (1, 0, 69, 1), (1, 1, 72, 1), (1, 2, 76, 2),
    (2, 0, 74, 1.5), (2, 1.5, 76, 1), (2, 2.5, 67, 1.5),
    (3, 0, 71, 1), (3, 1, 74, 1), (3, 2, 71, 2),
]
ENDING = [(0, 0, 76, 1.5), (0, 1.5, 72, 1), (0, 2.5, 71, 1), (0, 3.5, 69, 4)]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def add(buf, sig, at):
    i = int(at * SR)
    if i >= len(buf) or i + len(sig) <= 0:
        return
    s0 = max(0, -i)
    j = min(len(buf), i + len(sig))
    buf[max(0, i):j] += sig[s0: s0 + j - max(0, i)]


def piano(m, vel=1.0, length=5.0):
    """Felt piano: a few slightly inharmonic partials, the high ones dying first."""
    t = np.arange(int(length * SR)) / SR
    f, out = hz(m), np.zeros_like(t)
    for k in range(1, 7):
        fk = k * f * np.sqrt(1 + 0.00035 * k * k)
        if fk > 9000:
            break
        out += (vel ** (0.6 + 0.25 * k)) / k ** 1.5 * np.sin(2 * np.pi * fk * t + rng.uniform(0, 6.28)) * np.exp(-t * (0.9 + 0.75 * k))
    att = int(0.006 * SR)
    out[:att] *= np.linspace(0, 1, att)
    rel = int(0.08 * SR)
    out[-rel:] *= np.linspace(1, 0, rel)
    return out * vel


def pad_note(m, length):
    """Three detuned band-limited saws: a soft string section."""
    t = np.arange(int(length * SR)) / SR
    out = np.zeros_like(t)
    for cents in (-8, 0, 7):
        f = hz(m) * 2 ** (cents / 1200)
        for k in range(1, 12):
            if k * f > 2600:
                break
            out += np.sin(2 * np.pi * k * f * t + rng.uniform(0, 6.28)) / k
    return out / 3


def lowpass(x, cutoff, order=2):
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(spec / (1 + (f / cutoff) ** (2 * order)) ** 0.5, n=len(x))


def reverb(x, seconds=3.2, seed=0):
    r = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = r.standard_normal(n) * np.exp(-t * 6.9 / seconds)
    ir = lowpass(ir, 4500, 1)
    ir[: int(0.02 * SR)] = 0  # pre-delay
    ir /= np.sqrt((ir ** 2).sum())
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]


def score(n, cues):
    """Stereo music for a video of n samples, following the scene cues."""
    at = {c["name"]: c for c in cues}
    start = at["explore"]["start"] - BAR / 2       # comes in under the first game footage
    reason_t = at["reason"]["start"]
    reveal_t = at["reveal"]["start"]
    verdict_t = at["verdict"]["start"]
    numbers_t = at["numbers"]["start"]
    end_t = at["end"]["start"]
    total = n / SR

    pad = np.zeros(n)
    keys = np.zeros(n)
    arp = np.zeros(n)
    bass = np.zeros(n)

    bar = 0
    t = start
    while t < total - 0.5:
        chord = CHORDS[bar % 4]
        in_reveal = reveal_t - 0.3 <= t < verdict_t - 0.2
        final = t >= end_t - 0.2
        if final:
            chord = CHORDS[0]
        # pad: every bar, swelling in and crossfading into the next
        if not in_reveal:
            length = BAR + 1.6 if not final else total - t
            env = np.ones(int(length * SR))
            a, r = int(1.4 * SR), int(1.6 * SR)
            env[:a] = np.linspace(0, 1, a) ** 1.5
            env[-r:] *= np.linspace(1, 0, r)
            level = 0.9 if t < verdict_t else 1.15
            for m in chord[1:]:
                add(pad, pad_note(m, length) * env * level * 0.16, t)
        # piano motif: every phrase from the start, again over the numbers and the end
        phrase_bar = bar % 4
        motif_on = (t < reason_t) or (numbers_t - 0.2 <= t < end_t - 0.2)
        if motif_on and not in_reveal:
            for b, beat, m, hold in MOTIF:
                if b == phrase_bar:
                    add(keys, piano(m, 0.55 + 0.1 * rng.random(), hold * BEAT + 2.5), t + beat * BEAT + rng.normal(0, 0.008))
        if final:
            for b, beat, m, hold in ENDING:
                add(keys, piano(m, 0.6, hold * BEAT + 4), t + beat * BEAT)
            for i, m in enumerate(chord):  # the last chord, rolled
                add(keys, piano(m, 0.45, 7), t + 4 * BEAT + i * 0.07)
        # arpeggio while the investigator reasons, and under the verdict
        if reason_t - 0.2 <= t < numbers_t - 0.2 and not in_reveal:
            tones = [m + 12 for m in chord[1:]]
            pattern = [0, 2, 1, 3, 2, 1, 3, 0]
            for i, p in enumerate(pattern):
                if rng.random() < 0.85:
                    add(arp, piano(tones[p % len(tones)], 0.28 + 0.08 * rng.random(), 2.2), t + i * BEAT / 2)
        # bass under the verdict
        if verdict_t - 0.2 <= t < end_t + BAR and not in_reveal:
            ln = BAR + 0.3
            tt = np.arange(int(ln * SR)) / SR
            b = (np.sin(2 * np.pi * hz(chord[0] - 12) * tt) + 0.25 * np.sin(4 * np.pi * hz(chord[0] - 12) * tt))
            b *= np.minimum(1, tt / 0.25) * (0.75 + 0.25 * np.exp(-tt * 2)) * np.minimum(1, (ln - tt) / 0.3)
            add(bass, b * 0.32, t)
        bar += 1
        t = start + bar * BAR

    # the Reveal card: a held breath, one low note
    add(keys, piano(33, 0.9, 6) + piano(45, 0.5, 6), reveal_t + 0.1)

    pad = lowpass(pad, 1100)
    dry = pad + keys * 0.9 + arp * 0.7 + bass
    left = dry * 0.75 + reverb(keys * 0.9 + arp * 0.7 + pad * 0.6, seed=1) * 0.55
    right = dry * 0.75 + reverb(keys * 0.9 + arp * 0.7 + pad * 0.6, seed=2) * 0.55
    # fade the music in under the hiss
    fade = np.clip((np.arange(n) / SR - start) / 4.0, 0, 1) ** 2
    return left * fade, right * fade, start
