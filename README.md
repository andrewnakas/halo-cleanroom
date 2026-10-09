# Halo: Combat Evolved — clean-room web build

Play: https://andrewnakas.github.io/halo-cleanroom/

The game runs in the browser as WebAssembly, from the community decompilation
([OpenCE](https://github.com/OpenCommunityEdition/OpenCE), CC0; web port by fqlx, our branch:
[andrewnakas/OpenCE `web`](https://github.com/andrewnakas/OpenCE/tree/web)). The maps it downloads are
**clean-room maps**: level geometry, collision, scripts, tuning numbers and text are kept as facts; every
texture, sound, voice line and font glyph is made again from CC0/OFL sources or drawn from code.

- Textures: [ambientCG](https://ambientcg.com) materials (CC0) tinted to a 4x4 colour grid per image; menus
  and HUD drawn from code; text set in Overpass (OFL) and OpenCE-Regular (Newtown, public domain).
- Sounds: [Kenney](https://kenney.nl) packs (CC0) fitted to each sound's length and loudness outline; announcer
  lines are a synthetic placeholder voice (Piper).
- Sources are listed in `assets/LICENSES.csv`.
- No disc image, retail map, tag, pixel or sample is in this repository or on the site. A taint scan
  (`games/halo/taint.py`) compares every generated stream with every retail stream and must report
  `0 failing` before a release.
- You can also bring your own Xbox disc image: the page copies its maps into your browser's private storage;
  nothing is uploaded.

State: early. Maps so far: the menu (`ui`) and Blood Gulch. See `STATUS.md`.

## Layout

| Path | What |
|---|---|
| `games/halo/xiso_extract.py`, `extract_tags.py` | dirty room: disc image -> maps -> kept facts (spec) |
| `games/halo/generate.py`, `drawn.py`, `hud.py`, `functions.py` | clean room: spec + CC0 library -> clean tags |
| `games/halo/tags.py`, `codecs.py` | tag files, DXT and Xbox ADPCM codecs |
| `games/halo/taint.py` | taint scan |
| `games/halo/make_site.py` | site folder with `clean/maps.json` |
| `cleanroom/`, `ports/`, `docs/` | shared clean-room harness (from the N64 projects) |

Maps are built with [Invader](https://github.com/SnowyMouse/invader) (`invader-build -g xbox-ntsc`).

This project is not affiliated with Microsoft, Bungie or 343 Industries. Halo is a trademark of Microsoft.
