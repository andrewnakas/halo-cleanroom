"""Dirty room: copy maps/ out of an Xbox disc image (XDVDFS).

    python -m games.halo.xiso_extract <image.iso|.xiso> <out dir> [--all]

Reads only the file system; writes maps/*.map (or every file with --all)
into <out dir>. The output is retail data: keep it under D:/n64work/halo/dirty,
never in the repo.
"""
import argparse
import os
import struct
import sys

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
# game partition offsets: extract-xiso images, XGD1, XGD2, XGD3 dumps
PARTITIONS = (0, 0x18300000, 0xFD90000, 0x2080000)


def find_partition(f):
    for base in PARTITIONS:
        f.seek(base + 32 * SECTOR)
        if f.read(20) == MAGIC:
            return base
    sys.exit("not an Xbox disc image (no XDVDFS volume descriptor)")


def read_dir(f, base, sector, size):
    """every entry of a directory: (name, sector, size, is_dir)"""
    if size == 0:
        return []
    f.seek(base + sector * SECTOR)
    data = f.read(size)
    out, seen, stack = [], set(), [0]
    while stack:
        off = stack.pop()
        if off in seen or off + 14 > len(data):
            continue
        seen.add(off)
        left, right, sec, sz, attr, nlen = struct.unpack_from("<HHIIBB", data, off)
        if left == 0xFFFF:  # padding
            continue
        name = data[off + 14:off + 14 + nlen].decode("latin-1")
        out.append((name, sec, sz, bool(attr & 0x10)))
        if left:
            stack.append(left * 4)
        if right:
            stack.append(right * 4)
    return out


def walk(f, base, sector, size, prefix=""):
    for name, sec, sz, is_dir in read_dir(f, base, sector, size):
        path = prefix + name
        if is_dir:
            yield from walk(f, base, sec, sz, path + "/")
        else:
            yield path, sec, sz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    n = total = 0
    with open(a.image, "rb") as f:
        base = find_partition(f)
        f.seek(base + 32 * SECTOR + 20)
        root_sector, root_size = struct.unpack("<II", f.read(8))
        for path, sec, sz in walk(f, base, root_sector, root_size):
            if not a.all and not (path.lower().startswith("maps/") and path.lower().endswith(".map")):
                continue
            dest = os.path.join(a.out, *path.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            f.seek(base + sec * SECTOR)
            with open(dest, "wb") as o:
                left = sz
                while left:
                    chunk = f.read(min(left, 1 << 22))
                    o.write(chunk)
                    left -= len(chunk)
            n += 1
            total += sz
    print(f"partition 0x{base:x}: {n} files, {total / 1e6:.1f} MB -> {a.out}")


if __name__ == "__main__":
    main()
