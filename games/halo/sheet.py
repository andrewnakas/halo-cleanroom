"""Dev tool: contact sheet of bitmap tags (dirty or clean tree) for one look.

    python -m games.halo.sheet <tags dir> <out.png> <path regex> [--cell 128] [--cols 10] [--skip regex]

Images are shown over a checkerboard with their tag name and index. Sheets of
the dirty tree are dev-only: never commit or publish them.
"""
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

from . import tags


def main():
    root, out, pattern = sys.argv[1:4]
    opt = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    cell, cols, skip = int(opt("--cell", 128)), int(opt("--cols", 10)), opt("--skip", None)
    items = []
    for p in tags.find(root, "bitmap"):
        rel = os.path.relpath(p, root).replace("\\", "/")
        if not re.search(pattern, rel) or (skip and re.search(skip, rel)):
            continue
        t = tags.BitmapTag(p)
        for i, b in enumerate(t.bitmaps):
            items.append((f"{os.path.basename(rel)[:-7]}#{i}", b.read(0, 0)))
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 12)), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    yy, xx = np.mgrid[0:cell, 0:cell]
    checker = (((xx // 8 + yy // 8) % 2) * 40 + 60).astype(np.uint8)
    for k, (label, rgba) in enumerate(items):
        img = Image.fromarray(rgba).convert("RGBA")
        img.thumbnail((cell, cell), Image.LANCZOS)
        bg = Image.fromarray(np.dstack([checker] * 3)).convert("RGBA")
        bg.alpha_composite(img, ((cell - img.width) // 2, (cell - img.height) // 2))
        x, y = (k % cols) * cell, (k // cols) * (cell + 12)
        sheet.paste(bg.convert("RGB"), (x, y))
        draw.text((x + 1, y + cell), label[-22:], fill=(255, 255, 120))
    sheet.save(out)
    print(f"{len(items)} images -> {out} ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    main()
