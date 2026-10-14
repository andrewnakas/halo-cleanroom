"""Music and ambience for the clean maps (v0.6).

Music: recorded CC0 tracks (cc0/music/<style>/, sources and licences in SOURCES.json; choir and
chant, orchestral battle music, dark sci-fi ambient, strings), one per variation, picked by the
tag's style. Of the retail score only each track's length and its average loudness are used:
the recording is cut to the length (an intro from its start, an ending from its end, a loop
crossfaded into itself) and set to that level with one gain, so it never pumps. Two earlier
tries failed by ear: CC0 sound effects shaped to the outline buzzed, and a numpy synthesiser
sounded nothing like music.

Ambience: smooth noise (wind, room tone, a soft machine hum), no engine samples, which
buzzed. The band outline then gives it the original's colour over time.
"""
import hashlib
import json
import os
import re

import numpy as np
from scipy.signal import butter, lfilter, resample_poly, sosfilt

MUSIC = re.compile(r"sound/music/|sound/sinomatixx/")
STYLES = [
    ("battle", r"perc|battle|rhythm|anfast|jig|iron|scifi|rr2|mor\d|haloperc"),
    ("eerie", r"spooky|nightmare|wierd|misc|magic"),
    ("strings", r"strng|string|cstrng|cello|stringvox"),
    ("choir", r""),
]
ROOT = None            # cc0/music, set by generate_sounds
_tracks = {}


def is_music(rel):
    return bool(MUSIC.search(rel.lower()))


def is_ambience(rel):
    return "/ambience/" in rel.lower()


def _rng(rel):
    return np.random.default_rng(int(hashlib.md5(rel.encode()).hexdigest()[:8], 16))


def _lowpass(x, cut, rate, order=2):
    return sosfilt(butter(order, min(cut, rate * 0.45), "low", fs=rate, output="sos"), x)


def edges(x, rate):
    """30 ms fades at the ends of a variation: the game switches between them at random"""
    k = min(len(x) // 4, int(rate * 0.03))
    if k:
        x = x.copy()
        x[:k] *= np.linspace(0, 1, k)
        x[-k:] *= np.linspace(1, 0, k)
    return x


def level(x, outline, limit=2.0):
    """one gain for the whole variation: its average loudness becomes the original's"""
    loud = [v for v in outline if v > -60]
    if not loud:
        return x
    want = 10 ** (np.mean(loud) / 20)
    have = float(np.sqrt((x[np.abs(x) > 1e-4] ** 2).mean())) if np.any(np.abs(x) > 1e-4) else 1.0
    gain = min(want / max(have, 1e-6), limit, 0.95 / max(np.abs(x).max(), 1e-6))
    return x * gain


def _load(path, rate):
    key = (path, rate)
    if key not in _tracks:
        import soundfile
        data, sr = soundfile.read(path, dtype="float32", always_2d=True)
        x = data.mean(1)
        if sr != rate:
            from math import gcd
            g = gcd(sr, rate)
            x = resample_poly(x, rate // g, sr // g).astype(np.float32)
        # trim leading and trailing silence
        loud = np.flatnonzero(np.abs(x) > 1e-3)
        _tracks[key] = x[loud[0]:loud[-1] + 1] if len(loud) else x
    return _tracks[key]


def _choose(rel, variant, style):
    folder = os.path.join(ROOT, style)
    names = sorted(f for f in os.listdir(folder) if f.lower().endswith((".ogg", ".mp3", ".wav", ".flac")))
    low = rel.lower()
    if "title1" in low and "chant.ogg" in names:
        return os.path.join(folder, "chant.ogg")           # the menu: Gregorian chant
    pick = int(hashlib.md5((rel + "#" + variant).encode()).hexdigest()[:8], 16) % len(names)
    return os.path.join(folder, names[pick])


def music(rel, n, rate, loop, variant=""):
    low = rel.lower()
    style = next(s for s, pattern in STYLES if re.search(pattern, low))
    path = _choose(rel, variant, style)
    track = _load(path, rate)
    xf = min(int(rate * 2.0), n // 4)
    ending = re.search(r"(^|/|_)out", os.path.basename(low)) is not None
    if len(track) >= n + xf:
        if ending:
            x = track[-n:].copy()
        elif loop:
            # a stretch from inside the track (not the very start, varied per variation)
            room = len(track) - n - xf
            start = int(_rng(rel + variant).integers(0, max(room, 0) + 1))
            seg = track[start:start + n + xf].copy()
            ramp = np.linspace(0, 1, xf, dtype=np.float32)
            seg[:xf] = seg[:xf] * ramp + seg[n:n + xf] * (1 - ramp)     # the end runs into the start
            x = seg[:n]
        else:
            x = track[:n].copy()
    else:
        # shorter than the variation: the track repeats with crossfades
        x = np.zeros(n, np.float32)
        pos, step = 0, max(len(track) - xf, 1)
        ramp = np.linspace(0, 1, min(xf, len(track)), dtype=np.float32)
        while pos < n:
            piece = track[:min(len(track), n - pos)].copy()
            k = min(len(ramp), len(piece))
            if pos:
                piece[:k] *= ramp[:k]
                x[pos:pos + k] *= (1 - ramp[:k])
            x[pos:pos + len(piece)] += piece
            pos += step
    if not loop and not ending:
        k = min(n // 3, int(rate * 1.5))
        x[-k:] *= np.linspace(1, 0, k)                       # an intro or a cue ends softly
    if ending:
        k = min(n // 3, int(rate * 0.5))
        x[:k] *= np.linspace(0, 1, k)
    return x.astype(np.float32), os.path.relpath(path, ROOT).replace(chr(92), "/")


def ambience(rel, n, rate, loop):
    """smooth noise for the original's band outline to colour: wind outside, a room inside"""
    rng = _rng(rel)
    low = rel.lower()
    fade = min(n // 4, int(rate * 1.5)) if loop else 0
    total = n + fade
    white = rng.standard_normal(total)
    brown = np.cumsum(white)
    brown -= _lowpass(brown, 8, rate, 1)                       # no drift
    pink = lfilter([0.049922, -0.095993, 0.050613, -0.004408], [1, -2.494956, 2.017265, -0.522189], white)
    t = np.arange(total) / rate
    if "exterior" in low or "wind" in low or "wave" in low:
        gust = 0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t + rng.random() * 6) * np.sin(2 * np.pi * 0.023 * t + 1)
        x = brown / np.abs(brown).max() * gust + 0.25 * _lowpass(pink, 2500, rate) / np.abs(pink).max()
    else:
        hum = sum(a * np.sin(2 * np.pi * f * t + rng.random() * 6) for f, a in ((55.0, 0.05), (110.0, 0.025)))
        x = brown / np.abs(brown).max() + 0.3 * _lowpass(pink, 1200, rate) / np.abs(pink).max() + hum
    if fade:
        ramp = np.linspace(0, 1, fade)
        x[:fade] = x[:fade] * ramp + x[n:n + fade] * (1 - ramp)
    x = x[:n]
    return (x / max(np.abs(x).max(), 1e-6) * 0.6).astype(np.float32)
