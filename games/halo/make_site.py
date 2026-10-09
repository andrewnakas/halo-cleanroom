"""Assemble a site folder: the web build + maps under clean/ with maps.json.

    python -m games.halo.make_site <build/web/site> <maps dir> <out site> [--version V]
        [--maps ui,bloodgulch,...] [--extra <out dir>=<base url>=a30,a50,...]...

--maps limits the maps stored in the main site (default: every map that no --extra takes).
--extra puts the named maps in another folder (its own Pages repository of the same
origin, e.g. D:/n64work/halo/pages_maps1=/halo-cleanroom-maps1/clean/=a30,a50); the main
manifest lists them with that base URL.

For publishing, <maps dir> must hold clean maps only (taint scan 0 first).
Dev round-trip tests point it at dirty maps: name that output *_DIRTY and
never publish it.
"""
import argparse
import hashlib
import json
import os
import shutil


PART = 48 * 1024 * 1024


def empty(folder):
    """Emptied, not removed: a dev server may be serving it, and .git stays."""
    os.makedirs(folder, exist_ok=True)
    for name in os.listdir(folder):
        if name == ".git":
            continue
        path = os.path.join(folder, name)
        shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)


def store(maps, name, clean):
    data = open(os.path.join(maps, name), "rb").read()
    entry = {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if len(data) > PART * 2 - 1:      # GitHub takes no file over 100 MB: serve it in pieces
        entry["parts"] = (len(data) + PART - 1) // PART
        entry["part_sha256"] = []
        for i in range(entry["parts"]):
            piece = data[i * PART:(i + 1) * PART]
            entry["part_sha256"].append(hashlib.sha256(piece).hexdigest())
            open(os.path.join(clean, f"{name}.part{i}"), "wb").write(piece)
    else:
        open(os.path.join(clean, name), "wb").write(data)
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("build")
    ap.add_argument("maps")
    ap.add_argument("out")
    ap.add_argument("--version", default="dev")
    ap.add_argument("--maps", dest="only", default="")
    ap.add_argument("--extra", action="append", default=[])
    a = ap.parse_args()
    names = sorted(n for n in os.listdir(a.maps) if n.endswith(".map"))
    extras = []
    taken = set()
    for spec in a.extra:
        folder, base, maps = spec.rsplit("=", 2)
        maps = [m + ".map" for m in maps.split(",") if m]
        extras.append((folder, base, maps))
        taken.update(maps)
    main_names = [m + ".map" for m in a.only.split(",") if m] or [n for n in names if n not in taken]
    for n in main_names + sorted(taken):
        if n not in names:
            raise SystemExit(f"{n} is not in {a.maps}")

    empty(a.out)
    shutil.copytree(a.build, a.out, ignore=shutil.ignore_patterns("*.rsp", "clean"), dirs_exist_ok=True)
    clean = os.path.join(a.out, "clean")
    os.makedirs(clean)
    files = [store(a.maps, n, clean) for n in main_names]
    report = [f"{a.out}: {len(files)} maps, {sum(f['size'] for f in files) / 1e6:.1f} MB"]
    for folder, base, maps in extras:
        empty(folder)
        os.makedirs(os.path.join(folder, "clean"))
        open(os.path.join(folder, ".nojekyll"), "w").close()
        open(os.path.join(folder, "index.html"), "w").write(
            '<!doctype html><meta charset="utf-8"><title>Halo clean-room maps</title>'
            '<p>Clean-room campaign maps for <a href="/halo-cleanroom/">halo-cleanroom</a>.</p>\n')
        entries = [dict(store(a.maps, n, os.path.join(folder, "clean")), base=base) for n in maps]
        files += entries
        report.append(f"{folder}: {len(entries)} maps, {sum(f['size'] for f in entries) / 1e6:.1f} MB")
    json.dump({"version": a.version, "files": files}, open(os.path.join(clean, "maps.json"), "w"), indent=1)
    print("\n".join(report))


if __name__ == "__main__":
    main()
