"""Dirty room: tags extracted from the retail maps -> spec (the kept facts).

    python -m games.halo.extract_tags <dirty tags> <spec dir> [--add] [--redo bitmaps]

--add keeps the spec and extracts only tags it does not hold yet (new maps);
--redo bitmaps recomputes the bitmap facts of every tag (a changed rule).

Kept as they are: every tag that is not a bitmap, sound or font (geometry,
collision, scenario, scripts, numeric tuning, strings).
Coarse only:
  bitmap  skeleton tag (pixels zeroed) + per image a 4x4 colour grid, an
          alpha class (opaque / binary / gradient) and, where the image is not
          opaque, its alpha outline at 2 bits per texel (spec/alpha2/<tag>/<image>_<face>.bin,
          the rule of the SM64 clean room; owner's decision 2026-10-09)
  sound   skeleton tag (samples and mouth data zeroed) + per permutation its
          length and a loudness outline (RMS in 3 dB steps, <= 32 points)
  font    skeleton tag (glyph pixels zeroed; metrics are numbers)
The spec is the only input of the clean room (games/halo/generate.py).
"""
import json
import os
import shutil
import sys

import numpy as np

from cleanroom.decomp.spec import alpha2

from . import tags
from .codecs import decode_xbox_adpcm

ASSET = (".bitmap", ".sound", ".font")


def grid4(rgba):
    """4x4 grid of the visible colour: [[r,g,b] * 16]"""
    h, w, _ = rgba.shape
    ys = (np.arange(4 + 1) * h) // 4
    xs = (np.arange(4 + 1) * w) // 4
    out = []
    for j in range(4):
        for i in range(4):
            cell = rgba[ys[j]:max(ys[j + 1], ys[j] + 1), xs[i]:max(xs[i + 1], xs[i] + 1)].reshape(-1, 4).astype(np.float64)
            wgt = cell[:, 3:4] + 1.0
            out.append([int(round(v)) for v in (cell[:, :3] * wgt).sum(0) / wgt.sum()])
    return out


def alpha_class(rgba):
    a = rgba[..., 3]
    if a.min() >= 250:
        return "opaque"
    mid = ((a > 16) & (a < 240)).mean()
    return "binary" if mid < 0.02 else "gradient"


def bitmap_facts(tag, outline_dir=None):
    images = []
    for i, b in enumerate(tag.bitmaps):
        faces = []
        for face in range(b.faces):
            rgba = b.read(0, face)
            fact = {"grid": grid4(rgba), "alpha": alpha_class(rgba)}
            if outline_dir and fact["alpha"] != "opaque" and rgba.ndim == 3:
                os.makedirs(outline_dir, exist_ok=True)
                open(os.path.join(outline_dir, f"{i}_{face}.bin"), "wb").write(bytes.fromhex(alpha2(rgba[..., 3])))
                fact["alpha2"] = 1
            faces.append(fact)
        images.append({"w": b.width, "h": b.height, "d": b.depth, "type": b.type, "format": b.format,
                       "mips": b.mipmaps, "faces": faces})
    return {"type": tag.type, "usage": tag.usage, "images": images,
            "sprites": sum(len(s["sprites"]) for s in tag.sequences)}


def outline(pcm, rate):
    """loudness outline: RMS per window in 3 dB steps (dBFS), at most 32 points"""
    mono = pcm.astype(np.float64).mean(1)
    n = len(mono)
    points = int(min(32, max(1, n // (rate // 20))))
    edges = (np.arange(points + 1) * n) // points
    out = []
    for i in range(points):
        seg = mono[edges[i]:max(edges[i + 1], edges[i] + 1)]
        rms = np.sqrt((seg ** 2).mean()) / 32768
        out.append(int(max(-60, 3 * round(20 * np.log10(max(rms, 1e-6)) / 3))))
    return out


def main():
    src, spec = sys.argv[1], sys.argv[2]
    add = "--add" in sys.argv
    redo = sys.argv[sys.argv.index("--redo") + 1] if "--redo" in sys.argv else ""
    out_tags = os.path.join(spec, "tags")
    out_alpha = os.path.join(spec, "alpha2")
    bitmaps, sounds, kept, fonts, new = {}, {}, 0, 0, 0
    if add or redo:
        bitmaps = json.load(open(os.path.join(spec, "bitmaps.json")))
        sounds = json.load(open(os.path.join(spec, "sounds.json")))
    elif os.path.isdir(out_tags):
        shutil.rmtree(out_tags)
        shutil.rmtree(out_alpha, ignore_errors=True)
    for root, _, files in os.walk(src):
        for name in files:
            p = os.path.join(root, name)
            rel = os.path.relpath(p, src).replace("\\", "/")
            dest = os.path.join(out_tags, rel)
            have = (add or redo) and os.path.exists(dest)
            if have and not (redo == "bitmaps" and name.endswith(".bitmap")):
                kept += not name.endswith(ASSET)
                fonts += name.endswith(".font")
                continue
            new += not have
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if name.endswith(".bitmap"):
                t = tags.BitmapTag(p)
                shutil.rmtree(os.path.join(out_alpha, rel), ignore_errors=True)
                bitmaps[rel] = bitmap_facts(t, os.path.join(out_alpha, rel))
                t.data[t.pixels:t.pixels + t.pixel_bytes] = bytes(t.pixel_bytes)
                t.save(dest)
            elif name.endswith(".sound"):
                t = tags.SoundTag(p)
                perms = []
                for pm in t.permutations:
                    pcm = decode_xbox_adpcm(t.samples(pm), t.channels) if pm["compression"] == 1 else np.zeros((1, 1))
                    perms.append({"name": pm["name"], "range": pm["range"], "next": pm["next"], "actual": pm["actual"],
                                  "samples": int(len(pcm)),
                                  "outline": outline(pcm, t.rate)})
                    t.data[pm["offset"]:pm["offset"] + pm["size"] + pm["mouth_size"]] = bytes(pm["size"] + pm["mouth_size"])
                sounds[rel] = {"class": t.sound_class, "rate": t.rate, "channels": t.channels, "perms": perms}
                t.save(dest)
            elif name.endswith(".font"):
                t = tags.FontTag(p)
                t.data[t.pixels:] = bytes(t.pixel_bytes)
                t.save(dest)
                fonts += 1
            else:
                shutil.copyfile(p, dest)
                kept += 1
    json.dump(bitmaps, open(os.path.join(spec, "bitmaps.json"), "w"), separators=(",", ":"))
    json.dump(sounds, open(os.path.join(spec, "sounds.json"), "w"), separators=(",", ":"))
    images = sum(len(b["images"]) for b in bitmaps.values())
    perms = sum(len(s["perms"]) for s in sounds.values())
    print(f"kept {kept} tags; {len(bitmaps)} bitmap tags ({images} images), "
          f"{len(sounds)} sounds ({perms} permutations), {fonts} fonts; {new} new; "
          f"{sum(f.get('alpha2', 0) for b in bitmaps.values() for im in b['images'] for f in im['faces'])} "
          f"alpha outlines -> {spec}")


if __name__ == "__main__":
    main()
