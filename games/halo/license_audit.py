"""Licence gate: every asset that ships is CC0 or public domain. Run after the taint scan.

    python -m games.halo.license_audit <clean dir> <site dir> [--licenses assets/LICENSES.csv]

<clean dir> holds materials_used.json and sounds_used.json (written by generate.py next to
clean/tags). <site dir> is the folder make_site wrote (what gets published).

Fails (exit 1) when
  - a row of LICENSES.csv has a licence other than CC0-1.0 or PD (engine code is not listed
    there; it keeps its own licence),
  - a clean bitmap or sound names a source with no row (or a row that fails),
  - a published file is neither engine code, a clean map, nor an asset with a CC0/PD row.
Prints `0 failing` on success, like the taint scan.
"""
import argparse
import csv
import fnmatch
import json
import os
import sys

ALLOWED = {"CC0-1.0", "PD"}
# published files that are the engine and its page (code: OpenCE CC0, launcher MIT/CC0, vendored sha256 MIT)
CODE = ["index.html", "*.js", "*.css", "halo.wasm", "manifest.webmanifest", "version.json", ".nojekyll",
        "vendor/sha256-LICENSE.txt", "LICENSE*", "NOTICE*"]
# published files that are assets: pattern -> LICENSES.csv row
ASSETS = {"icons/*.png": "opence_web_icons"}
MAPS = ["clean/*.map", "clean/*.map.part*", "clean/maps.json"]
CODE_MADE = ("murmur (synthesised)", "drawn", "code")


def row_for(source, rows):
    """The LICENSES.csv row a recorded source comes from (None if none)."""
    if source in rows:
        return source
    if source.startswith(CODE_MADE):
        return "code"
    if "/" in source:                       # a sound: <pack folder>/.../<file>.ogg
        pack = source.split("/")[0].lower()
        for name in rows:
            if name.lower() in (pack, "kenney_" + pack) or pack == "kenney_" + name.lower():
                return name
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clean")
    ap.add_argument("site")
    ap.add_argument("--licenses", default=os.path.join(os.path.dirname(__file__), "..", "..", "assets", "LICENSES.csv"))
    a = ap.parse_args()
    rows = {r["asset"]: r for r in csv.DictReader(open(a.licenses, encoding="utf-8"))}
    failing = []
    for name, r in rows.items():
        if r["license"] not in ALLOWED:
            failing.append(f"LICENSES.csv: {name} is {r['license']}")
    used = 0
    for record in ("materials_used.json", "sounds_used.json"):
        path = os.path.join(a.clean, record)
        if not os.path.isfile(path):
            failing.append(f"{record}: missing (run generate.py)")
            continue
        for tag, source in json.load(open(path)).items():
            used += 1
            row = row_for(source, rows)
            if row is None:
                failing.append(f"{tag}: source {source!r} has no row in LICENSES.csv")
            elif row != "code" and rows[row]["license"] not in ALLOWED:
                failing.append(f"{tag}: source {source!r} is {rows[row]['license']}")
    shipped = 0
    for base, _, files in os.walk(a.site):
        if ".git" in base.split(os.sep):
            continue
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), a.site).replace(os.sep, "/")
            shipped += 1
            if any(fnmatch.fnmatch(rel, p) for p in CODE + MAPS):
                continue
            row = next((r for p, r in ASSETS.items() if fnmatch.fnmatch(rel, p)), None)
            if row is None:
                failing.append(f"site: {rel} is not code, a clean map or a listed asset")
            elif row not in rows or rows[row]["license"] not in ALLOWED:
                failing.append(f"site: {rel} needs a CC0/PD row {row!r}")
    for line in failing[:60]:
        print(line)
    if len(failing) > 60:
        print(f"... {len(failing) - 60} more")
    print(f"{len(rows)} licence rows, {used} clean sources, {shipped} published files; {len(failing)} failing")
    sys.exit(1 if failing else 0)


if __name__ == "__main__":
    main()
