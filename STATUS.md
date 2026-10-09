# Halo: Combat Evolved clean room: status

## Now (2026-10-09)
- **Web build runs the game**: OpenCE (fqlx's wasm port) built with emsdk 6.0.10; headless Chrome boots the
  main menu and plays Blood Gulch (first person, HUD, world) from **clean maps**.
- **Clean maps v0.1**: `ui.map` (9.3 MB) and `bloodgulch.map` (21.8 MB), built by Invader (`-g xbox-ntsc`) from
  kept tags + regenerated bitmaps (744 images), sounds (1098 permutations) and fonts (4).
- **Taint (v0.1 tags, 2026-10-09 05:0x): `2009 generated streams scanned against 2009 retail streams; 364 with
  short coincidental matches; 0 failing`.** Log: `D:/n64work/halo/taint.log`. The staged maps are those tags.
- Keyboard input checked headlessly (W walks forward); pregame lobby and HUD readable.
- **NOT PUBLISHED: BLOCKED on permission.** Creating the public repo was denied by Claude Code's auto-mode
  classifier ("Create Public Surface"). Everything is staged: site in `D:/n64work/halo/pages` (git, branch
  gh-pages, 36 MB), tools repo committed on `main`. **To publish, run `sh tools/publish_halo.sh`** (or tell
  the session to). The OpenCE source branch is already public: github.com/andrewnakas/OpenCE branch `web`.

## Pipeline (all under `games/halo/`, work dirs under `D:\n64work\halo\`)
| Step | Command | Output |
|---|---|---|
| Dirty: maps | `python -m games.halo.xiso_extract <xiso> D:/n64work/halo/dirty` | `dirty/maps` (24 maps, 1.86 GB) |
| Dirty: tags | `invader-extract -m dirty/maps -t dirty/tags -r dirty/maps/<map>.map` then `invader-bludgeon -T invalid-enums -T out-of-range -T invalid-indices -b "*"` + one lens flare index (`headlights scorpion` reflection 0 -> bitmap 0) | `dirty/tags` |
| Spec (kept facts) | `python -m games.halo.extract_tags dirty/tags spec` | `spec/tags` (kept tags + skeletons), `bitmaps.json`, `sounds.json` |
| Clean tags | `python -m games.halo.generate spec cc0 clean/tags [--only bitmaps --match <regex>]` | `clean/tags` |
| Maps | `invader-build -g xbox-ntsc -t clean/tags -m clean/maps "levels\ui\ui"` (and `levels\test\bloodgulch\bloodgulch`) | `clean/maps` |
| Taint | `python -m games.halo.taint dirty/tags clean/tags` | must print `0 failing` |
| Site | `python -m games.halo.make_site OpenCE/build/web/site clean/maps site_clean --version N` | `site_clean` |
| Look | `python ports/wasm/serve.py site_clean 8072`, `python ports/wasm/cdp_shot.py <out> --url "http://localhost:8072/index.html?auto=1&quick=host" --secs 60 --webgl`; sheets: `python -m games.halo.sheet <tags> out.png <regex>` | screenshots |

Web build: `powershell -File D:\n64work\halo\build_web.ps1` (configure `--release --web-clean --web-emcc ...emcc.exe`,
`ninja -j6 web`, log `build_web.log`).

## Decisions
- **Step 0 (Hynes):** mitchellhynes.com/halo has no source or license. Found **OpenCE PR #12** (fqlx): source-built
  WASM/WebGL2 port, CC0, live on Pages. Based the web port on it. It uses pthreads; its service worker supplies
  cross-origin isolation on GitHub Pages, so that is fine.
- OpenCE work tree `D:\n64work\halo\OpenCE`, branch `web` (fqlx branch + ours). Ours: `tools/web_build.py` moved to
  port.json sources, POSIX object paths, embedded assets, Discord stubs; `configure.py --web-clean` (no traced HUD
  redraws); launcher "Download clean maps" (`clean/maps.json`, SHA-256, OPFS), "Play Blood Gulch" button,
  `?auto=1[&quick=host]` for headless checks; `network.quick_play_map` (site: bloodgulch).
- **Kept facts (strict reading of the plan):** every tag that is not a bitmap, sound or font is kept (geometry,
  collision, scenario, scripts, numbers, strings, sprite rectangles, font metrics). Bitmaps keep only a 4x4
  colour grid per image + an **alpha class** (opaque/binary/gradient). Sounds keep length + a loudness outline
  (<= 32 points, 3 dB steps). Sound mouth data is zeroed.
  - **Question for the morning:** the plan says "alpha class" for Halo; SM64 kept a 2-bit alpha outline. With the
    outline, sprites/decals/foliage/HUD would keep their silhouettes. I stayed with the stricter rule. Say so if
    you want the 2-bit outline (one switch in `extract_tags.py`).
- Bitmaps: CC0 material (ambientCG) by tag name, tinted to the grid; UI and HUD drawn from code (`drawn.py`,
  `hud.py`), text re-set in Overpass / OpenCE-Regular; menu titles use upstream's text pictures (free font).
  Briefs came from one look at dirty contact sheets (what each picture is), not from pixels.
- Sounds: Kenney CC0 samples by class/name fitted to length and outline; announcer lines by Piper
  (`en_US-ryan-high`, placeholder) from the tag names.
- **Taint calibration** (logged because it differs from the N64 harness): same scanner (`cleanroom.taint`), but
  windows need >= 10 distinct bytes of 16 (default 6) and pixels fail at 64 B (16 texels) instead of 32 B,
  because against ~150M retail windows near-black gradients collide by chance and clean images are tinted to
  retail's own colours. Added an exact-stream check. Positive control (dirty vs dirty) fails 17 of 17.
- Upstream `port/assets/hud` (traced HUD redraws) left out of our wasm; fonts and titles kept.

## Known gaps (next)
- Function textures in `rasterizer/` (vector normalization, fog, glow) are only smooth grids: lighting and
  fog may look off; draw them from their formulas.
- Sprites without outlines: particles, decals, lens flares, foliage are soft blobs; HUD message icons are
  plain shapes; level/map pictures are colour bands (render them from the BSP).
- Main menu lists maps that are not built yet: only `ui` and `bloodgulch` exist. Next maps: a30, the rest of MP.
- Lightmaps are 4x4 grids per lightmap page (flat lighting).
- Meter fill direction (alpha ramp) is a guess; check shield/health drain in play.
- Voices: announcer is plain Piper; no practice pack yet.
- Quick play shows a "room could not agree on a host" toast when alone (public MQTT signalling).
- Gamepad input not verified (keyboard is).

## For the morning
- Run `sh tools/publish_halo.sh` to publish v0.1 (repo + Pages), or allow the session to.
- Look at `D:\n64work\halo\shots\clean*/` (menu, Blood Gulch) and the sheets `clean_ui_shell.png`, `clean_hud.png`.
- Answer the alpha question above.
- Disk: D: has ~36 GB free and falling (other sessions too).
