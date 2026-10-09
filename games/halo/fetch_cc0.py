"""Clean room: fetch the CC0 texture library the clean bitmaps are picked from.

    python -m games.halo.fetch_cc0 <out dir> [--per 6]

ambientCG (CC0 1.0), 1K JPG, the most popular materials per material class.
Keeps Color, NormalGL and Roughness. Appends every asset to assets/LICENSES.csv.
"""
import argparse
import csv
import io
import json
import os
import urllib.request
import zipfile

API = "https://ambientcg.com/api/v2/full_json?type=Material&limit={n}&sort=Popular&q={q}&include=downloadData"
# material classes the clean bitmaps are chosen from (coarse colour + class)
CLASSES = {
    "metal": "metal", "metal_plates": "metal plates", "painted_metal": "painted metal",
    "diamond_plate": "diamond plate", "rust": "rust", "rock": "rock", "cliff": "cliff",
    "ground": "ground", "grass": "grass", "dirt": "dirt", "gravel": "gravel", "sand": "sand",
    "snow": "snow", "ice": "ice", "concrete": "concrete", "tiles": "tiles", "asphalt": "asphalt",
    "moss": "moss", "bark": "bark", "leaves": "leaves", "marble": "marble", "plaster": "plaster",
    "fabric": "fabric", "leather": "leather", "wood": "planks", "foil": "foil", "grate": "metal walkway",
}
KEEP = ("_Color.jpg", "_NormalGL.jpg", "_Roughness.jpg", "_Opacity.jpg")
UA = {"User-Agent": "halo-cleanroom asset fetch"}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--per", type=int, default=6)
    ap.add_argument("--licenses", default=os.path.join(os.path.dirname(__file__), "..", "..", "assets", "LICENSES.csv"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(os.path.dirname(a.licenses), exist_ok=True)
    have = set()
    if os.path.exists(a.licenses):
        have = {r["asset"] for r in csv.DictReader(open(a.licenses, encoding="utf-8"))}
    new_rows, index = [], {}
    idx_path = os.path.join(a.out, "index.json")
    if os.path.exists(idx_path):
        index = json.load(open(idx_path))
    for cls, q in CLASSES.items():
        found = json.loads(get(API.format(n=a.per, q=urllib.parse.quote(q))))["foundAssets"]
        for asset in found:
            aid = asset["assetId"]
            dest = os.path.join(a.out, aid)
            index.setdefault(aid, {"class": cls, "tags": asset.get("tags", [])})
            if not os.path.isdir(dest):
                dl = [d for d in asset["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]
                      if d["attribute"] == "1K-JPG"]
                if not dl:
                    continue
                z = zipfile.ZipFile(io.BytesIO(get(dl[0]["downloadLink"])))
                os.makedirs(dest)
                for name in z.namelist():
                    if name.endswith(KEEP):
                        open(os.path.join(dest, os.path.basename(name)), "wb").write(z.read(name))
            if aid not in have:
                new_rows.append({"asset": aid, "kind": "texture", "class": cls,
                                 "source": f"https://ambientcg.com/view?id={aid}", "license": "CC0-1.0"})
                have.add(aid)
    json.dump(index, open(idx_path, "w"), indent=1)
    write_header = not os.path.exists(a.licenses)
    with open(a.licenses, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["asset", "kind", "class", "source", "license"])
        if write_header:
            w.writeheader()
        w.writerows(new_rows)
    print(f"{len(index)} materials in {len(CLASSES)} classes ({len(new_rows)} new) -> {a.out}")


if __name__ == "__main__":
    import urllib.parse  # noqa: F401
    main()
