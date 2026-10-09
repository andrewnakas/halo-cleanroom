"""Clean room: bitmaps that are drawn by name instead of tinted from a
material (menus, HUD, engine function textures). Each drawer gets the kept
facts only (name, size, colour grid, alpha class, sprite rectangles) and
returns (h,w,4) float RGBA, or None to fall through to generate.py.

Everything here is our own drawing: shapes from code, text set in free fonts
(Overpass, OpenCE/Newtown). Briefs were written after one look at a dirty
contact sheet (what each picture is), never from its pixels.
"""
import json
import os
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CC0 = "D:/n64work/halo/cc0"          # set by generate.py
SS = 4                               # supersampling
BLUE = (70, 150, 255)
NAVY = (6, 16, 40)

_fonts, _titles = {}, None


def font(size, name="Overpass-900.ttf"):
    k = (name, int(size))
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(os.path.join(CC0, "fonts", name), int(size))
    return _fonts[k]


class Canvas:
    """RGBA canvas in texels, drawn supersampled"""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def s(self, *v):
        return [x * SS for x in v]

    def rrect(self, box, radius, fill=None, outline=None, width=1):
        self.d.rounded_rectangle(self.s(*box), radius * SS, fill=fill, outline=outline, width=max(1, int(width * SS)))

    def poly(self, pts, fill=None, outline=None, width=1):
        p = [(x * SS, y * SS) for x, y in pts]
        if fill:
            self.d.polygon(p, fill=fill)
        if outline:
            self.d.line(p + [p[0]], fill=outline, width=max(1, int(width * SS)), joint="curve")

    def line(self, pts, fill, width=1):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=fill, width=max(1, int(width * SS)), joint="curve")

    def ellipse(self, box, fill=None, outline=None, width=1):
        self.d.ellipse(self.s(*box), fill=fill, outline=outline, width=max(1, int(width * SS)))

    def text(self, xy, s, size, fill, anchor="mm", name="Overpass-900.ttf"):
        self.d.text((xy[0] * SS, xy[1] * SS), s, font=font(size * SS, name), fill=fill, anchor=anchor)

    def glow(self, radius, color):
        """a soft halo of the drawing, under it"""
        a = self.img.getchannel("A").filter(ImageFilter.GaussianBlur(radius * SS))
        halo = Image.new("RGBA", self.img.size, color + (0,))
        halo.putalpha(a.point(lambda v: min(255, int(v * 1.6))))
        halo.alpha_composite(self.img)
        self.img = halo
        self.d = ImageDraw.Draw(self.img)

    def out(self):
        return np.asarray(self.img.resize((self.w, self.h), Image.BOX), np.float32)


def tone(im, face=0):
    """(bright colour, mean colour) of the kept grid"""
    g = np.asarray(im["faces"][face]["grid"], np.float32)
    return tuple(int(v) for v in g[g.sum(1).argmax()]), tuple(int(v) for v in g.mean(0))


def lighter(c, k=1.5):
    return tuple(int(min(255, v * k + 20)) for v in c)


# ---------- icons (unit box x,y,size)

def icon(c, kind, x, y, s, col, lw=None):
    lw = lw or max(1.0, s / 18)
    P = lambda pts: [(x + px * s, y + py * s) for px, py in pts]
    if kind == "flag":
        c.line(P([(0.3, 0.92), (0.3, 0.1)]), col, lw * 1.5)
        c.poly(P([(0.3, 0.12), (0.85, 0.2), (0.7, 0.36), (0.9, 0.52), (0.3, 0.5)]), fill=col)
    elif kind == "crown":   # king of the hill
        c.poly(P([(0.08, 0.92), (0.3, 0.6), (0.7, 0.6), (0.92, 0.92)]), fill=col)
        c.poly(P([(0.3, 0.5), (0.26, 0.2), (0.4, 0.36), (0.5, 0.14), (0.6, 0.36), (0.74, 0.2), (0.7, 0.5)]), fill=col)
    elif kind == "person":
        c.ellipse((x + 0.41 * s, y + 0.08 * s, x + 0.59 * s, y + 0.26 * s), fill=col)
        c.poly(P([(0.32, 0.3), (0.68, 0.3), (0.74, 0.58), (0.64, 0.58), (0.62, 0.42), (0.6, 0.94), (0.52, 0.94),
                  (0.5, 0.64), (0.48, 0.94), (0.4, 0.94), (0.38, 0.42), (0.36, 0.58), (0.26, 0.58)]), fill=col)
    elif kind == "skull":
        c.ellipse((x + 0.18 * s, y + 0.12 * s, x + 0.82 * s, y + 0.72 * s), fill=col)
        c.rrect((x + 0.34 * s, y + 0.6 * s, x + 0.66 * s, y + 0.88 * s), 0.04 * s, fill=col)
        for ex in (0.36, 0.64):
            c.ellipse((x + (ex - 0.1) * s, y + 0.36 * s, x + (ex + 0.1) * s, y + 0.56 * s), fill=(0, 0, 0, 0))
        c.poly(P([(0.5, 0.56), (0.45, 0.68), (0.55, 0.68)]), fill=(0, 0, 0, 0))
    elif kind == "bolt":
        c.poly(P([(0.58, 0.06), (0.22, 0.54), (0.46, 0.54), (0.38, 0.94), (0.78, 0.42), (0.54, 0.42)]), fill=col)
    elif kind == "question":
        c.text((x + 0.5 * s, y + 0.52 * s), "?", 0.8 * s, col)
    elif kind == "lock":
        c.rrect((x + 0.22 * s, y + 0.46 * s, x + 0.78 * s, y + 0.9 * s), 0.06 * s, fill=col)
        c.d.arc(c.s(x + 0.3 * s, y + 0.12 * s, x + 0.7 * s, y + 0.74 * s), 180, 360, fill=col, width=int(lw * 2 * SS))
    elif kind == "pad":      # game controller
        c.rrect((x + 0.1 * s, y + 0.3 * s, x + 0.9 * s, y + 0.66 * s), 0.16 * s, outline=col, width=lw)
        c.poly(P([(0.14, 0.6), (0.06, 0.86), (0.2, 0.9), (0.34, 0.66)]), outline=col, width=lw)
        c.poly(P([(0.86, 0.6), (0.94, 0.86), (0.8, 0.9), (0.66, 0.66)]), outline=col, width=lw)
        c.ellipse((x + 0.24 * s, y + 0.4 * s, x + 0.36 * s, y + 0.52 * s), outline=col, width=lw)
        c.ellipse((x + 0.64 * s, y + 0.4 * s, x + 0.76 * s, y + 0.52 * s), outline=col, width=lw)
    elif kind == "console":
        c.rrect((x + 0.08 * s, y + 0.34 * s, x + 0.92 * s, y + 0.72 * s), 0.05 * s, outline=col, width=lw)
        c.line(P([(0.08, 0.52), (0.92, 0.52)]), col, lw)
        c.ellipse((x + 0.42 * s, y + 0.4 * s, x + 0.58 * s, y + 0.5 * s), outline=col, width=lw)
    elif kind == "gear":
        for k in range(8):
            a = k * np.pi / 4
            c.line([(x + (0.5 + 0.26 * np.cos(a)) * s, y + (0.5 + 0.26 * np.sin(a)) * s),
                    (x + (0.5 + 0.4 * np.cos(a)) * s, y + (0.5 + 0.4 * np.sin(a)) * s)], col, lw * 2.4)
        c.ellipse((x + 0.24 * s, y + 0.24 * s, x + 0.76 * s, y + 0.76 * s), outline=col, width=lw * 2.2)
    elif kind == "people":
        for dx in (-0.24, 0, 0.24):
            icon(c, "person", x + dx * s + 0.15 * s, y + 0.1 * s, 0.7 * s, col)
    elif kind == "screen":
        c.rrect((x + 0.14 * s, y + 0.16 * s, x + 0.86 * s, y + 0.66 * s), 0.04 * s, outline=col, width=lw)
        c.line(P([(0.5, 0.66), (0.5, 0.8)]), col, lw)
        c.line(P([(0.3, 0.82), (0.7, 0.82)]), col, lw)
    elif kind == "shield":
        c.poly(P([(0.5, 0.04), (0.84, 0.2), (0.88, 0.56), (0.5, 0.96), (0.12, 0.56), (0.16, 0.2)]),
               fill=col, outline=lighter(col), width=lw)
    elif kind == "blade":
        c.poly(P([(0.5, 0.0), (0.56, 0.12), (0.54, 0.86), (0.6, 0.9), (0.4, 0.9), (0.46, 0.86), (0.44, 0.12)]), fill=col)


def panel(name, tag, sk, index, im, face, base):
    """frames, fields and bars: a translucent navy plate in a blue line"""
    w, h = im["w"], im["h"]
    bright, mean = tone(im)
    c = Canvas(w, h)
    m = max(1.0, min(w, h) / 24)
    r = min(w, h) * (0.45 if re.search(r"kbd_|option_bkds|list_item|menu_bkds", name) else 0.08)
    solid = im["faces"][face]["alpha"] != "gradient" or re.search(r"list_field|pregame_list|kbd_", name)
    fill = None if re.search(r"kbd_(hilite|select|engaged)|4way_profile_border", name) else mean + (255 if solid and "kbd" not in name else 190,)
    line = bright if sum(bright) > 200 else BLUE
    if w <= 16 or h <= 16:      # strips that are stretched: plate with lines on the long edges
        c.d.rectangle(c.s(0, 0, w, h), fill=mean + (200,))
        if "left" in name:
            c.line([(m, 0), (m, h)], line, m)
        elif "right" in name:
            c.line([(w - m, 0), (w - m, h)], line, m)
        return c.out()
    c.rrect((m, m, w - m, h - m), r, fill=fill, outline=line + (255,), width=max(1.0, min(w, h) / 40))
    return c.out()


MAP_NAMES = {"beaver_creek": "Beaver\nCreek", "bloodgulch": "Blood\nGulch", "boardingaction": "Boarding\nAction",
             "bonus_level": "Bonus\nLevel", "carousel": "Carousel", "chillout": "Chill\nOut", "hangemhigh": "Hang 'em\nHigh",
             "prisoner": "Prisoner", "ratrace": "Rat Race", "ruinedpain": "Ruined\nPain", "sidewinder": "Side\nWinder",
             "wizard": "Wizard"}


def map_card(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    c.d.rectangle(c.s(0, 0, w, h), fill=(0, 0, 0, 255))
    label = MAP_NAMES.get(os.path.basename(name)[:-7], os.path.basename(name)[:-7].title())
    c.d.multiline_text((w * SS / 2, h * SS / 2), label, font=font(w * 0.17 * SS), fill=(255, 255, 255, 255),
                       anchor="mm", align="center", spacing=w * 0.03 * SS)
    return c.out()


def button(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    letter = os.path.basename(name)[0].upper()
    col = {"A": (40, 170, 60), "B": (200, 40, 40), "X": (40, 80, 200), "Y": (220, 170, 30)}[letter]
    c = Canvas(w, h)
    r = w * (0.2 if "_sm" in name else 0.27)
    c.ellipse((w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r), fill=col + (255,), outline=(235, 235, 235, 255), width=max(1, w / 28))
    c.text((w / 2, h / 2), letter, r * 1.3, (255, 255, 255, 255))
    return c.out()


def arrow(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    bright, _ = tone(im)
    col = (lighter(bright) if index else BLUE) + (255,)
    c = Canvas(w, h)
    s = min(w, h * 0.5) * 0.7
    cx, cy = w / 2, h / 2
    d = -1 if "left" in name else 1
    c.poly([(cx - d * s / 2, cy - s * (h / w if h > w else 1) / 2), (cx + d * s / 2, cy),
            (cx - d * s / 2, cy + s * (h / w if h > w else 1) / 2)], fill=col)
    return c.out()


def controller_badge(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    if index < 3:
        icon(c, "pad", w * 0.1, h * 0.1, w * 0.8, BLUE + (255,))
        if index != 1:
            c.text((w / 2, h * 0.47), "?", w * 0.3, BLUE + (255,))
        return c.out()
    number, variant = (index - 3) // 3 + 1, (index - 3) % 3
    col = [(60, 140, 230), (70, 60, 200), (210, 50, 50)][variant]
    r = w * 0.2
    c.ellipse((w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r), fill=tuple(v // 3 for v in col) + (255,), outline=col + (255,), width=w / 20)
    c.text((w / 2, h / 2), str(number), r * 1.5, (255, 255, 255, 255))
    c.glow(w / 24, col)
    return c.out()


GAME_ICONS = ["flag", "crown", "person", "skull", "bolt", "question"]


def game_type(name, tag, sk, index, im, face, base):
    """256x128 sheet cell: the icon tile sits in the left half"""
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    s = min(w, h)
    c.d.rectangle(c.s(0, 0, s, s), fill=(20, 70, 150, 255))
    c.d.rectangle(c.s(0, s * 0.7, s, s), fill=(14, 50, 110, 255))
    icon(c, GAME_ICONS[index % 6], s * 0.12, s * 0.12, s * 0.76, (4, 10, 24, 255))
    return c.out()


def rules_options(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    if index == 5:      # the "save changes" dialog
        c.rrect((2, h * 0.18, w - 2, h * 0.62), 6, fill=NAVY + (255,), outline=(255, 255, 255, 255), width=1.5)
        c.text((10, h * 0.25), "SAVE CHANGES ?", h * 0.07, BLUE + (255,), anchor="lm")
        c.d.multiline_text((10 * SS, h * 0.42 * SS), "Are you sure you want to\npermanently save all\nchanges to your rules?",
                           font=font(h * 0.06 * SS, "Overpass-750.ttf"), fill=BLUE + (255,), anchor="lm", spacing=2 * SS)
        return c.out()
    icon(c, GAME_ICONS[index], w * 0.14, h * 0.14, w * 0.72, (2, 8, 20, 255))
    c.glow(w / 60, BLUE)
    return c.out()


def difficulty(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    steel, dark = (150, 156, 170, 255), (60, 64, 76, 255)
    if index >= 1:
        for sign in ((-1, 1) if index >= 2 else (1,)):
            blade = Canvas(w, h)
            icon(blade, "blade", w * 0.1, h * 0.02, w * 0.8, (190, 196, 210, 255))
            c.img.alpha_composite(blade.img.rotate(38 * sign, resample=Image.BICUBIC, center=(w * SS / 2, h * SS / 2)))
        c.d = ImageDraw.Draw(c.img)
    icon(c, "shield", w * 0.2, h * 0.16, w * 0.6, steel[:3] + (255,), lw=w / 50)
    c.ellipse((w * 0.4, h * 0.36, w * 0.6, h * 0.56), fill=dark, outline=(210, 214, 226, 255), width=w / 60)
    if index == 3:
        icon(c, "skull", w * 0.3, h * 0.2, w * 0.4, (232, 232, 224, 255))
    return c.out()


def logo(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    c.text((w / 2, h * 0.5), "H A L O", h * 0.3, (255, 255, 255, 255), name="OpenCE-Regular.ttf")
    a = np.asarray(c.img, np.float32)
    ramp = np.linspace(0, 1, a.shape[0])[:, None]
    shade = np.where(ramp < 0.5, 1.0 - 0.5 * ramp, 0.35 + 0.9 * (ramp - 0.5))      # chrome: light top, dark band, light foot
    rgb = np.stack([shade * 200 + 40, shade * 215 + 40, shade * 235 + 20], -1)
    a[..., :3] = np.clip(rgb, 0, 255)
    c.img = Image.fromarray(a.astype(np.uint8))
    c.glow(h / 40, (30, 90, 220))
    return c.out()


def option_icon(kinds):
    def fn(name, tag, sk, index, im, face, base):
        w, h = im["w"], im["h"]
        c = Canvas(w, h)
        s = min(w, h) * 0.7
        icon(c, kinds[index % len(kinds)], (w - s) / 2, (h - s) / 2, s, (60, 110, 190, 150), lw=s / 40)
        return c.out()
    return fn


def flat(alpha):
    def fn(name, tag, sk, index, im, face, base):
        out = np.concatenate([base, np.full(base.shape[:2] + (1,), float(alpha), np.float32)], -1)
        return out
    return fn


def swatch(name, tag, sk, index, im, face, base):
    """player colour tiles: the kept colour in a rounded tile (or on a figure)"""
    w, h = im["w"], im["h"]
    g = np.asarray(im["faces"][face]["grid"], np.float32)
    col = tuple(int(v) for v in g[g.max(1).argmax()])
    c = Canvas(w, h)
    if "marine" in name:
        s = min(w, h * 0.5) * 1.6
        icon(c, "person", (w - s) / 2, (h - s) / 2, s, col + (255,))
        c.glow(w / 80, (20, 40, 90))
    else:
        c.rrect((w * 0.2, h * 0.36, w * 0.8, h * 0.64), w * 0.04, fill=col + (255,), outline=(255, 255, 255, 255), width=1)
    return c.out()


def picture(name, tag, sk, index, im, face, base):
    """level and map pictures: the kept colours as soft bands in the square
    on the left (the right of the sheet is black); renders replace these"""
    w, h = im["w"], im["h"]
    out = np.zeros((h, w, 4), np.float32)
    out[..., 3] = 255
    s = min(w, h)
    out[:, :s, :3] = base[:, :s]
    return out


def title(name, tag, sk, index, im, face, base):
    """menu titles: text set in OpenCE-Regular (the upstream port's pictures of it)"""
    global _titles
    if _titles is None:
        listing = json.load(open(os.path.join(CC0, "titles", "titles.json")))["assets"]
        _titles = {(a["tag"].replace("\\", "/") + ".bitmap", a["bitmap"]): a for a in listing}
    a = _titles.get((name, index))
    w, h = im["w"], im["h"]
    if a is None or not os.path.isfile(os.path.join(CC0, "titles", a["name"] + ".png")):
        if "carnage" in name:
            c = Canvas(w, h)
            c.rrect((40, 20, w - 40, h - 20), 10, fill=NAVY + (215,), outline=BLUE + (255,), width=2)
            c.line([(40, 68), (w - 40, 68)], BLUE + (255,), 1.5)
            c.text((60, 52), "POSTGAME CARNAGE REPORT", 30, (150, 190, 255, 255), anchor="ls", name="OpenCE-Regular.ttf")
            return c.out()
        return None
    png = Image.open(os.path.join(CC0, "titles", a["name"] + ".png")).convert("RGBA")
    return np.asarray(png.resize((w, h), Image.BOX), np.float32)


def black(name, tag, sk, index, im, face, base):
    out = np.zeros(base.shape[:2] + (4,), np.float32)
    out[..., 3] = 255
    return out


def draw(rel, tag, skeleton, index, im, face, base):
    from . import effects, functions, hud
    name = rel.lower()
    for pattern, fn in functions.DRAWERS + hud.DRAWERS + DRAWERS + effects.DRAWERS:
        if re.search(pattern, name):
            out = fn(name, tag, skeleton, index, im, face, base)
            if out is not None:
                return out
    return None


DRAWERS = [
    (r"^ui/shell/.*/(header_|menu_)|postgame_carnage_report", title),
    (r"^ui/mp_map_ui/", map_card),
    (r"^ui/shell/bitmaps/[abxy]_butn", button),
    (r"^ui/shell/bitmaps/arrow_", arrow),
    (r"controller_graphix", controller_badge),
    (r"game_type_grafix", game_type),
    (r"rules_options", rules_options),
    (r"difficulty_options", difficulty),
    (r"halo_logo", logo),
    (r"locked_gametype", option_icon(["lock"])),
    (r"console_grafix", option_icon(["question", "console"])),
    (r"mp_options", option_icon(["screen", "screen", "console", "people"])),
    (r"profile_options", option_icon(["pad", "pad", "people", "gear", "screen"])),
    (r"gametype_options", option_icon(["gear", "people", "flag", "pad", "screen", "gear"])),
    (r"config_controller", option_icon(["pad"])),
    (r"colors_sm|player_color_marine", swatch),
    (r"mp_map_grafix|sp_levels", picture),
    (r"xdemos_wait|shell/bitmaps/black", black),
    (r"shell/bitmaps/white", flat(255)),
    (r"semi_transparent_grey", flat(128)),
    (r"shell/bitmaps/blue", flat(200)),
    (r"shell/bitmaps/gradient", flat(160)),
    (r"^ui/(kbd_|bkd_)|^ui/shell/.*(bkd|field|pausebox|background|border|list_item)", panel),
]
