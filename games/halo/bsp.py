"""Level geometry from kept tags (scenario_structure_bsp) and our own lightmaps.

    python -m games.halo.bsp <spec> <bsp tag rel path> <out.png>      contact sheet of the baked pages

Nothing here reads retail pixels. The kept facts are the level's triangles, their
lightmap coordinates, the sky's light directions/colours (numbers in the sky tag) and
the 4x4 colour grid of each lightmap page. The lighting itself is computed here:
sun visibility through a shadow map of the level, sky light by the surface normal.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

from . import hek

B = chr(92)


class Material:
    __slots__ = ("lightmap", "shader", "group", "pos", "normal", "uv", "lm_uv", "tris")


def load(path):
    """-> (materials, sky-independent info dict). Vertices are world units."""
    t = hek.Tag(path)
    r = t.root
    surfaces = np.concatenate([hek.array(r["surfaces"], n) for n in r["surfaces"].layout.fields], 1)
    out = []
    for lm in r["lightmaps"]:
        page = lm["bitmap"]
        for m in lm["materials"]:
            n, ln = m["rendered vertices count"], m["lightmap vertices count"]
            raw = bytes(m["uncompressed vertices"])
            if not n or len(raw) < n * 56:
                continue
            v = np.frombuffer(raw, ">f4", n * 14).reshape(n, 14)
            mat = Material()
            mat.lightmap = -1 if page == 0xFFFF else page
            mat.shader = m["shader"].replace(B, "/")
            mat.group = m.ref_class("shader")
            mat.pos = v[:, 0:3].astype(np.float32)
            mat.normal = v[:, 3:6].astype(np.float32)
            mat.uv = v[:, 12:14].astype(np.float32)
            mat.lm_uv = None
            if ln and len(raw) >= n * 56 + ln * 20:
                lv = np.frombuffer(raw, ">f4", ln * 5, n * 56).reshape(ln, 5)
                mat.lm_uv = lv[:, 3:5].astype(np.float32)
            first, count = m["surfaces"], m["surface count"]
            mat.tris = surfaces[first:first + count].astype(np.int64)
            out.append(mat)
    return out, {"lightmaps": r["lightmaps bitmap"].replace(B, "/")}


def sky_lights(spec, bsp_rel):
    """Sky lights for the level a BSP belongs to: [(direction to the light, colour*power)], ambient rgb."""
    tags = os.path.join(spec, "tags")
    want = os.path.splitext(bsp_rel)[0].replace("/", B).lower()
    folder = os.path.dirname(os.path.join(tags, bsp_rel))
    for _ in range(3):
        for name in os.listdir(folder):
            if not name.endswith(".scenario"):
                continue
            sc = hek.Tag(os.path.join(folder, name)).root
            if want not in [b["structure bsp"].lower() for b in sc["structure bsps"]]:
                continue
            for s in sc["skies"]:
                p = os.path.join(tags, s["sky"].replace(B, "/") + ".sky")
                if not s["sky"] or not os.path.exists(p):
                    continue
                sky = hek.Tag(p).root
                lights = []
                for li in sky["lights"]:
                    yaw, pitch = li["direction"]
                    d = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
                    lights.append((d, np.array(li["color"]) * li["power"]))
                amb = np.array(sky["outdoor ambient radiosity color"]) * sky["outdoor ambient radiosity power"]
                return lights, amb
            return [], np.zeros(3)
        folder = os.path.dirname(folder)
    return [], np.zeros(3)


def _raster(p, w, h, margin=0.0):
    """Texels covered by triangle p (3,2 in texel units) -> (ys, xs, barycentric (n,3)) or None."""
    x0 = max(int(math.floor(p[:, 0].min() - margin)), 0)
    x1 = min(int(math.ceil(p[:, 0].max() + margin)), w)
    y0 = max(int(math.floor(p[:, 1].min() - margin)), 0)
    y1 = min(int(math.ceil(p[:, 1].max() + margin)), h)
    if x1 <= x0 or y1 <= y0:
        return None
    den = (p[1, 1] - p[2, 1]) * (p[0, 0] - p[2, 0]) + (p[2, 0] - p[1, 0]) * (p[0, 1] - p[2, 1])
    if abs(den) < 1e-9:
        return None
    ys, xs = np.mgrid[y0:y1, x0:x1]
    px, py = xs + 0.5, ys + 0.5
    a = ((p[1, 1] - p[2, 1]) * (px - p[2, 0]) + (p[2, 0] - p[1, 0]) * (py - p[2, 1])) / den
    b = ((p[2, 1] - p[0, 1]) * (px - p[2, 0]) + (p[0, 0] - p[2, 0]) * (py - p[2, 1])) / den
    c = 1 - a - b
    eps = -margin / max(math.sqrt(abs(den)), 1e-3) - 1e-4
    keep = (a >= eps) & (b >= eps) & (c >= eps)
    if not keep.any():
        return None
    return ys[keep], xs[keep], np.stack([a[keep], b[keep], c[keep]], 1)


class ShadowMap:
    """Orthographic depth of the level seen from a light (direction d points to the light)."""

    def __init__(self, mats, d, size=1536):
        d = d / np.linalg.norm(d)
        up = np.array([0, 0, 1.0]) if abs(d[2]) < 0.95 else np.array([1.0, 0, 0])
        self.u = np.cross(up, d)
        self.u /= np.linalg.norm(self.u)
        self.v = np.cross(d, self.u)
        self.d = d
        allp = np.concatenate([m.pos for m in mats])
        su, sv = allp @ self.u, allp @ self.v
        self.lo = np.array([su.min(), sv.min()])
        span = max(su.max() - su.min(), sv.max() - sv.min(), 1e-3)
        self.scale = (size - 1) / span
        self.size = size
        self.texel = span / size
        depth = np.full((size, size), -1e9, np.float32)      # the nearest surface to the light has the largest depth
        for m in mats:
            if m.group in ("sotr", "schi", "scex", "sgla", "swat", "smet", "spla"):
                continue                 # see-through or additive surfaces cast no shadow
            q = np.stack([(m.pos @ self.u - self.lo[0]) * self.scale, (m.pos @ self.v - self.lo[1]) * self.scale], 1)
            z = m.pos @ d
            for tri in m.tris:
                hit = _raster(q[tri], size, size, 0.5)
                if hit is None:
                    continue
                ys, xs, bc = hit
                np.maximum.at(depth, (ys, xs), (bc @ z[tri]).astype(np.float32))
        self.depth = depth

    def visible(self, pos, normal):
        """0..1 visibility of world points (n,3) (3x3 percentage-closer)."""
        bias = self.texel * 2.5
        p = pos + normal * bias
        x = (p @ self.u - self.lo[0]) * self.scale
        y = (p @ self.v - self.lo[1]) * self.scale
        z = p @ self.d
        out = np.zeros(len(pos), np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                xi = np.clip((x + dx).astype(np.int64), 0, self.size - 1)
                yi = np.clip((y + dy).astype(np.int64), 0, self.size - 1)
                out += z >= self.depth[yi, xi] - bias
        return out / 9.0


def bake(mats, lights, ambient, sizes):
    """sizes {page: (w, h)} -> {page: (light (h,w,3) float, covered (h,w) bool)}"""
    suns = [(d, c) for d, c in lights if d[2] > 0.05 and c.max() > 0.05]
    lit = [m for m in mats if m.lightmap >= 0 and m.lm_uv is not None]
    maps = [(ShadowMap(mats, d), d / np.linalg.norm(d), c) for d, c in suns] if lit else []
    fills = [(d / np.linalg.norm(d), c) for d, c in lights if not (d[2] > 0.05 and c.max() > 0.05)]
    amb = ambient if ambient.max() > 0.01 else np.array([0.35, 0.35, 0.38])
    out = {}
    for page, (w, h) in sizes.items():
        pos = np.zeros((h, w, 3), np.float32)
        nrm = np.zeros((h, w, 3), np.float32)
        cover = np.zeros((h, w), bool)
        for m in lit:
            if m.lightmap != page:
                continue
            q = m.lm_uv * np.array([w, h], np.float32)
            for tri in m.tris:
                hit = _raster(q[tri], w, h, 0.75)
                if hit is None:
                    continue
                ys, xs, bc = hit
                bc = np.clip(bc, 0, 1)
                bc /= bc.sum(1, keepdims=True)
                pos[ys, xs] = bc @ m.pos[tri]
                nrm[ys, xs] = bc @ m.normal[tri]
                cover[ys, xs] = True
        light = np.zeros((h, w, 3), np.float32)
        if cover.any():
            P, N = pos[cover], nrm[cover]
            N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-6)
            if maps:
                L = amb[None] * (0.55 + 0.45 * N[:, 2:3])
                for sm, d, c in maps:
                    ndl = np.clip(N @ d, 0, 1)
                    L = L + c[None] * (ndl * sm.visible(P, N))[:, None]
                for d, c in fills:
                    L = L + 0.5 * c[None] * np.clip(N @ d, 0, 1)[:, None]
            else:       # no sun here (interiors): light from above and a little from every side
                L = np.repeat((0.5 + 0.35 * np.clip(N[:, 2:3], -0.4, 1) + 0.15 * np.abs(N[:, 0:1])), 3, 1)
            light[cover] = L
            # soften within the charts, then spread the charts' edges into the unused texels
            wgt = ndimage.gaussian_filter(cover.astype(np.float32), 0.8)
            for k in range(3):
                light[..., k] = ndimage.gaussian_filter(light[..., k], 0.8) / np.maximum(wgt, 1e-4)
            idx = ndimage.distance_transform_edt(~cover, return_distances=False, return_indices=True)
            light = light[idx[0], idx[1]]
        out[page] = (light, cover)
    return out


def tint(light, cover, grid):
    """Our lighting carried on the kept 4x4 colour grid of the page -> (h,w,3) float 0..255.
    Each grid cell keeps its kept mean colour; inside it, brightness follows our lighting."""
    h, w = cover.shape
    g = np.asarray(grid, np.float32).reshape(4, 4, 3)
    base = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32)
    if not cover.any():
        return base
    luma = light @ np.array([0.3, 0.59, 0.11], np.float32)
    ys = (np.arange(5) * h) // 4
    xs = (np.arange(5) * w) // 4
    cell = np.zeros((4, 4), np.float32)
    whole = float(luma[cover].mean())
    for j in range(4):
        for i in range(4):
            c = cover[ys[j]:ys[j + 1], xs[i]:xs[i + 1]]
            cell[j, i] = luma[ys[j]:ys[j + 1], xs[i]:xs[i + 1]][c].mean() if c.any() else whole
    mean = np.asarray(Image.fromarray(cell).resize((w, h), Image.BICUBIC), np.float32)
    ratio = np.clip(luma / np.maximum(mean, 1e-3), 0.3, 2.5)
    hue = light / np.maximum(luma[..., None], 1e-3)
    hue = 0.75 + 0.25 * np.clip(hue, 0.5, 1.6)           # a little of the light's own colour
    return np.clip(base * ratio[..., None] * hue, 0, 255)


_cache = {}


def lightmap_pages(spec, bitmap_rel):
    """Baked pages for a lightmap bitmap tag: {image index: (h,w,3) 0..255}, or None when no BSP uses it."""
    if "index" not in _cache:
        index = {}
        tags = os.path.join(spec, "tags")
        for folder, _, files in os.walk(tags):
            for name in files:
                if name.endswith(".scenario_structure_bsp"):
                    p = os.path.join(folder, name)
                    head = open(p, "rb").read(64 + 16)
                    n = int.from_bytes(head[64 + 8:64 + 12], "big")
                    # the lightmaps reference is the first field: its path follows the root struct
                    lay = hek.layout(hek.ROOTS()["scenario_structure_bsp"])
                    data = open(p, "rb").read(64 + lay.size + n)
                    ref = data[64 + lay.size:64 + lay.size + n].decode("latin1").replace(B, "/").lower()
                    index[ref + ".bitmap"] = os.path.relpath(p, tags).replace(os.sep, "/")
        _cache["index"] = index
        _cache["facts"] = json.load(open(os.path.join(spec, "bitmaps.json")))
    bsp_rel = _cache["index"].get(bitmap_rel.lower())
    if not bsp_rel:
        return None
    if bitmap_rel not in _cache:
        facts = _cache["facts"][bitmap_rel]
        mats, _ = load(os.path.join(spec, "tags", bsp_rel))
        lights, amb = sky_lights(spec, bsp_rel)
        sizes = {i: (im["w"], im["h"]) for i, im in enumerate(facts["images"])}
        baked = bake(mats, lights, amb, sizes)
        for key in [k for k in _cache if k not in ("index", "facts")]:
            del _cache[key]              # one level's pages at a time
        pages = {i: tint(light, cover, facts["images"][i]["faces"][0]["grid"]) for i, (light, cover) in baked.items()}
        _cache[bitmap_rel] = pages
    return _cache[bitmap_rel]


def main():
    spec, bsp_rel, out = sys.argv[1:4]
    mats, info = load(os.path.join(spec, "tags", bsp_rel))
    pages = lightmap_pages(spec, info["lightmaps"] + ".bitmap")
    lights, amb = sky_lights(spec, bsp_rel)
    print(f"{bsp_rel}: {len(mats)} materials, {sum(len(m.tris) for m in mats)} triangles, "
          f"{len(pages or {})} lightmap pages, {len(lights)} sky lights, ambient {np.round(amb, 2)}")
    if pages:
        cell = 192
        keys = sorted(pages)[:24]
        cols = 6
        sheet = Image.new("RGB", (cols * cell, ((len(keys) + cols - 1) // cols) * cell), (30, 0, 30))
        for k, i in enumerate(keys):
            im = Image.fromarray(pages[i].astype(np.uint8)).resize((cell, cell), Image.NEAREST)
            sheet.paste(im, ((k % cols) * cell, (k // cols) * cell))
        sheet.save(out)


if __name__ == "__main__":
    main()
