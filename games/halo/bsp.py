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
            v = np.frombuffer(raw, "<f4", n * 14).reshape(n, 14)
            mat = Material()
            mat.lightmap = -1 if page == 0xFFFF else page
            mat.shader = m["shader"].replace(B, "/")
            mat.group = m.ref_class("shader")
            mat.pos = v[:, 0:3].astype(np.float32)
            mat.normal = v[:, 3:6].astype(np.float32)
            mat.uv = v[:, 12:14].astype(np.float32)
            mat.lm_uv = None
            if ln and len(raw) >= n * 56 + ln * 20:
                lv = np.frombuffer(raw, "<f4", ln * 5, n * 56).reshape(ln, 5)
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


def cell_cover(cover):
    h, w = cover.shape
    ys = (np.arange(5) * h) // 4
    xs = (np.arange(5) * w) // 4
    return np.array([[cover[ys[j]:ys[j + 1], xs[i]:xs[i + 1]].mean() for i in range(4)] for j in range(4)], np.float32)


def filler_colour(pages):
    """The colour of lightmap texels no surface uses, from grid cells our charts leave empty
    (pages: [(grid, cover)]); None when every cell is in use."""
    empty = [np.asarray(grid, np.float32).reshape(4, 4, 3)[cell_cover(cover) < 0.002] for grid, cover in pages]
    empty = np.concatenate(empty) if empty else np.zeros((0, 3))
    return np.median(empty, 0) if len(empty) else None


def tint(light, cover, grid, filler=None, level=None):
    """Our lighting carried on the kept 4x4 colour grid of the page -> (h,w,3) float 0..255.
    A cell's kept colour mixes the lit charts with the page's unused texels, so the charts'
    share is solved from our own coverage; inside a cell, brightness follows our lighting."""
    h, w = cover.shape
    g = np.asarray(grid, np.float32).reshape(4, 4, 3)
    if not cover.any():
        return np.asarray(Image.fromarray(g.astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32)
    if filler is not None:
        # (the charts carry a rim of spread texels: count it as lit)
        cov = cell_cover(ndimage.binary_dilation(cover, iterations=2))[..., None]
        page = np.clip((g.sum((0, 1)) - (1 - cov).sum((0, 1)) * filler) / max(float(cov.sum()), 1e-3), 0, 255)
        if cov.sum() < 1.5 and level is not None:      # a page that is nearly empty: the level's lit colour
            page = level
        solved = np.clip((g - (1 - cov) * filler) / np.maximum(cov, 1e-3), 0, 255)
        trust = np.clip((cov - 0.5) / 0.4, 0, 1)        # mostly-lit cells keep their own colour
        g = trust * solved + (1 - trust) * page
    luma = light @ np.array([0.3, 0.59, 0.11], np.float32)
    ys = (np.arange(5) * h) // 4
    xs = (np.arange(5) * w) // 4
    cell = np.zeros((4, 4), np.float32)
    whole = float(luma[cover].mean())
    for j in range(4):
        for i in range(4):
            c = cover[ys[j]:ys[j + 1], xs[i]:xs[i + 1]]
            cell[j, i] = luma[ys[j]:ys[j + 1], xs[i]:xs[i + 1]][c].mean() if c.mean() > 0.05 else whole
    # cells as smooth fields (bilinear between cell centres)
    base = np.stack([np.asarray(Image.fromarray(g[..., k]).resize((w, h), Image.BILINEAR), np.float32) for k in range(3)], -1)
    mean = np.asarray(Image.fromarray(cell).resize((w, h), Image.BILINEAR), np.float32)
    ratio = np.clip(luma / np.maximum(mean, 1e-3), 0.25, 2.5)
    hue = light / np.maximum(luma[..., None], 1e-3)
    hue = 0.8 + 0.2 * np.clip(hue, 0.5, 1.6)           # a little of the light's own colour
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
        for key in [k for k in _cache if k not in ("index", "facts", "filler")]:
            del _cache[key]              # one level's pages at a time
        grids = {i: facts["images"][i]["faces"][0]["grid"] for i in baked}
        filler = filler_colour([(grids[i], cover) for i, (light, cover) in baked.items()])
        level = None
        if filler is not None:
            covs = {i: cell_cover(ndimage.binary_dilation(cover, iterations=2))[..., None] for i, (_, cover) in baked.items()}
            total = sum(float(c.sum()) for c in covs.values())
            lit = sum(np.asarray(grids[i], np.float32).reshape(4, 4, 3).sum((0, 1)) - (1 - covs[i]).sum((0, 1)) * filler
                      for i in baked)
            level = np.clip(lit / max(total, 1e-3), 0, 255)
        pages = {i: tint(light, cover, grids[i], filler, level) for i, (light, cover) in baked.items()}
        _cache["filler"] = filler
        _cache[bitmap_rel] = pages
    return _cache[bitmap_rel]


# ---------- pictures of a level (menu thumbnails): rendered from its own geometry

def material_colours(spec, mats):
    """Mean kept colour of each material's base map (shader -> bitmap -> 4x4 grid)."""
    facts = _cache.get("facts") or json.load(open(os.path.join(spec, "bitmaps.json")))
    _cache["facts"] = facts
    tags = os.path.join(spec, "tags")
    ext = {"senv": "shader_environment", "soso": "shader_model", "sotr": "shader_transparent_generic",
           "schi": "shader_transparent_chicago", "scex": "shader_transparent_chicago_extended",
           "swat": "shader_transparent_water", "sgla": "shader_transparent_glass", "smet": "shader_transparent_meter",
           "spla": "shader_transparent_plasma"}
    seen, out = {}, []
    for m in mats:
        key = (m.shader, m.group)
        if key not in seen:
            col = np.array([128.0, 128.0, 128.0])
            path = os.path.join(tags, m.shader + "." + ext.get(m.group, "shader_environment"))
            try:
                root = hek.Tag(path).root
                for field in ("base map", "map", "diffuse map"):
                    if field in root and root[field]:
                        f = facts.get(root[field].replace(B, "/") + ".bitmap")
                        if f:
                            col = np.asarray(f["images"][0]["faces"][0]["grid"], np.float64).mean(0)
                            break
            except (OSError, KeyError, AssertionError):
                pass
            seen[key] = col
        out.append(seen[key])
    return out


def overview(spec, bsp_rel, w, h, yaw=0.6, pitch=0.85):
    """A lit three-quarter view from above (back faces culled: ceilings open up) -> (h,w,3) 0..255."""
    mats, _ = load(os.path.join(spec, "tags", bsp_rel))
    mats = [m for m in mats if m.group in ("senv", "soso") and len(m.tris)]
    if not mats:
        return np.zeros((h, w, 3), np.float32)
    lights, amb = sky_lights(spec, bsp_rel)
    suns = [(d / np.linalg.norm(d), c) for d, c in lights if d[2] > 0.05 and c.max() > 0.05][:1]
    shadow = ShadowMap(mats, suns[0][0], 1024) if suns else None
    amb = amb if amb.max() > 0.01 else np.array([0.45, 0.45, 0.5])
    colours = material_colours(spec, mats)
    # camera basis: looking down along -view
    view = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
    right = np.cross([0, 0, 1.0], view)
    right /= np.linalg.norm(right)
    up = np.cross(view, right)
    allp = np.concatenate([m.pos for m in mats])
    lo_hi = np.percentile(np.stack([allp @ right, allp @ up], 1), [1, 99], axis=0)
    centre, span = lo_hi.mean(0), (lo_hi[1] - lo_hi[0]).max() * 1.08
    ss = 2
    W, H = w * ss, h * ss
    scale = min(W, H) / max(span, 1e-3)
    depth = np.full((H, W), -1e9, np.float32)
    top = np.linspace(22, 6, H)[:, None, None] * np.array([1.0, 1.1, 1.4])[None, None]
    img = np.repeat(top, W, 1).astype(np.float32)
    for m, col in zip(mats, colours):
        x = (m.pos @ right - centre[0]) * scale + W / 2
        y = H / 2 - (m.pos @ up - centre[1]) * scale
        z = m.pos @ view
        n = m.normal / np.maximum(np.linalg.norm(m.normal, axis=1, keepdims=True), 1e-6)
        if suns:
            d, c = suns[0]
            lit = amb[None] * (0.6 + 0.4 * n[:, 2:3]) + c[None] * (np.clip(n @ d, 0, 1) * shadow.visible(m.pos, n))[:, None]
        else:
            lit = np.repeat(0.45 + 0.4 * np.clip(n[:, 2:3], 0, 1) + 0.15 * np.abs(n[:, 0:1]), 3, 1)
        shade = np.clip(lit, 0, 1.6) * col[None] * 1.15
        q = np.stack([x, y], 1)
        for tri in m.tris:
            a_, b_, c_ = q[tri]
            if (b_[0] - a_[0]) * (c_[1] - a_[1]) - (b_[1] - a_[1]) * (c_[0] - a_[0]) > 0:
                continue                                    # faces away from the camera
            hit = _raster(q[tri], W, H)
            if hit is None:
                continue
            ys, xs, bc = hit
            zz = (bc @ z[tri]).astype(np.float32)
            near = zz > depth[ys, xs]
            ys, xs = ys[near], xs[near]
            depth[ys, xs] = zz[near]
            img[ys, xs] = bc[near] @ shade[tri]
    img = np.clip(img, 0, 255).reshape(h, ss, w, ss, 3).mean((1, 3))
    return img


def level_bsp(spec, level):
    """The first structure BSP of a map name (bloodgulch, a10, ...) as a tag path, or None."""
    tags = os.path.join(spec, "tags")
    for folder in (f"levels/{level}", f"levels/test/{level}"):
        p = os.path.join(tags, folder, level + ".scenario")
        if os.path.exists(p):
            sc = hek.Tag(p).root
            for b in sc["structure bsps"]:
                rel = b["structure bsp"].replace(B, "/") + ".scenario_structure_bsp"
                if os.path.exists(os.path.join(tags, rel)):
                    return rel
    return None


def main():
    spec, bsp_rel, out = sys.argv[1:4]
    if "--view" in sys.argv:
        Image.fromarray(overview(spec, bsp_rel, 512, 512).astype(np.uint8)).save(out)
        return
    mats, info = load(os.path.join(spec, "tags", bsp_rel))
    pages = lightmap_pages(spec, info["lightmaps"] + ".bitmap")
    lights, amb = sky_lights(spec, bsp_rel)
    print(f"{bsp_rel}: {len(mats)} materials, {sum(len(m.tris) for m in mats)} triangles, "
          f"{len(pages or {})} lightmap pages, {len(lights)} sky lights, ambient {np.round(amb, 2)}")
    print("unused-texel colour:", None if _cache.get("filler") is None else np.round(_cache["filler"]))
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
