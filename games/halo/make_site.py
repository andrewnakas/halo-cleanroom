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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("build")
    ap.add_argument("maps")
    ap.add_argument("out")
    ap.add_argument("--version", default="dev")
    a = ap.parse_args()
    if os.path.isdir(a.out):
        shutil.rmtree(a.out)
    shutil.copytree(a.build, a.out, ignore=shutil.ignore_patterns("*.rsp", "clean"))
    clean = os.path.join(a.out, "clean")
    os.makedirs(clean)
    files = []
    for name in sorted(os.listdir(a.maps)):
        if not name.endswith(".map"):
            continue
        data = open(os.path.join(a.maps, name), "rb").read()
        open(os.path.join(clean, name), "wb").write(data)
        files.append({"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    json.dump({"version": a.version, "files": files}, open(os.path.join(clean, "maps.json"), "w"), indent=1)
    print(f"{a.out}: {len(files)} maps, {sum(f['size'] for f in files) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
