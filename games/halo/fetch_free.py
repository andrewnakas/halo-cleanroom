"""Clean room: fetch the CC0 fonts and the public-domain voices, pinned by SHA-256.

    python -m games.halo.fetch_free <cc0 dir> [--voices <piper voices dir>]

Fonts: Kenney Fonts (CC0 1.0) -> <cc0>/fonts/Kenney Future.ttf, Kenney Future Narrow.ttf.
Titles: OpenCE's titles.json (CC0 layout facts: each title's words and letter positions)
-> <cc0>/titles/titles.json. Its pictures are not fetched; drawn.title sets the letters.
Voices: the Piper voices in dialog.VOICES (model and data public domain), with their
MODEL_CARDs -> <voices dir> (default $PIPER_VOICES).
"""
import argparse
import hashlib
import io
import os
import urllib.request
import zipfile

from . import dialog

UA = {"User-Agent": "halo-cleanroom asset fetch"}
FONTS_ZIP = ("https://kenney.nl/media/pages/assets/kenney-fonts/8d5435c213-1677661710/kenney_kenney-fonts.zip",
             "4e69a86eef3cd47e9d8207413868cd08bcddeb2dae4047dbd10362e2a7a16bac")
FONTS = ("Kenney Future.ttf", "Kenney Future Narrow.ttf")
# OpenCE main at the time of writing; titles.json is layout facts (text, letter lefts, cap height)
TITLES = "https://raw.githubusercontent.com/OpenCommunityEdition/OpenCE/{ref}/port/assets/titles/titles.json"
PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/{who}/{quality}/{name}{ext}"


def get(url, sha=None):
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read()
    if sha and hashlib.sha256(data).hexdigest() != sha:
        raise SystemExit(f"{url}: sha256 {hashlib.sha256(data).hexdigest()}, expected {sha}")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cc0")
    ap.add_argument("--voices", default=dialog.PIPER)
    ap.add_argument("--opence-ref", default="main")
    a = ap.parse_args()
    fonts = os.path.join(a.cc0, "fonts")
    os.makedirs(fonts, exist_ok=True)
    z = zipfile.ZipFile(io.BytesIO(get(*FONTS_ZIP)))
    for name in FONTS:
        open(os.path.join(fonts, name), "wb").write(z.read("Fonts/" + name))
    open(os.path.join(fonts, "Kenney-CC0.txt"), "wb").write(z.read("License.txt"))
    os.makedirs(os.path.join(a.cc0, "titles"), exist_ok=True)
    open(os.path.join(a.cc0, "titles", "titles.json"), "wb").write(get(TITLES.format(ref=a.opence_ref)))
    os.makedirs(a.voices, exist_ok=True)
    for name in dialog.VOICES:
        _, who, quality = name.split("-", 2)
        for ext in (".onnx", ".onnx.json"):
            dest = os.path.join(a.voices, name + ext)
            if not os.path.isfile(dest):
                open(dest, "wb").write(get(PIPER.format(who=who, quality=quality, name=name, ext=ext)))
        card = get(PIPER.format(who=who, quality=quality, name="MODEL_CARD", ext="")).decode()
        if "public domain" not in card.lower() or "finetuned" in card.lower():
            raise SystemExit(f"{name}: its MODEL_CARD no longer says public-domain data trained from scratch")
        open(os.path.join(a.voices, name + ".MODEL_CARD"), "w").write(card)
    print(f"fonts {', '.join(FONTS)}; titles.json; voices {', '.join(dialog.VOICES)}")


if __name__ == "__main__":
    main()
