"""Clean room: effect sprites (particles, decals, flares, contrails, sky
bodies), drawn from code in the kept colours and sprite rectangles.

Shapes come from the tag's name (a flare is a soft disc, a spark a streak,
smoke a ragged puff). Textures that are added to the scene fade to black at
their edges; ones that darken it fade to white. Briefs were written after one
look at a dirty contact sheet.
"""
import hashlib
import re

import numpy as np
from PIL import Image


def _seed(name, k):
    return int(hashlib.md5(f"{name}#{k}".encode()).hexdigest()[:8], 16)


def noise(w, h, cells, rng):
    """smooth value noise 0..1, (h,w)"""
    g = rng.random((max(2, cells), max(2, cells))).astype(np.float32)
    return np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255


def shape(kind, w, h, rng):
    """mask 0..1 of one sprite, (h,w)"""
    y, x = np.mgrid[0:h, 0:w]
    u, v = (x + 0.5) / w * 2 - 1, (y + 0.5) / h * 2 - 1
    r = np.hypot(u, v)
    if kind == "ring":
        return np.clip(1 - np.abs(r - 0.72) / 0.12, 0, 1) ** 1.5
    if kind == "streak":
        core = np.clip(1 - np.abs(v) / 0.28, 0, 1) ** 2 * np.clip(1 - np.abs(u) ** 3, 0, 1)
        return core * (0.7 + 0.3 * noise(w, h, 6, rng))
    if kind == "star":
        ang = np.arctan2(v, u)
        rays = 0.25 + 0.75 * np.abs(np.cos(ang * 4)) ** 8
        return np.clip(1 - r / (0.25 + 0.7 * rays), 0, 1) ** 1.5
    if kind == "puff":
        n = noise(w, h, 5, rng) * 0.6 + noise(w, h, 11, rng) * 0.4
        return np.clip((1 - r * (0.9 + 0.5 * n)) * 1.6, 0, 1) * (0.55 + 0.45 * n)
    if kind == "splat":
        ang = np.arctan2(v, u)
        lobes = 0.55 + 0.3 * np.sin(ang * rng.integers(3, 7) + rng.random() * 6) + 0.2 * noise(w, h, 7, rng)
        return np.clip((lobes - r) * 6, 0, 1)
    if kind == "chip":
        ang = rng.random() * 3.14
        a, b = u * np.cos(ang) + v * np.sin(ang), -u * np.sin(ang) + v * np.cos(ang)
        return ((np.abs(a) < 0.6) & (np.abs(b) < 0.3 + 0.2 * a)).astype(np.float32)
    if kind == "disc":
        return np.clip((0.92 - r) * w / 4, 0, 1)
    return np.clip(1 - r, 0, 1) ** 2            # soft


KINDS = [
    (r"ring", "ring"), (r"spark|tracer|bolt|contrail|flash h ar|electric|treadmark|spike", "streak"),
    (r"muzzle|detonate|shell flash|impact burst|flash", "star"),
    (r"smoke|cloud|dust|burst|flame|fire|steam|snow|bubbles|ripple|mask", "puff"),
    (r"splat|burn|blood|dirt|ice|stone|metal|glass|hole|scorch", "splat"),
    (r"chip|casing|debris|gravel|bits|bunch|shirt|rubber", "chip"),
]


def kind_for(name):
    for pattern, kind in KINDS:
        if re.search(pattern, name):
            return kind
    return "soft"


def effect(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    facts = im["faces"][face]
    grid = np.asarray(facts["grid"], np.float32)
    lum = grid.mean(1)
    bright, dark, mean = grid[lum.argmax()], grid[lum.argmin()], grid.mean(0)
    if bright.max() > 8:
        bright = bright * min(3.0, 255 / bright.max())      # the grid dims a small bright core
    boxes = [s["rect"] for seq in sk.sequences for s in seq["sprites"] if s["bitmap"] == index] or [(0, 0, 1, 1)]
    kind = kind_for(name)
    mask = np.zeros((h, w), np.float32)
    for k, (l, t, r, b) in enumerate(boxes):
        x0, y0, x1, y1 = int(round(l * w)), int(round(t * h)), int(round(r * w)), int(round(b * h))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        m = shape(kind, x1 - x0, y1 - y0, np.random.default_rng(_seed(name, k)))
        mask[y0:y1, x0:x1] = np.maximum(mask[y0:y1, x0:x1], m[:y1 - y0, :x1 - x0])
    out = np.empty((h, w, 4), np.float32)
    if facts["alpha"] == "opaque":
        if mean.mean() < 120:       # added to the scene: black where there is nothing
            out[..., :3] = bright * mask[..., None]
        else:                       # darkens the scene: white where there is nothing
            out[..., :3] = 255 + (dark - 255) * mask[..., None]
        out[..., 3] = 255
    else:
        out[..., :3] = bright * (0.55 + 0.45 * mask[..., None])
        out[..., 3] = (mask > 0.4) * 255 if facts["alpha"] == "binary" else mask * 255
    return out


def stars(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    rng = np.random.default_rng(_seed(name, index))
    out = np.zeros((h, w, 4), np.float32)
    n = w * h // 180
    ys, xs = rng.integers(0, h, n), rng.integers(0, w, n)
    out[ys, xs, :3] = (rng.random((n, 1)) ** 3 * 215 + 40) * np.array([1, 1, 1], np.float32)
    out[..., 3] = 255 if im["faces"][face]["alpha"] == "opaque" else out[..., :3].max(-1)
    return out


def planet(name, tag, sk, index, im, face, base):
    """a lit ball in the kept colours"""
    w, h = im["w"], im["h"]
    y, x = np.mgrid[0:h, 0:w]
    u, v = (x + 0.5) / w * 2 - 1, (y + 0.5) / h * 2 - 1
    r2 = u * u + v * v
    z = np.sqrt(np.clip(0.96 - r2, 0, 1))
    light = np.clip(0.25 + 0.75 * (0.5 * z - 0.45 * u - 0.35 * v + 0.35), 0, 1.15)
    rng = np.random.default_rng(_seed(name, 0))
    bands = 0.8 + 0.4 * noise(w, h, 9, rng)
    inside = np.clip((0.96 - r2) * w / 6, 0, 1)
    out = np.empty((h, w, 4), np.float32)
    out[..., :3] = np.clip(base * (light * bands)[..., None] * 1.25, 0, 255) * inside[..., None]
    out[..., 3] = 255 if im["faces"][face]["alpha"] == "opaque" else inside * 255
    return out


DRAWERS = [
    (r"^sky/.*(stars|star twinkle)|/stars\.bitmap", stars),
    (r"^sky/planets/", planet),
    (r"^effects/(?!zmaps)|lens|flare|contrail|glow|^sky/.*(galaxy|star mask|cloud mask)", effect),
]
