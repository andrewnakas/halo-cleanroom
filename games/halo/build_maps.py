"""Drive the per-map steps: retail map -> dirty tags -> spec -> clean tags -> clean map.

    python -m games.halo.build_maps extract  a30 a50     dirty room: invader-extract (+ repair), spec --add
    python -m games.halo.build_maps generate              clean room: generate --add (new tags only)
    python -m games.halo.build_maps build    a30 a50     invader-build into clean/maps
    python -m games.halo.build_maps all      a30          the three in order
    (map names: ui, the multiplayer maps, the campaign levels; "campaign", "multiplayer", "everything")

Work folder: HALO_WORK or D:/n64work/halo (dirty/, spec/, cc0/, clean/, tools/invader).
A campaign level is built with the single-player globals laid over the tags
(clean/tags_sp, a kept tag: the retail maps hold two different globals under one path).
After `generate`, run the taint scan before any map built from the tags is staged.
"""
import os
import shutil
import subprocess
import sys

WORK = os.environ.get("HALO_WORK", "D:/n64work/halo")
INVADER = os.path.join(WORK, "tools", "invader")
CAMPAIGN = ["a10", "a30", "a50", "b30", "b40", "c10", "c20", "c40", "d20", "d40"]
MULTIPLAYER = ["beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout", "damnation", "hangemhigh",
               "longest", "prisoner", "putput", "ratrace", "sidewinder", "wizard"]
GROUPS = {"campaign": CAMPAIGN, "multiplayer": MULTIPLAYER, "everything": ["ui"] + MULTIPLAYER + CAMPAIGN}


def scenario(name):
    if name == "ui":
        return "levels/ui/ui"
    return f"levels/{name}/{name}" if name in CAMPAIGN else f"levels/test/{name}/{name}"


def run(args, log=None, check=True):
    """Run a tool; its output goes to a log file, the last line is returned."""
    out = subprocess.run(args, capture_output=True, text=True, errors="replace")
    text = out.stdout + out.stderr
    if log:
        open(os.path.join(WORK, log), "w", encoding="utf-8").write(text)
    last = ([line for line in text.strip().splitlines() if line.strip()] or [""])[-1]
    if check and out.returncode:
        raise SystemExit(f"{os.path.basename(args[0])} failed ({out.returncode}): {last}  [{log}]")
    return last


def tool(name):
    return os.path.join(INVADER, f"invader-{name}.exe")


def extract(names):
    dirty = os.path.join(WORK, "dirty")
    for n in names:
        last = run([tool("extract"), "-m", f"{dirty}/maps", "-t", f"{dirty}/tags", "-r", f"{dirty}/maps/{n}.map"],
                   f"extract_{n}.log")
        print(f"extract {n}: {last}")
    if any(n in CAMPAIGN for n in names) and not os.path.exists(f"{dirty}/tags_sp/globals/globals.globals"):
        first = next(n for n in names if n in CAMPAIGN)
        run([tool("extract"), "-m", f"{dirty}/maps", "-t", f"{dirty}/tags_sp", "-n", "-s", "globals\\globals.globals",
             f"{dirty}/maps/{first}.map"], "extract_sp_globals.log")
    # retail tags hold values the builder rejects (enums, ranges, indices): repair in place
    last = run([tool("bludgeon"), "-t", f"{dirty}/tags", "-T", "invalid-enums", "-T", "out-of-range",
                "-T", "invalid-indices", "-b", "*"], "bludgeon.log", check=False)
    print(f"bludgeon: {last}")
    repair(f"{dirty}/tags")
    last = run([sys.executable, "-m", "games.halo.extract_tags", f"{dirty}/tags", f"{WORK}/spec", "--add"], "spec.log")
    print(f"spec: {last}")
    sp = f"{WORK}/clean/tags_sp/globals"
    os.makedirs(sp, exist_ok=True)
    shutil.copyfile(f"{dirty}/tags_sp/globals/globals.globals", f"{sp}/globals.globals")


def repair(tree):
    """Retail lens flares name reflection bitmaps their bitmap tag does not have (the builder
    refuses them, the game clamps): point those at the tag's last bitmap."""
    import struct

    from . import hek
    fixed = 0
    for folder, _, files in os.walk(tree):
        for name in files:
            if not name.endswith(".lens_flare"):
                continue
            path = os.path.join(folder, name)
            t = hek.Tag(path)
            ref = t.root["bitmap"]
            if not ref:
                continue
            bitmap = os.path.join(tree, ref.replace(chr(92), "/") + ".bitmap")
            if not os.path.exists(bitmap):
                continue
            head = open(bitmap, "rb").read(64 + 108)
            count = struct.unpack(">I", head[64 + 96:64 + 100])[0]      # the bitmap data block's count
            changed = False
            for r in t.root["reflections"]:
                kind, off, n, fmt = r.layout.fields["bitmap index"]
                if r["bitmap index"] >= max(count, 1) and r["bitmap index"] != 0xFFFF:
                    struct.pack_into(">H", t.data, r.offset + off, max(count, 1) - 1)
                    changed = True
            if changed:
                open(path, "wb").write(t.data)
                fixed += 1
    # script sources keep a few Windows-1252 characters (an ellipsis in debug prints) that
    # the script compiler rejects: a full stop of the same length
    scripts = 0
    for folder, _, files in os.walk(tree):
        for name in files:
            if not name.endswith(".scenario"):
                continue
            path = os.path.join(folder, name)
            t = hek.Tag(path)
            changed = False
            for f in t.root["source files"]:
                view = f["source"]
                for i in [i for i, b in enumerate(bytes(view)) if b > 127]:
                    view[i] = ord(".")
                    changed = True
            if changed:
                open(path, "wb").write(t.data)
                scripts += 1
    print(f"repair {tree}: {fixed} lens flares, {scripts} script sources")


def generate():
    last = run([sys.executable, "-m", "games.halo.generate", f"{WORK}/spec", f"{WORK}/cc0", f"{WORK}/clean/tags",
                "--add"], "generate_add.log")
    print(f"generate: {last}")


def build(names, tags="clean"):
    out = os.path.join(WORK, tags, "maps")
    os.makedirs(out, exist_ok=True)
    for n in names:
        overlay = ["-t", f"{WORK}/{tags}/tags_sp"] if n in CAMPAIGN else []
        last = run([tool("build"), "-g", "xbox-ntsc"] + overlay + ["-t", f"{WORK}/{tags}/tags", "-m", out, scenario(n)],
                   f"build_{n}.log")
        size = os.path.getsize(os.path.join(out, n + ".map")) / 1e6
        print(f"build {n}: {size:.1f} MB  ({last[:90]})")


def main():
    step, names = sys.argv[1], []
    for a in sys.argv[2:]:
        names += GROUPS.get(a, [a])
    if step == "repair":
        for tree in ("dirty/tags", "spec/tags", "clean/tags"):
            repair(os.path.join(WORK, tree))
    if step in ("extract", "all"):
        extract(names)
    if step in ("generate", "all"):
        generate()
    if step in ("build", "all"):
        build(names)


if __name__ == "__main__":
    main()
