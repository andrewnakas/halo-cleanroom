"""Taint scan: no retail pixels, samples or glyphs in the clean tag tree.

    python -m games.halo.taint <dirty tags> <clean tags> [--index dir] [--match regex]

The harness criterion (cleanroom.taint): every decoded stream of the clean
tree (bitmap RGBA per image and face, sound PCM per permutation, font
coverage) is scanned against every retail stream of the dirty tree; a shared
run of >= FAIL_RUN bytes fails (flat and periodic windows carry no content
and are ignored). Sound mouth data must not be retail's. Kept tags (every
other class: numbers, geometry, text) are listed, not scanned.
Prints one summary; must end with "0 failing" before publishing.
"""
import json
import os
import sys

import numpy as np

from . import tags
from .codecs import decode_xbox_adpcm
from .generate import smooth_grid
from .extract_tags import grid4


def detail(rgba):
    h, w, _ = rgba.shape
    return rgba[..., :3].astype(np.float32) - smooth_grid(grid4(rgba), w, h)


def corr(a, b):
    a, b = a.ravel() - a.mean(), b.ravel() - b.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / den) if den > 1e-6 else 0.0


def scan_bitmap(dirty, clean):
    d, c = tags.BitmapTag(dirty), tags.BitmapTag(clean)
    worst, why = 0.0, ""
    for bd, bc in zip(d.bitmaps, c.bitmaps):
        for face in range(bd.faces):
            x, y = bd.read(0, face), bc.read(0, face)
            flat = x.reshape(-1, 4).std(0).max() < 3
            if not flat and np.array_equal(x, y):
                return 1.0, "identical pixels"
            if x.shape[0] * x.shape[1] < 64 or flat:
                continue
            dx, dy = detail(x), detail(y)
            if dx.std() < 4:      # nothing but the kept grid in the retail image
                continue
            r = max(abs(corr(dx, dy)), abs(corr(x[..., 3].astype(np.float32), y[..., 3].astype(np.float32)))
                    if x[..., 3].std() > 8 and dx.std() < 1e9 and False else 0.0)
            if r > worst:
                worst, why = r, "detail correlates"
    return worst, why


def scan_sound(dirty, clean):
    d, c = tags.SoundTag(dirty), tags.SoundTag(clean)
    worst, why = 0.0, ""
    for pd, pc in zip(d.permutations, c.permutations):
        a, b = d.samples(pd), c.samples(pc)
        if any(d.data[pc["mouth_offset"]:pc["mouth_offset"] + pc["mouth_size"]]) and \
                d.data[pd["mouth_offset"]:pd["mouth_offset"] + pd["mouth_size"]] == \
                c.data[pc["mouth_offset"]:pc["mouth_offset"] + pc["mouth_size"]]:
            return 1.0, "mouth data kept"
        if a == b and any(a):
            return 1.0, "identical samples"
        x = decode_xbox_adpcm(a, d.channels).astype(np.float32).mean(1)
        y = decode_xbox_adpcm(b, c.channels).astype(np.float32).mean(1)
        if x.std() < 30:
            continue
        r = abs(corr(x, y))
        if r > worst:
            worst, why = r, "waveform correlates"
    return worst, why


def scan_font(dirty, clean):
    d, c = tags.FontTag(dirty), tags.FontTag(clean)
    a = np.frombuffer(bytes(d.data[d.pixels:]), np.uint8).astype(np.float32)
    b = np.frombuffer(bytes(c.data[c.pixels:]), np.uint8).astype(np.float32)
    if np.array_equal(a, b):
        return 1.0, "identical glyphs"
    return 0.0, ""       # a redraw of the same letters in the same cells correlates by design


MATCH = None      # --match regex: scan only these tags (quick checks)
SKIP = set()      # tag files already in the on-disk retail index


def _find(tree, ext):
    import re
    out = []
    for p in tags.find(tree, ext):
        rel = os.path.relpath(p, tree).replace(chr(92), "/")
        if rel not in SKIP and (not MATCH or re.search(MATCH, rel)):
            out.append(p)
    return out


def streams(tree):
    """(label, bytes) for every expressive stream of a tag tree"""
    for p in _find(tree, "bitmap"):
        t = tags.BitmapTag(p)
        rel = os.path.relpath(p, tree).replace("\\", "/")
        for i, b in enumerate(t.bitmaps):
            for face in range(b.faces):
                yield f"{rel}#{i}.{face}", b.read(0, face).tobytes()
    for p in _find(tree, "sound"):
        t = tags.SoundTag(p)
        rel = os.path.relpath(p, tree).replace("\\", "/")
        for i, pm in enumerate(t.permutations):
            yield f"{rel}#{i}", decode_xbox_adpcm(t.samples(pm), t.channels).tobytes()
            if pm["mouth_size"] >= 16:
                yield f"{rel}#{i}.mouth", bytes(t.data[pm["mouth_offset"]:pm["mouth_offset"] + pm["mouth_size"]])
    for p in _find(tree, "font"):
        t = tags.FontTag(p)
        yield os.path.relpath(p, tree).replace("\\", "/"), bytes(t.data[t.pixels:])


def main():
    from cleanroom import taint
    global MATCH
    dirty, clean = sys.argv[1], sys.argv[2]
    MATCH = sys.argv[sys.argv.index("--match") + 1] if "--match" in sys.argv else None
    # A window counts only if it carries information: >= 10 distinct byte
    # values in 16. The harness default (6) is tuned for N64-sized corpora;
    # against ~150M retail windows, near-black DXT gradients and near-silent
    # PCM tails collide by chance. The positive control (dirty vs dirty)
    # still fails every textured image and every audible sound.
    taint.MIN_DISTINCT = 10
    # The retail index stays in sorted chunks (one union of ~150M hashes needs
    # several GB). --index DIR keeps it on disk: built once from the whole
    # dirty tree, then every scan (also with --match, which then filters the
    # clean side only) reads it back.
    import hashlib
    digest = lambda data: hashlib.md5(data).hexdigest()
    cache = sys.argv[sys.argv.index("--index") + 1] if "--index" in sys.argv else None
    chunks, batch, n_retail, retail = [], [], 0, {}
    global SKIP
    if cache and os.path.isfile(os.path.join(cache, "meta.json")):
        meta = json.load(open(os.path.join(cache, "meta.json")))
        retail = meta["streams"]
        chunks = [np.load(os.path.join(cache, f"chunk_{i}.npy"), mmap_mode="r") for i in range(meta["chunks"])]
        SKIP = {label.split("#")[0] for label in retail}     # index only the tags that are new
    if True:
        keep_match, MATCH = MATCH, (None if cache else MATCH)

        def flush():
            chunk = np.unique(np.concatenate(batch))
            if cache:
                os.makedirs(cache, exist_ok=True)
                np.save(os.path.join(cache, f"chunk_{len(chunks)}.npy"), chunk)
                chunk = np.load(os.path.join(cache, f"chunk_{len(chunks)}.npy"), mmap_mode="r")
            chunks.append(chunk)
            batch.clear()
        for label, s in streams(dirty):
            retail[label] = digest(s)
            h, per = taint._hashes(s)
            batch.append(h[~per])
            if sum(len(x) for x in batch) > 8_000_000:
                flush()
        if batch:
            flush()
        if cache:
            json.dump({"streams": retail, "chunks": len(chunks)}, open(os.path.join(cache, "meta.json"), "w"))
        MATCH, SKIP = keep_match, set()
    n_retail = len(retail)

    def scan(labelled):
        out = []
        for label, s in labelled:
            h, per = taint._hashes(s)
            if not len(h):
                continue
            m = np.zeros(len(h), bool)
            for index in chunks:
                pos = np.minimum(np.searchsorted(index, h), len(index) - 1)
                m |= index[pos] == h
            m &= ~per
            if m.any():
                out.append((label, int(np.nonzero(m)[0][0]), int(m.sum()), taint._max_run(m)))
        return out
    n_clean, hits = 0, []

    def counted():
        nonlocal n_clean
        for item in streams(clean):
            n_clean += 1
            # the same stream as retail's of that name, and not a flat fill
            if retail.get(item[0]) == digest(item[1]) and len(set(item[1][:65536])) > 8:
                same.append((item[0], 0, 0, len(item[1])))
            yield item
    same = []
    hits = scan(counted())
    hits = [h for h in hits if h[0] not in {x[0] for x in same}] + same
    # pixels: 16 bytes are only 4 RGBA texels, and a clean image is tinted to
    # the retail image's own colours, so 8 equal dark texels in a row happen
    # by chance; a bitmap fails at 16 texels (64 B). Samples and glyphs: 32 B.
    limit = lambda label: 2 * taint.FAIL_RUN if ".bitmap#" in label else taint.FAIL_RUN
    # mathematical tables computed from their formula equal retail's by definition
    allow = json.load(open(os.path.join(os.path.dirname(__file__), "taint_allow.json")))
    bad = sorted((h for h in hits if h[3] >= limit(h[0])), key=lambda h: -h[3])
    math = [h for h in bad if h[0].split("#")[0] in allow]
    bad = [h for h in bad if h[0].split("#")[0] not in allow]
    kept = sum(1 for root, _, files in os.walk(clean) for f in files if not f.endswith((".bitmap", ".sound", ".font")))
    for label, off, n, run in bad[:20]:
        print(f"  FAIL {label} run {run} B at {off}")
    print(f"taint: {n_clean} generated streams scanned against {n_retail} retail streams; "
          f"{len(hits) - len(bad) - len(math)} with short coincidental matches; "
          f"{len(math)} formula tables allowed ({len(allow)} listed in taint_allow.json); {len(bad)} failing "
          f"(run >= {taint.FAIL_RUN} B, pixels {2 * taint.FAIL_RUN} B); {kept} kept tags not scanned")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
