# Halo: Combat Evolved — clean-room web build

Play: https://andrewnakas.github.io/halo-cleanroom/

The game runs in the browser as WebAssembly, from the community decompilation
([OpenCE](https://github.com/OpenCommunityEdition/OpenCE), CC0; web port by fqlx, our branch:
[andrewnakas/OpenCE `web`](https://github.com/andrewnakas/OpenCE/tree/web)). The maps it downloads are
**clean-room maps**: level geometry, collision, scripts, tuning numbers and text are kept as facts; every
texture, sound, voice line and font glyph is made again from CC0/OFL sources or drawn from code.

- Textures: [ambientCG](https://ambientcg.com) materials (CC0) tinted to a 4x4 colour grid per image, inside a
  2-bit alpha outline where the image has one; menus drawn from code; text set in Overpass (OFL) and
  OpenCE-Regular (Newtown, public domain).
- Lighting: lightmaps are baked here from each level's own geometry and the sky's light directions.
- Menu pictures of the levels are renders of that geometry.
- Sounds: [Kenney](https://kenney.nl) packs (CC0) fitted to each sound's length and loudness outline.
- Voices: the spoken lines are kept as text only (transcribed) and said again by synthetic placeholder voices
  (Piper). No performer is cloned and nothing is trained on the game's audio.
- Sources are listed in `assets/LICENSES.csv`.
- No disc image, retail map, tag, pixel or sample is in this repository or on the site. A taint scan
  (`games/halo/taint.py`) compares every generated stream with every retail stream and must report
  `0 failing` before a release.
- You can also bring your own Xbox disc image: the page copies its maps into your browser's private storage;
  nothing is uploaded.

State: the menu, the 13 multiplayer maps and the 10 campaign levels (levels download as you reach them; the later
ones are served from `halo-cleanroom-maps1` and `-maps2`). See `STATUS.md`.

## Layout

| Path | What |
|---|---|
| `games/halo/xiso_extract.py`, `extract_tags.py` | dirty room: disc image -> maps -> kept facts (spec) |
| `games/halo/generate.py`, `drawn.py`, `hud.py`, `effects.py`, `functions.py` | clean room: spec + CC0 library -> clean tags |
| `games/halo/hek.py`, `bsp.py` | any kept tag through tag definitions; level geometry, baked lightmaps, level pictures |
| `games/halo/dialog.py`, `practice.py` | spoken lines: text out of the dirty room, placeholder voices; recording pack |
| `games/halo/build_maps.py`, `smoke.py` | per-map driver (Invader); browser check of campaign levels |
| `games/halo/tags.py`, `codecs.py` | tag files, DXT and Xbox ADPCM codecs |
| `games/halo/taint.py` | taint scan |
| `games/halo/make_site.py` | site folder with `clean/maps.json` |
| `cleanroom/`, `ports/`, `docs/` | shared clean-room harness (from the N64 projects) |

Maps are built with [Invader](https://github.com/SnowyMouse/invader) (`invader-build -g xbox-ntsc`).

This project is not affiliated with Microsoft, Bungie or 343 Industries. Halo is a trademark of Microsoft.
