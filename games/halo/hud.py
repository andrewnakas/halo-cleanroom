"""Clean room: the HUD, drawn from code. White shapes (the game colours
them); sprite rectangles are kept numbers from the bitmap tags. Briefs were
written after one look at a dirty contact sheet (what each element is).
"""
import numpy as np

from .drawn import SS, Canvas, font

W = (255, 255, 255, 255)


def kept_shape(name, index, face, im, base):
    """The image as its kept alpha outline in the kept coarse colour (white for the
    grey HUD pieces the game tints), or None when no outline was kept."""
    from .drawn import kept_alpha
    a = kept_alpha(name, index, face, im)
    if a is None:
        return None
    grid = np.asarray(im["faces"][face]["grid"], np.float32)
    spread = (grid.max(1) - grid.min(1)).max()
    out = np.empty((im["h"], im["w"], 4), np.float32)
    if spread >= 40:
        out[..., :3] = np.clip(base * (255.0 / max(base.max(), 1.0)), 0, 255)
    elif im["format"] == "a8y8":
        # brightness and alpha are separate here and only the alpha's outline is kept:
        # bright where the shape is solid, dark in its faint fills (a white fill reads as a slab)
        out[..., :3] = (255.0 * (a / 255.0) ** 1.5)[..., None]
    else:
        out[..., :3] = 255.0
    out[..., 3] = a
    return out


def outlined(drawer, drawn_indices=()):
    """Use the kept outline; the drawer remains for images without one and for those
    that hold text (drawn_indices), which is re-typeset instead."""
    def draw(name, tag, sk, index, im, face, base):
        mine = drawer(name, tag, sk, index, im, face, base)
        if index in drawn_indices:
            return mine
        shape = kept_shape(name, index, face, im, base)
        if shape is None:
            return mine
        # hairlines fall under the outline's lowest level (alpha < 64) and vanish:
        # where the outline holds far less ink than the drawn brief, the brief stands
        if mine is not None and shape[..., 3].sum() < 0.35 * np.asarray(mine)[..., 3].sum():
            return mine
        return shape
    return draw


def ramp_direction(base, box):
    """Which way a meter fills, from the kept coarse colour under its box: +1 when the
    brightness rises to the right (the left fills first), -1 the other way; left first
    when the grid does not say."""
    l, t, r, b = box
    luma = base[t:b, l:r].mean(-1)
    if luma.shape[1] < 12:
        return 1
    third = max(luma.shape[1] // 3, 1)
    left, right = float(luma[:, :third].mean()), float(luma[:, -third:].mean())
    return -1 if left - right > 20 else 1


def rects(sk, index, im):
    """[(sequence, sprite number, (l, t, r, b) in texels)] of one image"""
    out = []
    for si, seq in enumerate(sk.sequences):
        for k, sp in enumerate(seq["sprites"]):
            if sp["bitmap"] == index:
                l, t, r, b = sp["rect"]
                out.append((si, k, (l * im["w"], t * im["h"], r * im["w"], b * im["h"])))
    return out


def slant_bar(c, box, lean=0.5, fill=W, outline=None, width=1):
    l, t, r, b = box
    d = (b - t) * lean
    c.poly([(l + d, t), (r, t), (r - d, b), (l, b)], fill=fill, outline=outline, width=width)


def ticks(c, box, n, rows=1, lean=0.5, duty=0.55):
    l, t, r, b = box
    rh = (b - t) / rows
    for row in range(rows):
        step = (r - l - rh * lean) / n
        for i in range(n):
            x = l + i * step
            slant_bar(c, (x, t + row * rh + 0.5, x + step * duty + rh * lean, t + (row + 1) * rh - 0.5), lean)


def as_meter(c, boxes, base, shape=None):
    """Meter texture. The game (rasterizer_xbox_dynavobgeom.c, the meter combiner) draws a
    texel when the meter's value is above its brightness and kills texels of zero alpha:
    brightness is a ramp across each box (the order of filling), alpha is the shape."""
    a = c.out()
    drawn = a[..., 3]
    alpha = drawn if shape is None else shape
    ramp = np.full(alpha.shape, 250.0, np.float32)
    for l, t, r, b in boxes:
        l, t, r, b = int(l), int(t), int(np.ceil(r)), int(np.ceil(b))
        ramp[t:b, l:r] = np.linspace(6, 250, max(r - l, 1))[None, ::ramp_direction(base, (l, t, r, b))]
    out = np.zeros(a.shape, np.float32)
    out[..., :3] = ramp[..., None]
    out[..., 3] = alpha
    return out


def raw_level(name, index, face, im):
    """the kept alpha levels 0..3 of an image (h,w)"""
    import os
    from cleanroom.decomp.gen import unpack_alpha2
    from . import drawn
    raw = open(os.path.join(drawn.SPEC, "alpha2", name, f"{index}_{face}.bin"), "rb").read()
    return (unpack_alpha2(raw.hex(), im["w"], im["h"]) / 85.0).astype(np.int32)


def hud_meters(name, tag, sk, index, im, face, base):
    from .drawn import kept_alpha
    c = Canvas(im["w"], im["h"])
    boxes = []
    for si, k, (l, t, r, b) in rects(sk, index, im):
        box = (l + 2, t + 2, r - 2, b - 2)
        boxes.append((l, t, r, b))
        if "unit" in name:
            if b - t > 20 and si % 2:
                ticks(c, box, 8, 1, 0.35, 0.8)
            else:
                slant_bar(c, box, 0.35)
        else:
            ticks(c, box, max(4, int((r - l) / 6)), 2 if b - t > 20 else 1)
    return as_meter(c, boxes, base, kept_alpha(name, index, face, im))


def hud_ammo_alphas(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    box = (2, 2, w - 18, h - 2)
    if index in (0, 3):
        slant_bar(c, box, 0.6, fill=W if index == 0 else (255, 255, 255, 130))
    elif index == 2:
        for i in range(3):      # rockets
            x = 4 + i * 30
            c.rrect((x, 5, x + 20, 11), 2, fill=W)
            c.poly([(x + 20, 4), (x + 27, 8), (x + 20, 12)], fill=W)
    elif index == 6:
        for row in range(2):    # long rounds
            for i in range(2):
                x = 4 + i * 34 + row * 6
                c.rrect((x, 2 + row * 7, x + 22, 6 + row * 7), 1, fill=W)
                c.poly([(x + 22, 2 + row * 7), (x + 29, 4 + row * 7), (x + 22, 6 + row * 7)], fill=W)
    else:
        n, rows = {1: (30, 2), 4: (24, 1), 5: (12, 1), 7: (12, 1)}[index]
        ticks(c, box, n, rows, 0.6, 0.5 if index != 7 else 0.7)
    return c.out()


def hud_outlines(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    if "weapon_backgrounds" in name:
        if index >= 3:
            r = h * 0.48 * (1.0 if index == 3 else 0.8)
            c.ellipse((w * 0.25 - r, h / 2 - r, w * 0.25 + r, h / 2 + r), fill=W)
        else:
            slant_bar(c, (8, 8, [56, 72, 110][index], 22), 0.5, fill=(255, 255, 255, 110))
        return c.out()
    width = [112, 56, 40, 30][index % 4]
    slant_bar(c, (6, 8, 6 + width, 22), 0.5, fill=None, outline=W, width=1)
    return c.out()


VEHICLES = {8: "BANSHEE", 9: "GUNNER", 10: "PASSENGER", 11: "SCORPION", 12: "GHOST"}


def hud_unit_backgrounds(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    if index in (0, 1):         # the frame of the shield / health meters
        c.poly([(4, 10), (14, 6), (100 if index == 0 else 90, 6), (104, 10), (104, 20), (118, 20), (118, 26),
                (92, 26), (86, 18), (14, 18)], outline=W, width=1)
    elif index in (2, 3):
        c.poly([(8, 12), (16, 10), (14, 16)], fill=W)
    elif index in (4, 5):
        slant_bar(c, (12, 13, 116, 17 if index == 4 else 15), 0.4, fill=None if index == 4 else W, outline=W)
        c.poly([(4, 13), (10, 15), (4, 17)], fill=W)
    elif index in (6, 7):       # waypoint arrow with a distance under it
        c.poly([(54, 6), (74, 6), (64, 20)], fill=(255, 255, 255, 200))
        c.text((40, 27), "15m", 7, W, anchor="mm")
    else:
        c.text((6, 16), VEHICLES.get(index, ""), 11, W, anchor="lm", name="Kenney Future Narrow.ttf")
        c.ellipse((96, 12, 104, 20), outline=W, width=1)
        c.line([(104, 16), (112, 16)], W, 1.5)
    return c.out()


DIGITS = {10: ".", 11: ":", 12: "-", 13: "m", 14: ""}


def hud_numbers(name, tag, sk, index, im, face, base):
    c = Canvas(im["w"], im["h"])
    for si, k, (l, t, r, b) in rects(sk, index, im):
        ch = str(k) if k < 10 else DIGITS.get(k, "")
        c.text(((l + r) / 2, (t + b) / 2 + 0.5), ch, (b - t) * 1.05, W, name="Kenney Future.ttf")
    return c.out()


WARNINGS = {(0, 0): "Battery\nDepleted", (56, 0): "No\nWeapon", (0, 27): "Low\nBattery", (49, 27): "No\nFuel",
            (77, 27): "Low\nFuel", (0, 54): "No\nAmmo", (42, 54): "No\nGrenades", (0, 79): "Low\nAmmo",
            (42, 79): "Reload"}


def hud_warnings(name, tag, sk, index, im, face, base):
    c = Canvas(im["w"], im["h"])
    for si, k, (l, t, r, b) in rects(sk, index, im):
        label = WARNINGS.get((round(l), round(t)))
        if label:
            c.d.multiline_text(((l + r) / 2 * SS, (t + b) / 2 * SS), label, font=font(9 * SS, "Kenney Future Narrow.ttf"),
                               fill=W, anchor="mm", align="center", spacing=0)
        elif r - l > 20:
            c.poly([(l + 2, b - 1), ((l + r) / 2, t + 1), (r - 2, b - 1)], outline=W, width=1)
        else:
            c.poly([(l + 1, b - 1), ((l + r) / 2, t + 1), (r - 1, b - 1)], fill=W)
    return c.out()


def wedge(c, cx, cy, r0, r1, ang, half=0.22, fill=W):
    a = np.deg2rad(ang)
    c.poly([(cx + r0 * np.cos(a), cy + r0 * np.sin(a)),
            (cx + r1 * np.cos(a - half), cy + r1 * np.sin(a - half)),
            (cx + r1 * np.cos(a + half), cy + r1 * np.sin(a + half))], fill=fill)


def ring(c, cx, cy, r, width=1.2, gaps=0, dash=None):
    if dash:
        for k in range(dash):
            a = 2 * np.pi * k / dash
            c.line([(cx + (r - 2) * np.cos(a), cy + (r - 2) * np.sin(a)),
                    (cx + (r + 2) * np.cos(a), cy + (r + 2) * np.sin(a))], W, 1)
        return
    c.ellipse((cx - r, cy - r, cx + r, cy + r), outline=W, width=width)
    for k in range(gaps):       # ticks through the ring
        a = 2 * np.pi * k / gaps
        c.line([(cx + (r - 4) * np.cos(a), cy + (r - 4) * np.sin(a)),
                (cx + (r + 4) * np.cos(a), cy + (r + 4) * np.sin(a))], W, 1.2)


def arc(c, box, start, end, width=1.5):
    c.d.arc(c.s(*box), start, end, fill=W, width=int(width * SS))


def hud_reticles(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    cx, cy = w / 2, h / 2
    if index == 0:              # sheet: rifle ring, small ring, dots, chevron
        ring(c, 33, 33, 24, 1.2, 4)
        ring(c, 80, 14, 11, 1)
        for dx, dy in ((104, 12), (110, 16), (106, 18)):
            c.ellipse((dx - 1, dy - 1, dx + 1, dy + 1), fill=W)
        c.line([(2, 74), (9, 68), (16, 74)], W, 1)
    elif index == 1:
        wedge(c, cx, cy, 6, 18, -90)
        for sx in (-1, 1):
            c.ellipse((cx + sx * 10 - 5, cy + 10, cx + sx * 10 + 5, cy + 20), outline=W, width=1.5)
            c.line([(cx + sx * 14, cy + 18), (cx + sx * 19, cy + 23)], W, 1.5)
    elif index == 2:
        ring(c, cx, cy, 26, 1.5, 4)
    elif index == 3:
        for a in (-90, 30, 150):
            wedge(c, cx, cy, 10, 26, a)
    elif index == 4:
        for a in (-45, 45, 135, 225):
            wedge(c, cx, cy, 12, 28, a)
    elif index == 5:
        ring(c, cx, cy, 24, dash=28)
    elif index == 6:
        for sx in (-1, 1):
            arc(c, (cx + sx * 22 - 8, cy - 8, cx + sx * 22 + 8, cy + 8), 90 if sx < 0 else 270, 270 if sx < 0 else 90)
            c.ellipse((cx + sx * 22 - 1.5, cy - 1.5, cx + sx * 22 + 1.5, cy + 1.5), fill=W)
    elif index == 7:
        ring(c, cx, cy, 30, 1)
        c.line([(cx - 34, cy), (cx + 34, cy)], W, 1)
        c.line([(cx, cy - 34), (cx, cy + 34)], W, 1)
        for k in range(1, 4):
            c.line([(cx - 6, cy + k * 7), (cx + 6, cy + k * 7)], W, 1)
    elif index == 8:
        ring(c, cx, cy, 28, 1)
    elif index == 9:
        for sx in (-1, 1):
            c.line([(cx + sx * 8, cy - 22), (cx + sx * 16, cy - 22), (cx + sx * 16, cy + 22), (cx + sx * 8, cy + 22)], W, 1.2)
            for k in range(-2, 3):
                c.line([(cx + sx * 20, cy + k * 8), (cx + sx * 26, cy + k * 8)], W, 1)
            wedge(c, cx + sx * 4, cy, 0, 8, 180 if sx > 0 else 0, 0.4)
    elif index == 10:
        for a in (-60, -120, 90):
            wedge(c, cx, cy, 8, 30, a, 0.25)
    else:
        for sx in (-1, 1):
            c.ellipse((cx + sx * 9 - 5, cy - 5, cx + sx * 9 + 5, cy + 5), outline=W, width=1.5)
            arc(c, (cx + sx * 16 - 10, cy - 10, cx + sx * 16 + 10, cy + 10), 120 if sx < 0 else 300, 240 if sx < 0 else 60)
        c.ellipse((cx - 2, cy - 14, cx + 2, cy - 10), fill=W)
    return c.out()


def hud_sprites(name, tag, sk, index, im, face, base):
    """icon sheets without a brief yet: a button or tag shape in every sprite"""
    c = Canvas(im["w"], im["h"])
    for si, k, (l, t, r, b) in rects(sk, index, im):
        if r - l < 8 or b - t < 8:
            c.ellipse((l + 1, t + 1, r - 1, b - 1), fill=W)
        elif "damage_arrows" in name:
            c.line([(l + 4, b - 4), ((l + r) / 2, t + 4), (r - 4, b - 4)], (255, 255, 255, 200), 3)
        elif "waypoints" in name:
            c.poly([(l + 6, t + 8), (r - 6, t + 8), ((l + r) / 2, b - 6)], fill=(255, 255, 255, 210), outline=W)
        elif (r - l) > 1.6 * (b - t):
            c.rrect((l + 2, t + 2, r - 2, b - 2), (b - t) * 0.4, outline=W, width=1.2)
        else:
            m = min(r - l, b - t) / 2 - 2
            c.ellipse(((l + r) / 2 - m, (t + b) / 2 - m, (l + r) / 2 + m, (t + b) / 2 + m), outline=W, width=1.5)
    if not c.img.getbbox():     # images without sprite rectangles (ammo type icons)
        w, h = im["w"], im["h"]
        slant_bar(c, (w * 0.3, h * 0.3, w * 0.7, h * 0.7), 0.5)
    return c.out()


def hud_single(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    c = Canvas(w, h)
    cx, cy = w / 2, h / 2
    if "sensor_blip_custom" in name:
        c.d.rectangle(c.s(0, 0, w, h), fill=(0, 0, 0, 255))
        c.poly([(cx, cy - 7), (cx + 7, cy), (cx, cy + 7), (cx - 7, cy)], fill=W)
    elif "sensor_blip" in name:
        c.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=W)
        c.glow(1.5, (255, 255, 255))
    elif "sweeper_mask" in name:
        out = np.full((h, w, 4), 255, np.float32)
        y, x = np.mgrid[0:h, 0:w]
        out[..., 3] = np.clip(1.25 - np.hypot(x - cx + 0.5, y - cy + 0.5) / (w * 0.36), 0, 1) * 255
        return out
    elif "sweeper" in name:
        c.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=(40, 40, 40, 255), width=6)
        c.ellipse((cx - 16, cy - 16, cx + 16, cy + 16), fill=(20, 20, 20, 200))
    elif "multiplayer" in name:
        c.poly([(cx - 10, cy - 5), (cx + 10, cy - 5), (cx, cy + 6)], fill=(30, 140, 40, 255), outline=(60, 220, 80, 255))
    elif "health_base" in name:
        slant_bar(c, (4, 8, 120, 24), 0.4, fill=(255, 255, 255, 60), outline=W)
    elif "caption" in name:
        c.text((6, 9), "TARGET DISTANCE:", 9, W, anchor="lm", name="Kenney Future Narrow.ttf")
        c.text((6, 23), "TARGET ELEVATION:", 9, W, anchor="lm", name="Kenney Future Narrow.ttf")
    elif "reticles_scope" in name:
        c.text((2, 12), "2x", 16, W, anchor="lm")
        c.text((2, 36), "10x", 16, W, anchor="lm")
        c.poly([(41, 4), (46, 9), (41, 14), (36, 9)], outline=W, width=1)
    elif "crosshairs" in name:
        k = w / 64
        if index in (0, 1):
            x = w * (0.72 if index == 0 else 0.28)
            sx = 1 if index == 0 else -1
            c.line([(x - sx * 6 * k, h * 0.1), (x, h * 0.14), (x, h * 0.86), (x - sx * 6 * k, h * 0.9)], W, 1.2 * k)
            for i in range(1, 12):
                c.line([(x - sx * (8 if i % 3 == 0 else 5) * k, h * (0.14 + 0.06 * i)),
                        (x - sx * 2 * k, h * (0.14 + 0.06 * i))], W, 0.8 * k)
        elif index in (2, 3):
            c.line([(4 * k, cy), (w - 4 * k, cy)], W, 0.8 * k)
            thick = (4 * k, w * 0.45) if index == 2 else (w * 0.55, w - 4 * k)
            c.line([(thick[0], cy), (thick[1], cy)], W, 3 * k)
        else:
            c.line([(cx, h * 0.3), (cx, h * 0.92)], W, 0.8 * k)
            c.line([(cx, h * 0.62), (cx, h * 0.92)], W, 3 * k)
    else:
        return None
    return c.out()


def scope_mask(name, tag, sk, index, im, face, base):
    """black outside the lens, clear inside with a darker rim"""
    w, h = im["w"], im["h"]
    y, x = np.mgrid[0:h, 0:w]
    if "sniper" in name:
        dx, dy = np.abs(x - w / 2 + 0.5) - w * 0.36, np.abs(y - h / 2 + 0.5) - h * 0.3
        r = h * 0.1
        dist = np.hypot(np.maximum(dx + r, 0), np.maximum(dy + r, 0)) - r      # rounded rectangle
        inside = np.clip(-dist / (h * 0.25), 0, 1)
    else:
        dist = np.hypot(x - w / 2 + 0.5, y - h / 2 + 0.5) - w * 0.47
        inside = np.clip(-dist / (w * 0.3), 0, 1)
    out = np.zeros((h, w, 4), np.float32)
    out[..., 3] = np.where(dist > 0, 255, 255 * (1 - inside) ** 3 * 0.55)
    return out


DRAWERS = [
    (r"^ui/hud/.*(ammo_meters|unit_meters)", hud_meters),
    (r"^ui/hud/.*ammo_alphas", outlined(hud_ammo_alphas)),
    (r"^ui/hud/.*(ammo_outlines|weapon_backgrounds)", outlined(hud_outlines)),
    (r"^ui/hud/.*unit_backgrounds", outlined(hud_unit_backgrounds, drawn_indices=tuple(VEHICLES))),
    (r"^ui/hud/.*counter_numbers", hud_numbers),
    (r"^ui/hud/.*reticle_warnings", hud_warnings),
    (r"^ui/hud/.*hud_reticles\.bitmap", outlined(hud_reticles)),
    (r"^ui/hud/.*scope_mask", outlined(scope_mask)),
    (r"^ui/hud/.*(msg_icons|damage_arrows|waypoints|ammo_type_icons)", outlined(hud_sprites)),
    (r"^ui/hud/.*(caption|reticles_scope)", hud_single),
    (r"^ui/hud/", outlined(hud_single)),
]
