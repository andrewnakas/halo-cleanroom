"""Clean room: spec (kept facts) + CC0 library -> a clean tag tree.

    python -m games.halo.generate <spec dir> <cc0 dir> <clean tags dir> [--only bitmaps|sounds|fonts] [--match regex] [--add]

Reads only the spec (games/halo/extract_tags.py) and the CC0 library. Never
reads the dirty tree.
  bitmaps  CC0 material picked by the tag's name, tinted to the kept 4x4
           colour grid; alpha drawn by class (drawn.py holds the named ones)
  sounds   CC0 samples picked by sound class and name, fitted to the kept
           length and loudness outline; announcer lines spoken by Piper
  fonts    glyphs drawn again with Overpass (OFL) in the kept cells
"""
import hashlib
import json
import os
import re
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import tags
from .codecs import encode_xbox_adpcm

# ---------- bitmaps

MATERIALS = [  # first match wins: tag path pattern -> library class
    (r"grass|turf|field", "grass"), (r"snow", "snow"), (r"\bice\b", "ice"), (r"sand|beach|dune", "sand"),
    (r"cliff", "cliff"), (r"rock|boulder|stone|cave", "rock"), (r"dirt|mud|ground|soil|path", "ground"),
    (r"gravel|pebble", "gravel"), (r"moss", "moss"), (r"bark|trunk|tree|log", "bark"),
    (r"leaf|leaves|fern|plant|bush|pine|frond", "leaves"), (r"concrete|cement", "concrete"),
    (r"grate|grating|grill|vent", "grate"), (r"tile|floor", "tiles"), (r"rust", "rust"),
    (r"panel|plate|plating|hull|armor|strip", "metal_plates"), (r"cloth|fabric|flag|canvas", "fabric"),
    (r"rubber|tire|tyre|seat|leather", "leather"), (r"glass|foil|chrome|mirror", "foil"),
    (r"paint|stripe|decal", "painted_metal"),
    (r"metal|steel|weapons/|vehicles/|characters/|powerups/|scenery/|levels/b|levels/c|levels/a50", "metal"),
]
FALLBACK = {"cliff": "rock", "gravel": "ground", "moss": "grass", "grate": "metal_plates", "ice": "snow",
            "foil": "metal", "rust": "metal", "leather": "fabric", "tiles": "concrete", "bark": "rock",
            "leaves": "grass", "painted_metal": "metal", "sand": "ground", "snow": "concrete",
            "metal_plates": "metal", "fabric": "concrete", "grass": "ground", "ground": "rock", "concrete": "rock"}


class Library:
    def __init__(self, root):
        self.root = os.path.join(root, "textures")
        index = json.load(open(os.path.join(self.root, "index.json"))) if os.path.exists(
            os.path.join(self.root, "index.json")) else {}
        self.by_class = {}
        for aid in sorted(os.listdir(self.root)):
            color = os.path.join(self.root, aid, aid + "_1K-JPG_Color.jpg")
            if os.path.isfile(color):
                cls = index.get(aid, {}).get("class") or re.sub(r"\d+[A-Z]?$", "", aid).lower()
                self.by_class.setdefault(cls, []).append(color)
        self.cache, self.used = {}, {}

    def pick(self, cls, key):
        seen = set()
        while cls not in self.by_class and cls in FALLBACK and cls not in seen:
            seen.add(cls)
            cls = FALLBACK[cls]
        files = self.by_class.get(cls) or next(iter(self.by_class.values()))
        return files[int(hashlib.md5(key.encode()).hexdigest(), 16) % len(files)]

    def detail(self, path, w, h):
        """luminance of the material around 1.0, (h,w)"""
        k = (path, w, h)
        if k not in self.cache:
            if len(self.cache) > 64:
                self.cache.clear()
            lum = np.asarray(Image.open(path).convert("L").resize((max(w, 4), max(h, 4)), Image.LANCZOS), np.float32)
            lum = np.asarray(Image.fromarray(lum).resize((w, h), Image.BOX), np.float32)
            self.cache[k] = lum / max(float(lum.mean()), 1.0)
        return self.cache[k]


def material_class(rel):
    name = rel.lower()
    for pattern, cls in MATERIALS:
        if re.search(pattern, name):
            return cls
    return "concrete"


def smooth_grid(grid, w, h):
    """the 4x4 grid as a smooth (h,w,3) float image"""
    g = np.asarray(grid, np.uint8).reshape(4, 4, 3)
    return np.asarray(Image.fromarray(g).resize((max(w, 1), max(h, 1)), Image.BICUBIC), np.float32)


def radial(w, h, rect=None, power=1.5, hard=False):
    """alpha of a round blob in rect (left, top, right, bottom in 0..1)"""
    left, top, right, bottom = rect or (0, 0, 1, 1)
    y, x = np.mgrid[0:h, 0:w]
    cx, cy = (left + right) / 2 * w, (top + bottom) / 2 * h
    rx, ry = max((right - left) * w / 2, 0.5), max((bottom - top) * h / 2, 0.5)
    r = np.sqrt(((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2)
    return ((r < 0.85) * 255.0) if hard else np.clip(1 - r, 0, 1) ** power * 255.0


def kind_of(rel, tag, im):
    name = rel.lower()
    if name.startswith("rasterizer/"):
        return "function"
    if tag["usage"] == 4:
        return "lightmap"
    if im["type"] == "cube":
        return "cube"
    if tag["usage"] in (2, 5) or im["format"] == "p8" or "bump" in name:
        return "bump"
    if tag["usage"] == 3 or "detail" in name:
        return "detail"
    if name.startswith("ui/"):
        return "ui"
    if name.startswith(("effects/", "sky/")) or "lens" in name or "flare" in name or "glow" in name:
        return "effect"
    return "texture"


def make_image(lib, rel, tag, skeleton, index, im, face):
    """mip 0 of one image/face -> (h,w,4) float RGBA"""
    from . import drawn
    w, h = im["w"], im["h"]
    facts = im["faces"][face]
    kind = kind_of(rel, tag, im)
    base = smooth_grid(facts["grid"], w, h)
    alpha = np.full((h, w), 255.0, np.float32)
    special = drawn.draw(rel, tag, skeleton, index, im, face, base)
    if special is not None:
        return special
    kept = drawn.kept_alpha(rel, index, face, im)
    if kind == "lightmap" and drawn.SPEC:
        from . import bsp
        pages = bsp.lightmap_pages(drawn.SPEC, rel)      # our own lighting from the level's geometry
        if pages and index in pages:
            return np.concatenate([pages[index], alpha[..., None]], -1)
    if kind in ("function", "lightmap", "cube"):
        rgb = base
        if kept is not None:
            alpha = kept
        elif facts["alpha"] != "opaque":
            alpha = base.mean(-1)
    elif kind == "bump" and im["format"] == "p8":
        # a palettized bump map: surface normals from the relief of the CC0 material that
        # the neighbouring diffuse texture uses (the palette is the engine's table of normals)
        twin = re.sub(r"[ _-]?bump", "", rel)                # the diffuse texture's name
        src = lib.pick(material_class(twin), twin)
        d = lib.detail(src, w, h)
        gy, gx = np.gradient(d.astype(np.float32))
        n = np.stack([-gx * 2.2, -gy * 2.2, np.ones_like(gx)], -1)
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        return np.concatenate([n * 127.5 + 127.5, alpha[..., None]], -1)      # quantised per level in generate_bitmaps
    elif kind == "bump":
        rgb = np.broadcast_to(np.asarray(facts["grid"], np.float32).mean(0), (h, w, 3)).copy()
        if kept is not None:
            alpha = kept
        elif facts["alpha"] != "opaque":
            alpha[:] = 128
    else:
        cls = material_class(rel) if kind in ("texture", "detail") else "concrete"
        src = lib.pick(cls, rel)
        lib.used[rel] = os.path.basename(os.path.dirname(src))
        d = lib.detail(src, w, h)
        strength = {"texture": 0.8, "detail": 1.0, "ui": 0.15, "effect": 0.3}[kind]
        rgb = base * (1 + strength * (d[..., None] - 1))
        if kept is not None:
            alpha = kept
        elif facts["alpha"] != "opaque":
            sprites = [s for seq in skeleton.sequences for s in seq["sprites"] if s["bitmap"] == index]
            hard = facts["alpha"] == "binary"
            if sprites:
                alpha[:] = 0
                for s in sprites:
                    alpha = np.maximum(alpha, radial(w, h, s["rect"], hard=hard))
            elif kind in ("effect",) or im["format"] in ("a8", "ay8", "a8y8"):
                alpha = radial(w, h, hard=hard)
            elif kind == "texture" and hard and material_class(rel) != "leaves":
                pass  # punch-through class with no outline kept: leave solid
            elif kind == "texture" and hard:
                alpha = (d > 0.9) * 255.0
            else:
                alpha = np.clip(60 + 150 * d, 0, 255) if kind == "texture" else radial(w, h, power=0.6)
    return np.concatenate([np.clip(rgb, 0, 255), alpha[..., None]], -1)


_palette = None


def palette_indices(rgba):
    """Normals as colours -> the nearest entry of the engine's bump palette, as a grey image
    whose brightness is the index (how the p8 encoder stores it)."""
    global _palette
    from scipy.spatial import cKDTree
    if _palette is None:
        table = json.load(open(os.path.join(os.path.dirname(__file__), "vector_palette.json")))
        _palette = cKDTree(np.asarray(table, np.float32))
    index = _palette.query(np.asarray(rgba, np.float32)[..., :3].reshape(-1, 3))[1].astype(np.uint8)
    index = index.reshape(rgba.shape[:2])
    return np.stack([index, index, index, np.full_like(index, 255)], -1)


def generate_bitmaps(spec, lib, out, match=None):
    from . import drawn, functions
    drawn.SPEC = spec
    drawn.CC0 = os.path.dirname(lib.root)
    facts = json.load(open(os.path.join(spec, "bitmaps.json")))
    n = 0
    for rel, tag in sorted(facts.items()):
        if match and not re.search(match, rel):
            continue
        t = tags.BitmapTag(os.path.join(spec, "tags", rel))
        for index, (b, im) in enumerate(zip(t.bitmaps, tag["images"])):
            tops = [np.clip(make_image(lib, rel, tag, t, index, im, f), 0, 255).astype(np.uint8)
                    for f in range(b.faces)]

            volume = functions.VOLUMES.get(rel.lower()) if b.type == "3d" else None

            vectors = im["format"] == "p8" and kind_of(rel, tag, im) == "bump"

            def level(mip, face, w, h, z, tops=tops, volume=volume, depth=b.depth, vectors=vectors):
                if volume:
                    return volume(w, h, max(1, depth >> mip), z)
                top = tops[face]
                if (w, h) != (top.shape[1], top.shape[0]):
                    top = np.asarray(Image.fromarray(top).resize((w, h), Image.BOX))
                return palette_indices(top) if vectors else top
            b.write(level)
            n += 1
        t.save(os.path.join(out, rel))
    used_path = os.path.join(out, "..", "materials_used.json")
    used = json.load(open(used_path)) if match and os.path.exists(used_path) else {}
    used.update(lib.used)
    json.dump(used, open(used_path, "w"), indent=0)
    print(f"bitmaps: {n} images in {len(facts)} tags, {len(set(lib.used.values()))} CC0 materials used")


# ---------- sounds

SOUND_RULES = [  # (path pattern, pack/name prefixes); first match wins
    (r"footstep|/jump|land", ["footstep_concrete", "footstep0"]), (r"ricc|bullet|needle", ["impactMetal_light", "impactTin"]),
    (r"plasma|charge|overheat|shield|teleport|invis|energy", ["forceField", "phaserUp", "phaserDown", "zap", "laserSmall"]),
    (r"fire|shot|burst|rifle|pistol|sniper|shotgun", ["laserRetro", "laserLarge", "explosionCrunch"]),
    (r"rocket|explo|grenade|detonat|frag|bang|tank", ["explosionCrunch", "lowFrequency_explosion"]),
    (r"reload|ready|empty|clip|bolt|melee|pickup|ammo|latch|click", ["metalClick", "metalLatch", "impactMetal_medium"]),
    (r"engine|warthog|ghost|banshee|scorpion|vehicle|turret|_lp|loop|hum", ["spaceEngine", "engineCircular", "thrusterFire"]),
    (r"flesh|body|hit|melee|punch", ["impactPunch", "impactSoft"]), (r"glass", ["impactGlass"]),
    (r"wood|tree", ["impactWood"]), (r"water|splash", ["slime", "impactSoft"]),
    (r"ui/|cursor|forward|back|countdown|timer", ["click", "select", "tick", "confirmation", "tone"]),
    (r"wind|ambien|nature", ["spaceEngineLow", "lowRandom"]), (r"metal|impact|collision|crash", ["impactMetal", "impactPlate"]),
]


class Sounds:
    def __init__(self, root):
        import soundfile
        self.sf = soundfile
        self.files = {}
        for base, _, files in os.walk(os.path.join(root, "sounds")):
            for f in files:
                if f.endswith(".ogg") and "Preview" not in f:
                    self.files[f[:-4]] = os.path.join(base, f)
        self.names = sorted(self.files)
        self.cache, self.used, self.voice = {}, {}, None

    def load(self, name, rate):
        from scipy.signal import resample_poly
        if (name, rate) not in self.cache:
            x, sr = self.sf.read(self.files[name], dtype="float32", always_2d=True)
            x = x.mean(1)
            if sr != rate:
                x = resample_poly(x, rate, sr)
            self.cache[(name, rate)] = x
        return self.cache[(name, rate)]

    def pick(self, rel, salt):
        low = rel.lower()
        prefixes = next((p for pat, p in SOUND_RULES if re.search(pat, low)), ["impactGeneric", "impactSoft"])
        names = [n for n in self.names if n.startswith(tuple(prefixes))] or self.names
        return names[int(hashlib.md5((rel + salt).encode()).hexdigest(), 16) % len(names)]

    def speak(self, text, rate):
        from piper import PiperVoice
        from scipy.signal import resample_poly
        if self.voice is None:
            self.voice = PiperVoice.load("C:/Users/andre/n64work/piper_voices/en_US-ryan-high.onnx")
        x = np.concatenate([c.audio_float_array for c in self.voice.synthesize(text)]).astype(np.float32)
        loud = np.flatnonzero(np.abs(x) > 0.01)
        if len(loud):
            x = x[max(0, loud[0] - 300):loud[-1] + 300]
        return resample_poly(x, rate, self.voice.config.sample_rate)


def fit(x, n, loop):
    """x to exactly n samples: looped (engines, ambience) or squeezed/padded"""
    from scipy.signal import resample
    if len(x) == 0:
        return np.zeros(n, np.float32)
    if loop or len(x) < n // 3:
        reps = int(np.ceil(n / len(x)))
        return np.tile(x, reps)[:n]
    if len(x) > n:
        squeezed = resample(x, max(n, int(len(x) / 1.35)))
        x = squeezed[:n]
        fade = min(len(x), 400)
        x[-fade:] *= np.linspace(1, 0, fade)
        return x
    return np.pad(x, (0, n - len(x)))


def shape(x, outline, limit=None):
    """x follows the loudness outline (dBFS RMS per window); limit caps the gain (speech:
    its own pauses must stay pauses)"""
    n, points = len(x), len(outline)
    edges = (np.arange(points + 1) * n) // points
    rng = np.random.default_rng(len(x))
    x = x + rng.normal(0, 1e-3, n).astype(np.float32)   # never silent under a loud window
    gains = np.empty(points)
    for i in range(points):
        seg = x[edges[i]:max(edges[i + 1], edges[i] + 1)]
        rms = float(np.sqrt((seg ** 2).mean()))
        gains[i] = 10 ** (outline[i] / 20) / max(rms, 1e-5) if outline[i] > -60 else 0.0
    if limit:
        gains = np.clip(gains, 0.0, limit)
    centres = (edges[:-1] + edges[1:]) / 2
    g = np.interp(np.arange(n), centres, gains) if points > 1 else np.full(n, gains[0])
    # a noise floor of a few LSB: silence is then ours, not the codec's idle pattern
    return np.tanh(x * g * 1.2) / 1.2 + rng.normal(0, 4e-4, n).astype(np.float32)


def murmur(n, rate, seed):
    """a wordless voice-like placeholder for dialogue that has no text here:
    a buzz with drifting pitch through two vowel resonances"""
    from scipy.signal import lfilter
    rng = np.random.default_rng(seed)
    f0 = 95 + 60 * rng.random()
    drift = np.interp(np.arange(n), np.linspace(0, n, 9), 1 + 0.18 * (rng.random(9) - 0.5))
    phase = np.cumsum(2 * np.pi * f0 * drift / rate)
    buzz = np.sign(np.sin(phase)) * 0.5 + np.sin(phase) * 0.5 + rng.normal(0, 0.05, n)
    out = np.zeros(n)
    for centre in (500 + 300 * rng.random(), 1300 + 700 * rng.random()):
        r = 0.97
        w = 2 * np.pi * centre / rate
        out += lfilter([1 - r], [1, -2 * r * np.cos(w), r * r], buzz)
    return (out / max(np.abs(out).max(), 1e-6)).astype(np.float32)


def generate_sounds(spec, lib, out, match=None):
    from . import dialog
    facts = json.load(open(os.path.join(spec, "sounds.json")))
    spoken = 0
    text_path = os.path.join(spec, "dialog.json")
    spoken_text = json.load(open(text_path, encoding="utf-8")) if os.path.exists(text_path) else {}
    for rel, s in sorted(facts.items()):
        if match and not re.search(match, rel):
            continue
        t = tags.SoundTag(os.path.join(spec, "tags", rel))
        rate, low = s["rate"], rel.lower()
        loop = s["class"] in (23, 32, 33, 34, 39) or bool(re.search(r"_lp|loop|engine|hum|ambien", low))
        speech = low.startswith("sound/dialog/multiplayer")
        perms = s["perms"]
        heads = [i for i, p in enumerate(perms) if not any(q["next"] == i and q["range"] == p["range"]
                                                           for q in perms)]
        # chains: a long permutation is stored as linked chunks
        base = {}
        for p in perms:
            base.setdefault(p["range"], len(base))
        starts = {}
        for i, p in enumerate(perms):
            starts.setdefault(p["range"], i)
        done = set()
        for h in heads:
            chain, i = [], h
            while i not in done and i < len(perms):
                chain.append(i)
                done.add(i)
                nxt = perms[i]["next"]
                if nxt == 0xFFFF:
                    break
                i = starts[perms[i]["range"]] + nxt
            total = sum(perms[i]["samples"] for i in chain)
            said_line = False
            if speech:
                text = re.sub(r"[_\d]+$", "", os.path.basename(rel)[:-6]).replace("_", " ")
                src = lib.speak(text, rate)
                spoken += 1
                lib.used[rel] = "piper:en_US-ryan-high"
            elif "/dialog/" in low and str(h) in spoken_text.get(rel, {}).get("lines", {}):
                # a transcribed line (text is the kept fact) in a placeholder voice
                who = dialog.speaker(rel)
                line = spoken_text[rel]["lines"][str(h)]["text"]
                said = dialog.speak(who, line, rate, max(total, 1))
                src = dialog.place(said, max(total, 1), [v for i in chain for v in perms[i]["outline"]])
                spoken += 1
                said_line = True
                lib.used[rel] = "piper:" + dialog.CAST.get(who, dialog.CAST["marine"])[0]
            elif "/dialog/" in low:
                src = murmur(max(total, 1), rate, int(hashlib.md5((rel + perms[h]["name"]).encode()).hexdigest()[:8], 16))
                lib.used[rel] = "murmur (synthesised)"
            else:
                name = lib.pick(rel, perms[h]["name"])
                src = lib.load(name, rate)
                lib.used[rel] = name
            x = fit(src.copy(), total, loop)
            pos = 0
            for i in chain:
                n = perms[i]["samples"]
                seg = shape(x[pos:pos + n], perms[i]["outline"], 3.0 if said_line else None)
                pos += n
                pcm = np.clip(seg * 32767, -32768, 32767).astype(np.int16)
                pcm = np.repeat(pcm[:, None], s["channels"], 1)
                t.replace(t.permutations[i], encode_xbox_adpcm(pcm))
        t.save(os.path.join(out, rel))
    used_path = os.path.join(out, "..", "sounds_used.json")
    used = json.load(open(used_path)) if match and os.path.exists(used_path) else {}
    used.update(lib.used)                 # (a partial run adds to the record)
    json.dump(used, open(used_path, "w"), indent=0)
    print(f"sounds: {len(facts)} tags, {sum(len(s['perms']) for s in facts.values())} permutations, "
          f"{spoken} spoken lines, {len(set(lib.used.values()))} CC0 sources used")


# ---------- fonts

def generate_fonts(spec, font_file, out):
    n = 0
    for p in tags.find(os.path.join(spec, "tags"), "font"):
        t = tags.FontTag(p)
        size = max(6, int(round((t.ascending + t.descending) * 0.92)))
        font = ImageFont.truetype(font_file, size)
        for c in t.characters:
            if c["w"] <= 0 or c["h"] <= 0 or c["offset"] < 0 or c["char"] < 32:
                continue
            img = Image.new("L", (c["w"], c["h"]), 0)
            ImageDraw.Draw(img).text((c["ox"], c["oy"]), chr(c["char"]), font=font, fill=255, anchor="ls")
            base = t.pixels + c["offset"]
            t.data[base:base + c["w"] * c["h"]] = img.tobytes()
            n += 1
        t.save(os.path.join(out, os.path.relpath(p, os.path.join(spec, "tags"))))
    print(f"fonts: {n} glyphs drawn with {os.path.basename(font_file)}")


def main():
    spec, cc0, out = sys.argv[1:4]
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    match = sys.argv[sys.argv.index("--match") + 1] if "--match" in sys.argv else None
    if "--add" in sys.argv:
        # only the tags of the spec that the clean tree does not hold yet
        # (an interrupted run leaves its list in pending_add.json: those tags are done again)
        pending = os.path.join(out, "..", "pending_add.json")
        added = json.load(open(pending)) if os.path.exists(pending) else []
        for root, _, files in os.walk(os.path.join(spec, "tags")):
            for f in files:
                src = os.path.join(root, f)
                rel = os.path.relpath(src, os.path.join(spec, "tags")).replace(chr(92), "/")
                dest = os.path.join(out, rel)
                if not os.path.isfile(dest):
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copyfile(src, dest)
                    added.append(rel)
        print(f"added {len(added)} tags")
        if not added:
            return
        json.dump(added, open(pending, "w"))
        match = "^(" + "|".join(re.escape(r) for r in added if r.endswith((".bitmap", ".sound"))) + ")$"
    elif only is None:
        if os.path.isdir(out):
            shutil.rmtree(out)
        shutil.copytree(os.path.join(spec, "tags"), out)   # kept tags + skeletons, then every asset is filled
    if only in (None, "bitmaps"):
        generate_bitmaps(spec, Library(cc0), out, match)
    if only in (None, "sounds"):
        generate_sounds(spec, Sounds(cc0), out, match)
    if only in (None, "fonts"):
        generate_fonts(spec, os.path.join(cc0, "fonts", "Overpass-900.ttf"), out)
    if "--add" in sys.argv and only is None:
        os.remove(pending)


if __name__ == "__main__":
    main()
