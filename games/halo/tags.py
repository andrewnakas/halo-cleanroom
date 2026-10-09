"""Halo tag files (HEK layout, big-endian) as Invader extracts them: the
bitmap tag's pixels, read and replaced in place. Every other field is kept.

    python -m games.halo.tags <tags dir>      # census: counts per format/type
"""
import os
import struct
import sys

import numpy as np

from .codecs import decode_dxt, encode_dxt

HEADER = 64
BITMAP_MAIN = 108
FORMATS = {0: "a8", 1: "y8", 2: "ay8", 3: "a8y8", 6: "r5g6b5", 8: "a1r5g5b5", 9: "a4r4g4b4",
           10: "x8r8g8b8", 11: "a8r8g8b8", 14: "dxt1", 15: "dxt3", 16: "dxt5", 17: "p8"}
BPP = {"a8": 1, "y8": 1, "ay8": 1, "p8": 1, "a8y8": 2, "r5g6b5": 2, "a1r5g5b5": 2, "a4r4g4b4": 2,
       "x8r8g8b8": 4, "a8r8g8b8": 4}
TYPES = {0: "2d", 1: "3d", 2: "cube", 3: "white"}


def level_size(fmt, w, h, d=1):
    if fmt.startswith("dxt"):
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fmt == "dxt1" else 16) * d
    return w * h * d * BPP[fmt]


def decode(fmt, data, w, h):
    """one level -> (h,w,4) uint8 RGBA"""
    if fmt.startswith("dxt"):
        return decode_dxt(data, w, h, fmt)
    n = w * h
    out = np.empty((n, 4), np.uint8)
    if fmt in ("a8", "y8", "ay8", "p8"):
        v = np.frombuffer(data[:n], np.uint8)
        out[:, :3] = 255 if fmt == "a8" else v[:, None]
        out[:, 3] = 255 if fmt in ("y8", "p8") else v
    elif fmt == "a8y8":
        v = np.frombuffer(data[:n * 2], np.uint8).reshape(n, 2)
        out[:, :3] = v[:, :1]
        out[:, 3] = v[:, 1]
    elif fmt in ("x8r8g8b8", "a8r8g8b8"):
        v = np.frombuffer(data[:n * 4], np.uint8).reshape(n, 4)
        out[:, 0], out[:, 1], out[:, 2] = v[:, 2], v[:, 1], v[:, 0]
        out[:, 3] = v[:, 3] if fmt == "a8r8g8b8" else 255
    else:
        v = np.frombuffer(data[:n * 2], "<u2").astype(np.uint32)
        if fmt == "r5g6b5":
            r, g, b, a = (v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31, v * 0 + 255
        elif fmt == "a1r5g5b5":
            r, g, b, a = ((v >> 10) & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, (v & 31) * 255 // 31, (v >> 15) * 255
        else:
            r, g, b, a = ((v >> 8) & 15) * 17, ((v >> 4) & 15) * 17, (v & 15) * 17, (v >> 12) * 17
        out[:] = np.stack([r, g, b, a], -1)
    return out.reshape(h, w, 4)


def encode(fmt, rgba):
    """(h,w,4) uint8 RGBA -> bytes of one level"""
    rgba = np.asarray(rgba, np.uint8)
    if fmt.startswith("dxt"):
        return encode_dxt(rgba, fmt)
    r, g, b, a = (rgba[..., i].astype(np.uint32) for i in range(4))
    y = ((r * 77 + g * 150 + b * 29) >> 8).astype(np.uint8)
    if fmt == "a8":
        return a.astype(np.uint8).tobytes()
    if fmt in ("y8", "p8"):
        return y.tobytes()
    if fmt == "ay8":
        return a.astype(np.uint8).tobytes()
    if fmt == "a8y8":
        return np.stack([y, a.astype(np.uint8)], -1).tobytes()
    if fmt in ("x8r8g8b8", "a8r8g8b8"):
        return np.stack([b, g, r, a if fmt == "a8r8g8b8" else a * 0 + 255], -1).astype(np.uint8).tobytes()
    if fmt == "r5g6b5":
        v = (r * 31 + 127) // 255 << 11 | (g * 63 + 127) // 255 << 5 | (b * 31 + 127) // 255
    elif fmt == "a1r5g5b5":
        v = (a >> 7) << 15 | (r * 31 + 127) // 255 << 10 | (g * 31 + 127) // 255 << 5 | (b * 31 + 127) // 255
    else:
        v = (a * 15 + 127) // 255 << 12 | (r * 15 + 127) // 255 << 8 | (g * 15 + 127) // 255 << 4 | (b * 15 + 127) // 255
    return v.astype("<u2").tobytes()


class Bitmap:
    """one bitmap of a bitmap tag"""

    def __init__(self, tag, entry_offset):
        self.tag, self.entry = tag, entry_offset
        e = tag.data[entry_offset:entry_offset + 48]
        self.width, self.height, self.depth, t, f, self.flags = struct.unpack(">6H", e[4:16])
        self.type, self.format = TYPES.get(t, str(t)), FORMATS.get(f, str(f))
        self.mipmaps = struct.unpack(">H", e[20:22])[0]
        self.pixel_offset, self.pixel_size = struct.unpack(">2I", e[24:32])

    @property
    def faces(self):
        return 6 if self.type == "cube" else 1

    def levels(self):
        """(mip, face, offset in the tag's pixel data, w, h, d, size); the tag stores
        mip-major: every face of a level, then the next level"""
        out, off = [], self.pixel_offset
        for mip in range(self.mipmaps + 1):
            w, h = max(1, self.width >> mip), max(1, self.height >> mip)
            d = max(1, self.depth >> mip) if self.type == "3d" else 1
            size = level_size(self.format, w, h, d)
            for face in range(self.faces):
                out.append((mip, face, off, w, h, d, size))
                off += size
        return out

    def read(self, mip=0, face=0):
        for m, f, off, w, h, d, size in self.levels():
            if (m, f) == (mip, face):
                base = self.tag.pixels + off
                return decode(self.format, self.tag.data[base:base + level_size(self.format, w, h)], w, h)
        raise KeyError((mip, face))

    def write(self, make):
        """make(mip, face, w, h, slice) -> RGBA (h,w,4); replaces every level"""
        for m, f, off, w, h, d, size in self.levels():
            one = level_size(self.format, w, h)
            buf = b"".join(encode(self.format, make(m, f, w, h, z)) for z in range(d))
            assert len(buf) == size == one * d, (self.tag.path, self.format, w, h, len(buf), size)
            base = self.tag.pixels + off
            self.tag.data[base:base + size] = buf


class BitmapTag:
    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, "rb").read())
        assert self.data[36:40] == b"bitm" and self.data[60:64] == b"blam", path
        h = self.data[HEADER:HEADER + BITMAP_MAIN]
        self.type, self.encoding, self.usage, self.flags = struct.unpack(">4H", h[:8])
        plate = struct.unpack(">I", h[28:32])[0]
        self.pixel_bytes = struct.unpack(">I", h[48:52])[0]
        nseq, nbitmaps = struct.unpack(">I", h[84:88])[0], struct.unpack(">I", h[96:100])[0]
        self.pixels = HEADER + BITMAP_MAIN + plate
        off = self.pixels + self.pixel_bytes
        self.sequences = []
        seqs = [self.data[off + i * 64:off + (i + 1) * 64] for i in range(nseq)]
        off += nseq * 64
        for s in seqs:
            first, count = struct.unpack(">2H", s[32:36])
            nsprites = struct.unpack(">I", s[52:56])[0]
            sprites = []
            for i in range(nsprites):
                bi, _, _, left, right, top, bottom, rx, ry = struct.unpack(">HHI6f", self.data[off:off + 32])
                sprites.append({"bitmap": bi, "rect": [left, top, right, bottom], "reg": [rx, ry]})
                off += 32
            self.sequences.append({"name": s[:32].split(b"\0")[0].decode("latin-1"), "first": first,
                                   "count": count, "sprites": sprites})
        self.bitmaps = [Bitmap(self, off + i * 48) for i in range(nbitmaps)]
        assert off + nbitmaps * 48 == len(self.data), (path, off + nbitmaps * 48, len(self.data))

    def save(self, path=None):
        path = path or self.path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(self.data)


class SoundTag:
    """sound tag: pitch ranges -> permutations -> sample data (Xbox ADPCM here)"""

    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, "rb").read())
        assert self.data[36:40] == b"snd!", path
        h = self.data[HEADER:HEADER + 164]
        self.sound_class, rate = struct.unpack(">2H", h[4:8])
        self.rate = 44100 if rate else 22050
        enc, self.compression = struct.unpack(">2H", h[108:112])
        self.channels = 2 if enc else 1
        promo = struct.unpack(">I", h[120:124])[0]
        off = HEADER + 164 + (promo + 1 if promo else 0)
        nranges = struct.unpack(">I", h[152:156])[0]
        ranges = [bytes(self.data[off + i * 72:off + (i + 1) * 72]) for i in range(nranges)]
        off += nranges * 72
        self.permutations = []   # {range, name, offset, size, mouth_offset, mouth_size}
        for ri, r in enumerate(ranges):
            n = struct.unpack(">I", r[60:64])[0]
            perms = [bytes(self.data[off + i * 124:off + (i + 1) * 124]) for i in range(n)]
            off += n * 124
            for pm in perms:
                size, mouth, sub = (struct.unpack(">I", pm[o:o + 4])[0] for o in (64, 84, 104))
                self.permutations.append({
                    "range": ri, "name": pm[:32].split(b"\0")[0].decode("latin-1"),
                    "compression": struct.unpack(">H", pm[40:42])[0],
                    "next": struct.unpack(">H", pm[42:44])[0], "actual": struct.unpack(">H", r[44:46])[0],
                    "offset": off, "size": size, "mouth_offset": off + size, "mouth_size": mouth})
                off += size + mouth + sub
        assert off == len(self.data), (path, off, len(self.data))

    def samples(self, perm):
        return bytes(self.data[perm["offset"]:perm["offset"] + perm["size"]])

    def replace(self, perm, data):
        assert len(data) == perm["size"], (self.path, len(data), perm["size"])
        self.data[perm["offset"]:perm["offset"] + perm["size"]] = data

    def save(self, path=None):
        path = path or self.path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(self.data)


class FontTag:
    """font tag: characters (metrics kept) + 8-bit coverage pixels"""

    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, "rb").read())
        assert self.data[36:40] == b"font", path
        h = self.data[HEADER:HEADER + 156]
        self.ascending, self.descending = struct.unpack(">2h", h[4:8])
        assert struct.unpack(">I", h[48:52])[0] == 0 and all(
            struct.unpack(">I", h[o + 8:o + 12])[0] == 0 for o in (60, 76, 92, 108)), path
        n = struct.unpack(">I", h[124:128])[0]
        self.pixel_bytes = struct.unpack(">I", h[136:140])[0]
        off = HEADER + 156
        self.characters = []
        for i in range(n):
            c, width, bw, bh, ox, oy, _, _, po = struct.unpack(">H5hHHi", self.data[off:off + 20])
            self.characters.append({"char": c, "width": width, "w": bw, "h": bh, "ox": ox, "oy": oy, "offset": po})
            off += 20
        self.pixels = off
        assert off + self.pixel_bytes == len(self.data), path

    def save(self, path=None):
        path = path or self.path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(self.data)


def find(tags, ext):
    out = []
    for root, _, files in os.walk(tags):
        out += [os.path.join(root, f) for f in files if f.endswith("." + ext)]
    return sorted(out)


def main():
    counts, bad = {}, 0
    for p in find(sys.argv[1], "bitmap"):
        try:
            t = BitmapTag(p)
            for b in t.bitmaps:
                assert b.levels()[-1][2] + b.levels()[-1][6] <= t.pixel_bytes, "levels overrun"
                b.read()
                k = (b.type, b.format)
                counts[k] = counts.get(k, 0) + 1
        except Exception as e:  # noqa: BLE001
            bad += 1
            print("BAD", os.path.relpath(p, sys.argv[1]), repr(e)[:120])
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"{v:5d} {k[0]:5s} {k[1]}")
    print(f"{sum(counts.values())} bitmaps, {bad} bad tags")


if __name__ == "__main__":
    main()
