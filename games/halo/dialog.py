"""Spoken lines: text out of the dirty room, placeholder voices in the clean room.

    python -m games.halo.dialog transcribe <dirty tags> <spec> [--model medium.en] [--match regex]

Dirty room (owner's decision 2026-10-09): every dialogue sound is transcribed to TEXT with a
speech recogniser; only the text (and the recogniser's confidence) enters the spec as
spec/dialog.json. No audio, no voice model, no timing beyond the kept length and outline.
The run is resumable (lines already in dialog.json are skipped).

Clean room: `speak(...)` voices a line with a Piper voice chosen per character (placeholders
until the owner records; no cloning, nothing trained on retail audio).
"""
import hashlib
from fractions import Fraction
import json
import os
import re
import sys

import numpy as np

PIPER = os.environ.get("PIPER_VOICES", "C:/Users/andre/n64work/piper_voices")

# who -> (piper voice, semitones, pace); pace < 1 speaks faster
CAST = {
    "cortana": ("en_US-amy-medium", 0.0, 0.95),
    "keyes": ("en_US-joe-medium", -1.5, 1.05),
    "chief": ("en_US-ryan-high", -3.0, 1.05),
    "sarge": ("en_US-joe-medium", -2.5, 0.92),
    "pilot": ("en_US-kristin-medium", 0.0, 0.95),
    "monitor": ("en_US-ryan-high", 4.0, 0.9),
    "grunt": ("en_US-joe-medium", 7.0, 0.9),
    "crewman": ("en_US-ryan-high", 0.5, 1.0),
    "marine": ("en_US-ryan-high", -0.5, 0.95),
    "marine2": ("en_US-joe-medium", 0.5, 0.95),
    "marine3": ("en_US-ryan-high", 1.5, 0.92),
    "woman": ("en_US-hfc_female-medium", 0.0, 0.97),
    "announcer": ("en_US-ryan-high", 0.0, 1.0),
}
ALIEN = re.compile(r"/(elite|jackal|hunter|flood|infection|sentinel|engineer)[^/]*/|_(elite|jackal|hunter|flood)\b")


def speaker(rel):
    """Who speaks a dialogue tag, from its path (names in tag paths are kept facts)."""
    low = rel.lower()
    base = os.path.basename(low)
    if low.startswith("sound/dialog/multiplayer"):
        return "announcer"
    if ALIEN.search(low):
        return ""
    for key, who in (("cortana", "cortana"), ("keyes", "keyes"), ("captain", "keyes"), ("chief", "chief"), ("johnson", "sarge"),
                     ("sarge", "sarge"), ("sargeant", "sarge"), ("pilot", "pilot"), ("foehammer", "pilot"),
                     ("monitor", "monitor"), ("spark", "monitor"), ("grunt", "grunt"), ("crewman", "crewman"), ("cryo", "crewman"), ("captkeyes", "keyes"),
                     ("crew", "crewman"), ("bisenti", "marine2"), ("mendoza", "marine3"), ("jenkins", "marine2"),
                     ("fitzgerald", "marine3"), ("female", "woman"), ("marine", "marine")):
        if key in base or f"/{key}" in low:
            if who == "marine":         # several marines: a steady choice per folder
                pick = int(hashlib.md5(os.path.dirname(low).encode()).hexdigest(), 16) % 3
                return ("marine", "marine2", "marine3")[pick]
            return who
    return "marine"


def chains(perms):
    """A long permutation is stored as linked chunks: [[permutation indices of one line]]."""
    heads = [i for i, p in enumerate(perms) if not any(q["next"] == i and q["range"] == p["range"] for q in perms)]
    starts = {}
    for i, p in enumerate(perms):
        starts.setdefault(p["range"], i)
    done, out = set(), []
    for h in heads:
        chain, i = [], h
        while i not in done and i < len(perms):
            chain.append(i)
            done.add(i)
            nxt = perms[i]["next"]
            if nxt == 0xFFFF:
                break
            i = starts[perms[i]["range"]] + nxt
        out.append(chain)
    return out


def is_dialog(rel):
    return "/dialog/" in rel.lower()


# ---------- dirty room

def transcribe(dirty, spec, model="medium.en", match=None):
    from faster_whisper import WhisperModel
    from scipy.signal import resample_poly

    from . import tags
    from .codecs import decode_xbox_adpcm
    out_path = os.path.join(spec, "dialog.json")
    out = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    facts = json.load(open(os.path.join(spec, "sounds.json")))
    todo = [rel for rel in sorted(facts) if is_dialog(rel) and rel not in out and (not match or re.search(match, rel))]
    whisper = None
    lines = kept = 0
    for n, rel in enumerate(todo):
        who = speaker(rel)
        entry = {"who": who, "lines": {}}
        if who and who != "announcer":
            if whisper is None:
                # (the model cache goes on D:; C: has no room for it)
                whisper = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=4,
                                       download_root=os.environ.get("WHISPER_ROOT", "D:/n64work/whisper_models"))
            t = tags.SoundTag(os.path.join(dirty, rel))
            for chain in chains(facts[rel]["perms"]):
                pcm = [decode_xbox_adpcm(t.samples(t.permutations[i]), t.channels) for i in chain
                       if t.permutations[i]["compression"] == 1]
                if not pcm:
                    continue
                x = np.concatenate(pcm).astype(np.float32).mean(1) / 32768
                x = resample_poly(x, 16000, t.rate).astype(np.float32)
                x = np.concatenate([np.zeros(3200, np.float32), x, np.zeros(8000, np.float32)])
                segs, _ = whisper.transcribe(x, language="en", beam_size=5, condition_on_previous_text=False)
                segs = list(segs)
                text = re.sub(r"\s+", " ", " ".join(s.text for s in segs)).strip()
                conf = float(np.exp(np.mean([s.avg_logprob for s in segs]))) if segs else 0.0
                quiet = float(np.mean([s.no_speech_prob for s in segs])) if segs else 1.0
                lines += 1
                if text and conf >= 0.3 and quiet < 0.7:
                    entry["lines"][str(chain[0])] = {"text": text, "conf": round(conf, 2)}
                    kept += 1
        out[rel] = entry
        if n % 25 == 24 or n == len(todo) - 1:
            json.dump(out, open(out_path + ".tmp", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
            os.replace(out_path + ".tmp", out_path)
            print(f"{n + 1}/{len(todo)} tags, {lines} lines heard, {kept} kept", flush=True)
    total = sum(len(e["lines"]) for e in out.values())
    low = sum(1 for e in out.values() for li in e["lines"].values() if li["conf"] < 0.5)
    print(f"dialog: {len(out)} tags, {total} lines with text ({low} under 0.5 confidence) -> {out_path}")


# ---------- clean room

_voices = {}


def _piper(name, text, length):
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    if name not in _voices:
        _voices[name] = PiperVoice.load(os.path.join(PIPER, name + ".onnx"))
    v = _voices[name]
    cfg = SynthesisConfig(length_scale=length)
    x = np.concatenate([c.audio_float_array for c in v.synthesize(text, syn_config=cfg)]).astype(np.float32)
    return x, v.config.sample_rate


def speak(who, text, rate, n):
    """A line as float samples at `rate`, at most n samples when it can be said that fast.
    Pitch is set by speaking slower/faster and resampling (duration is restored)."""
    from scipy.signal import resample_poly
    name, semitones, pace = CAST.get(who, CAST["marine"])
    f = 2 ** (semitones / 12)
    best = None
    for k in range(7):                         # speak faster until the line fits its slot
        raw, sr = _piper(name, text, pace * f * (0.88 ** k))
        ratio = Fraction(rate / (sr * f)).limit_denominator(400)
        x = resample_poly(raw, ratio.numerator, ratio.denominator).astype(np.float32)
        loud = np.flatnonzero(np.abs(x) > 0.01)
        if len(loud):
            x = x[max(0, loud[0] - 200):loud[-1] + 400]
        best = x
        if len(x) <= n:
            break
    return best / max(float(np.abs(best).max()), 1e-6) * 0.9 if len(best) else best


def place(x, n, outline):
    """The spoken line inside its slot: it starts where the kept outline first gets loud."""
    out = np.zeros(n, np.float32)
    if len(x) >= n:
        idx = np.linspace(0, len(x) - 1, n)
        return np.interp(idx, np.arange(len(x)), x).astype(np.float32)
    start = 0
    if outline:
        o = np.asarray(outline, np.float32)
        loud = np.flatnonzero(o > o.max() - 18)
        if len(loud):
            start = int(loud[0] * n / len(o))
    start = max(0, min(start, n - len(x)))
    out[start:start + len(x)] = x
    return out


def main():
    if sys.argv[1] != "transcribe":
        raise SystemExit(__doc__)
    args = sys.argv[2:]
    model = args[args.index("--model") + 1] if "--model" in args else "medium.en"
    match = args[args.index("--match") + 1] if "--match" in args else None
    transcribe(args[0], args[1], model, match)


if __name__ == "__main__":
    main()
