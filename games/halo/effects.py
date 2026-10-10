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
        # an irregular stain: a noisy blob with a few thrown droplets, soft-edged
        n = noise(w, h, 4, rng) * 0.55 + noise(w, h, 9, rng) * 0.3 + noise(w, h, 19, rng) * 0.15
        body = np.clip((0.62 + 0.5 * (n - 0.5) - r) * 5, 0, 1)
        for _ in range(int(rng.integers(3, 8))):
            a, d, size = rng.random() * 6.283, 0.45 + 0.4 * rng.random(), 0.04 + 0.07 * rng.random()
            body = np.maximum(body, np.clip((size - np.hypot(u - d * np.cos(a), v - d * np.sin(a))) * 14, 0, 1))
        return body * (0.75 + 0.25 * n)
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
    (r"splat|burn|blood|hole|scorch|stain|splash", "splat"),
    (r"chip|casing|debris|gravel|bits|bunch|shirt|rubber|dirt|ice|stone|metal|glass", "chip"),
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
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)      # (some rectangles overhang)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        m = shape(kind, x1 - x0, y1 - y0, np.random.default_rng(_seed(name, k)))
        mask[y0:y1, x0:x1] = np.maximum(mask[y0:y1, x0:x1], m[:y1 - y0, :x1 - x0])
    out = np.empty((h, w, 4), np.float32)
    from .drawn import kept_alpha
    kept = kept_alpha(name, index, face, im)
    boxy = False
    if kept is not None:
        inside = np.zeros((h, w), bool)
        for l, t, r, b in boxes:
            inside[max(int(round(t * h)), 0):int(round(b * h)), max(int(round(l * w)), 0):int(round(r * w))] = True
        boxy = inside.any() and (kept[inside] >= 250).mean() > 0.93
    if boxy:
        # the kept alpha is a full rectangle per sprite: the picture lives in the colour
        # (added to or multiplied into the scene), so it is drawn there
        if mean.mean() < 120:
            out[..., :3] = bright * mask[..., None]
        else:
            out[..., :3] = 255 + (dark - 255) * mask[..., None]
        out[..., 3] = kept
        return out
    if kept is not None:
        # the sprite's own silhouette is kept: our colour and grain inside it
        rng = np.random.default_rng(_seed(name, index))
        grain = 0.7 + 0.3 * (noise(w, h, 6, rng) * 0.6 + noise(w, h, 17, rng) * 0.4)
        body = (kept / 255.0) ** 0.6
        low = np.where(mean.mean() > 150, dark, mean)
        out[..., :3] = np.clip((low + (bright - low) * body[..., None]) * grain[..., None], 0, 255)
        out[..., 3] = kept
        return out
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


def galaxy(name, tag, sk, index, im, face, base):
    """a galaxy seen edge on: a bright bulge, a grainy disc with dust lanes, stars around it"""
    w, h = im["w"], im["h"]
    rng = np.random.default_rng(_seed(name, index))
    y, x = np.mgrid[0:h, 0:w]
    u, v = (x + 0.5) / w * 2 - 1, (y + 0.5) / h * 2 - 1
    grid = np.asarray(im["faces"][face]["grid"], np.float32)
    lum = grid.mean(1)
    bright, mean = grid[lum.argmax()], grid.mean(0)
    if bright.max() > 8:
        bright = bright * min(3.0, 255 / bright.max())
    clumps = noise(w, h, 24, rng) * 0.6 + noise(w, h, 60, rng) * 0.4
    disc = np.exp(-(v / 0.2) ** 2) * np.exp(-(u / 0.85) ** 4) * (0.35 + 0.65 * clumps)
    bulge = np.exp(-(u / 0.22) ** 2 - (v / 0.42) ** 2)
    lanes = np.clip(1 - 1.6 * np.exp(-((v - 0.05 * np.sin(u * 7 + 1)) / 0.045) ** 2) * (0.3 + 0.7 * noise(w, h, 18, rng)), 0, 1)
    glow = np.clip(disc * lanes * 0.8 + bulge * 1.1, 0, 1)
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = np.clip(mean[None, None] * glow[..., None] * 1.2 + (bright - mean)[None, None] * (bulge ** 2)[..., None], 0, 255)
    n = w * h // 260
    ys, xs = rng.integers(0, h, n), rng.integers(0, w, n)
    out[ys, xs, :3] = np.maximum(out[ys, xs, :3], (rng.random((n, 1)) ** 4 * 200 + 30))
    out[..., 3] = 255 if im["faces"][face]["alpha"] == "opaque" else out[..., :3].max(-1)
    return out


DRAWERS = [
    (r"^sky/.*galaxy", galaxy),
    (r"^sky/.*(stars|star twinkle)|/stars\.bitmap", stars),
    (r"^sky/planets/", planet),
    (r"^effects/(?!zmaps)|lens|flare|contrail|glow|^sky/.*(galaxy|star mask|cloud mask)", effect),
]
