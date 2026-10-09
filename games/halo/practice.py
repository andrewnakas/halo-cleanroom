"""Practice pack for recording the voices (PERSONAL USE: the reference clips are decoded
from the owner's own disc; the pack is written outside the repository and never published).

    python -m games.halo.practice <dirty tags> <spec> <out dir> [--who cortana,keyes] [--max 150]

Per character: numbered reference clips, one call-and-response track (clip, 0.3 s, a short
beep at 880 Hz, then a gap of 1.5x the line + 1.5 s to repeat it) and SCRIPT.txt with the
text of every line and the time it has to fit. Story lines (level folders) come first,
combat chatter after; --max limits the lines per character.
"""
import json
import os
import re
import sys
import wave

import numpy as np

from . import dialog, tags
from .codecs import decode_xbox_adpcm

HZ = 22050
STORY = re.compile(r"sound/dialog/(a\d\d|b\d\d|c\d\d|d\d\d|x\d\d)/")


def main():
    dirty, spec, out = sys.argv[1:4]
    only = sys.argv[sys.argv.index("--who") + 1].split(",") if "--who" in sys.argv else None
    most = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 150
    text = json.load(open(os.path.join(spec, "dialog.json"), encoding="utf-8"))
    facts = json.load(open(os.path.join(spec, "sounds.json")))
    cast = {}
    for rel in sorted(text, key=lambda r: (not STORY.search(r.lower()), r)):
        e = text[rel]
        who = dialog.speaker(rel)
        who = "marine" if who in ("marine2", "marine3") else who
        if not e["lines"] or (only and who not in only):
            continue
        for head, line in e["lines"].items():
            cast.setdefault(who, []).append((rel, int(head), line["text"]))

    def wr(path, x):
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(HZ)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())

    beep = (0.2 * np.sin(2 * np.pi * 880 * np.arange(int(0.08 * HZ)) / HZ)).astype(np.float32)
    report = []
    for who, lines in sorted(cast.items()):
        lines = lines[:most]
        folder = os.path.join(out, who)
        os.makedirs(os.path.join(folder, "clips"), exist_ok=True)
        track = []
        script = [f"{who}: record in this order, 2-3 takes each, in character.",
                  f"Play practice_{who}_call_and_response.wav and speak after each beep.", ""]
        for i, (rel, head, said) in enumerate(lines, 1):
            t = tags.SoundTag(os.path.join(dirty, rel))
            perms = facts[rel]["perms"]
            chain = next(c for c in dialog.chains(perms) if c[0] == head)
            pcm = np.concatenate([decode_xbox_adpcm(t.samples(t.permutations[k]), t.channels) for k in chain])
            x = pcm.astype(np.float32).mean(1) / 32768
            x = np.interp(np.arange(0, len(x) * HZ / t.rate) * t.rate / HZ, np.arange(len(x)), x).astype(np.float32)
            name = os.path.basename(rel)[:-6]
            wr(os.path.join(folder, "clips", f"{i:03d}_{name}.wav"), x)
            gap = np.zeros(int((len(x) / HZ * 1.5 + 1.5) * HZ), np.float32)
            track += [x, np.zeros(int(0.3 * HZ), np.float32), beep, gap]
            script.append(f"{i:03d}  {name:42s} max {len(x) / HZ:4.1f}s  \"{said}\"")
        script += ["", "These clips come from your own disc: practice only, do not share or commit them."]
        wr(os.path.join(folder, f"practice_{who}_call_and_response.wav"), np.concatenate(track))
        open(os.path.join(folder, "SCRIPT.txt"), "w", encoding="utf8").write("\n".join(script))
        report.append(f"{who} {len(lines)}")
    print(f"practice pack -> {out}: " + ", ".join(report))


if __name__ == "__main__":
    main()
