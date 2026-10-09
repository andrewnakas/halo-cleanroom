"""Read any kept tag (HEK tag file) through tag definitions.

    python -m games.halo.hek <tags dir> [regex]      walk every tag; report those that do not parse

The layouts come from Invader's definition JSON (GPLv3, tool data: fetched into
<work>/tools/invader_defs, not part of this repository; HALO_DEFS overrides the folder).
A tag file is a 64-byte header, the root struct, then for every element, in field
order, the payload of each block (its element array, then those elements' payloads),
tag reference (its path) and data field. Everything is big-endian.

    t = hek.Tag(path)
    t.root["lightmaps"]                 list of Element
    el["bitmap"], el["shader"]          numbers, tuples, paths (references), bytes (data)
    hek.array(block, "x")               (when a block is large) numpy view of one field
"""
import glob
import json
import os
import re
import struct
import sys

import numpy as np

DEFS_DIR = os.environ.get("HALO_DEFS", "D:/n64work/halo/tools/invader_defs")
HEADER = 64

# type -> (size, struct format per value, numpy dtype)
PRIM = {
    "int8": (1, "b"), "uint8": (1, "B"), "int16": (2, "h"), "uint16": (2, "H"), "int32": (4, "i"),
    "uint32": (4, "I"), "float": (4, "f"), "Angle": (4, "f"), "Fraction": (4, "f"), "Index": (2, "H"),
    "Pointer": (4, "I"), "TagID": (4, "I"), "TagFourCC": (4, "4s"), "ScenarioScriptNodeValue": (4, "I"),
    "ColorARGBInt": (4, "I"), "Point2DInt": (4, "hh"), "Rectangle2D": (8, "hhhh"), "Point2D": (8, "ff"),
    "Vector2D": (8, "ff"), "Euler2D": (8, "ff"), "Point3D": (12, "fff"), "Vector3D": (12, "fff"),
    "Euler3D": (12, "fff"), "ColorRGB": (12, "fff"), "Plane2D": (12, "fff"), "Plane3D": (16, "ffff"),
    "Quaternion": (16, "ffff"), "ColorARGB": (16, "ffff"), "Matrix": (36, "9f"), "TagString": (32, "32s"),
    "TagReflexive": (12, None), "TagDependency": (16, None), "TagDataOffset": (20, None),
}
_defs = None


def defs():
    global _defs
    if _defs is None:
        _defs = {}
        files = glob.glob(os.path.join(DEFS_DIR, "*.json"))
        if not files:
            raise SystemExit(f"no tag definitions in {DEFS_DIR}")
        for f in files:
            for x in json.load(open(f, encoding="utf-8")):
                _defs[x["name"]] = x
    return _defs


class Layout:
    """One struct: fields as (name, type, offset, values) and its dynamic fields."""
    cache = {}

    def __init__(self, name):
        d = defs()[name]
        self.name = name
        self.fields = {}
        self.dynamic = []        # (offset, kind, child layout name)
        off = 0
        if "inherits" in d:
            parent = layout(d["inherits"])
            self.fields.update(parent.fields)
            self.dynamic += parent.dynamic
            off = parent.size
        for f in d["fields"]:
            if isinstance(f, str):
                continue
            t = f["type"]
            if t == "pad":
                off += f["size"]
                continue
            other = defs().get(t)
            if other is not None and other["type"] == "enum":
                size, fmt = 2, "H"
            elif other is not None and other["type"] == "bitfield":
                size, fmt = other["width"] // 8, {8: "B", 16: "H", 32: "I"}[other["width"]]
            elif other is not None:      # an embedded struct
                sub = layout(t)
                for n, (st, so, sn, sf) in sub.fields.items():
                    self.fields[f"{f['name']}.{n}"] = (st, off + so, sn, sf)
                self.dynamic += [(off + o, k, c) for o, k, c in sub.dynamic]
                off += sub.size * f.get("count", 1)
                continue
            else:
                size, fmt = PRIM[t]
            n = f.get("count", 1) * (2 if f.get("bounds") else 1)
            self.fields[f["name"]] = (t, off, n, fmt)
            if fmt is None:
                kind = {"TagReflexive": "block", "TagDependency": "ref", "TagDataOffset": "data"}[t]
                self.dynamic.append((off, kind, f.get("struct")))
            off += size * n
        self.size = d.get("size", off)
        assert off == self.size, (name, off, self.size)
        self.flat = not self.dynamic


def layout(name):
    if name not in Layout.cache:
        Layout.cache[name] = Layout(name)
    return Layout.cache[name]


class Block(list):
    """The elements of a tag block (a list); large flat blocks keep only their place."""
    def __init__(self, tag, lay, offset, count):
        super().__init__()
        self.tag, self.layout, self.offset, self.count = tag, lay, offset, count

    def __len__(self):
        return self.count

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(self.count))]
        if i < 0:
            i += self.count
        if not 0 <= i < self.count:
            raise IndexError(i)
        if list.__len__(self):
            return list.__getitem__(self, i)
        return Element(self.tag, self.layout, self.offset + i * self.layout.size)

    def __iter__(self):
        return (self[i] for i in range(self.count))


class Element:
    def __init__(self, tag, lay, offset):
        self.tag, self.layout, self.offset = tag, lay, offset
        self.children = {}       # field offset -> Block / path / bytes

    def __contains__(self, name):
        return name in self.layout.fields

    def __getitem__(self, name):
        t, off, n, fmt = self.layout.fields[name]
        if fmt is None:
            return self.children.get(off, "" if t == "TagDependency" else b"" if t == "TagDataOffset" else [])
        v = struct.unpack_from(">" + fmt * n, self.tag.data, self.offset + off)
        if t == "TagString":
            return v[0].split(b"\0")[0].decode("latin1")
        return v[0] if len(v) == 1 else v

    def ref_class(self, name):
        t, off, n, fmt = self.layout.fields[name]
        return bytes(self.tag.data[self.offset + off:self.offset + off + 4]).decode("latin1")


def array(block, name):
    """One field of every element of a block as a numpy array (count, values)."""
    t, off, n, fmt = block.layout.fields[name]
    size = PRIM[t][0] * n if t in PRIM else struct.calcsize(">" + fmt * n)
    code = (fmt * n).replace("9f", "f" * 9)
    kinds = set(code)
    assert len(kinds) == 1, code
    dt = np.dtype(">" + {"f": "f4", "h": "i2", "H": "u2", "i": "i4", "I": "u4", "b": "i1", "B": "u1"}[code[0]])
    raw = np.frombuffer(block.tag.data, np.uint8, block.count * block.layout.size, block.offset)
    raw = raw.reshape(block.count, block.layout.size)[:, off:off + size]
    return np.ascontiguousarray(raw).view(dt).reshape(block.count, len(code))


class Tag:
    def __init__(self, path, root=None):
        self.path = path
        self.data = bytearray(open(path, "rb").read())
        self.group = bytes(self.data[36:40]).decode("latin1")
        assert self.data[60:64] == b"blam", path
        if root is None:
            ext = os.path.splitext(path)[1][1:]
            root = ROOTS()[ext]
        lay = layout(root)
        self.root = Element(self, lay, HEADER)
        self.end = self._walk(lay, HEADER, 1, HEADER + lay.size, [self.root])

    def _walk(self, lay, offset, count, pos, elements):
        data = self.data
        for i in range(count):
            base = offset + i * lay.size
            el = elements[i] if elements is not None else None
            for off, kind, child in lay.dynamic:
                at = base + off
                if kind == "block":
                    n = struct.unpack_from(">I", data, at)[0]
                    if not n:
                        continue
                    cl = layout(child)
                    block = Block(self, cl, pos, n)
                    start = pos
                    pos += n * cl.size
                    if pos > len(data):
                        raise ValueError(f"{self.path}: block {child} runs past the end")
                    if not cl.flat:
                        kids = [Element(self, cl, start + j * cl.size) for j in range(n)]
                        list.extend(block, kids)
                        pos = self._walk(cl, start, n, pos, kids)
                    if el is not None:
                        el.children[off] = block
                elif kind == "ref":
                    n = struct.unpack_from(">I", data, at + 8)[0]
                    if n:
                        if el is not None:
                            el.children[off] = bytes(data[pos:pos + n]).decode("latin1")
                        pos += n + 1
                else:
                    n = struct.unpack_from(">I", data, at)[0]
                    if n:
                        if el is not None:
                            el.children[off] = memoryview(data)[pos:pos + n]
                        pos += n
        return pos


_roots = None


def ROOTS():
    """file extension -> root struct name"""
    global _roots
    if _roots is None:
        _roots = {}
        for name, d in defs().items():
            if d["type"] == "struct" and "class" in d:
                _roots[d["class"]] = name
    return _roots


def main():
    root = sys.argv[1]
    match = sys.argv[2] if len(sys.argv) > 2 else None
    ok, bad, skipped = 0, [], {}
    for folder, _, files in os.walk(root):
        for name in files:
            p = os.path.join(folder, name)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            if match and not re.search(match, rel):
                continue
            ext = os.path.splitext(name)[1][1:]
            if ext not in ROOTS():
                skipped[ext] = skipped.get(ext, 0) + 1
                continue
            try:
                t = Tag(p)
                if t.end != len(t.data):
                    bad.append(f"{rel}: ends at {t.end} of {len(t.data)}")
                else:
                    ok += 1
            except Exception as e:      # noqa: BLE001 (a report, not a handler)
                bad.append(f"{rel}: {type(e).__name__} {e}")
    print(f"{ok} tags parsed to their last byte; {len(bad)} did not; no definition for {skipped}")
    for line in bad[:15]:
        print("  " + line)


if __name__ == "__main__":
    main()
