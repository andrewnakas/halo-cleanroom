"""Assemble a site folder: the web build + maps under clean/ with maps.json.

    python -m games.halo.make_site <build/web/site> <maps dir> <out site> [--version V]

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("build")
    ap.add_argument("maps")
    ap.add_argument("out")
    ap.add_argument("--version", default="dev")
    a = ap.parse_args()
    if os.path.isdir(a.out):      # emptied, not removed: a dev server may be serving it
        for name in os.listdir(a.out):
            path = os.path.join(a.out, name)
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    shutil.copytree(a.build, a.out, ignore=shutil.ignore_patterns("*.rsp", "clean"), dirs_exist_ok=True)
    clean = os.path.join(a.out, "clean")
    os.makedirs(clean)
    files = []
    for name in sorted(os.listdir(a.maps)):
        if not name.endswith(".map"):
            continue
        data = open(os.path.join(a.maps, name), "rb").read()
        entry = {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if len(data) > PART * 2 - 1:      # GitHub takes no file over 100 MB: serve it in pieces
            entry["parts"] = (len(data) + PART - 1) // PART
            for i in range(entry["parts"]):
                open(os.path.join(clean, f"{name}.part{i}"), "wb").write(data[i * PART:(i + 1) * PART])
        else:
            open(os.path.join(clean, name), "wb").write(data)
        files.append(entry)
    json.dump({"version": a.version, "files": files}, open(os.path.join(clean, "maps.json"), "w"), indent=1)
    print(f"{a.out}: {len(files)} maps, {sum(f['size'] for f in files) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
