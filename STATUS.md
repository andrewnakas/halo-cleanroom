# Halo: Combat Evolved clean room: status

## Now (2026-10-09, session 2)
- **PUBLISHED v0.2**: https://andrewnakas.github.io/halo-cleanroom/ (menu + 13 multiplayer maps, taint 0 failing);
  the live page was checked headless (boots to the main menu). Repo `andrewnakas/halo-cleanroom` (main = tools,
  gh-pages = site). `tools/publish_halo.sh` now refuses unless `D:/n64work/halo/taint_site.log` says `0 failing`
  and is newer than every staged map's build.
- **Machine memory comes and goes**: `WindowsTerminal.exe` (PID 25988) swings between 2 and 30 GB; while it is high,
  free commit is under 1 GB (even `import numpy` fails) and the page file fills C:. Heavy jobs run one at a time
  and are resumable; code-only work fills the gaps. Two jobs died to it and were rerun.
- **`clean/tags` is ahead of the published site and NOT taint-scanned yet** (every bitmap regenerated with the alpha
  outline, baked lightmaps, campaign tags added). Nothing is staged from it until a full scan prints `0 failing`.
- Owner decisions this session: **2-bit alpha outline** (SM64 rule) replaces the strict alpha class; campaign
  dialogue may be **transcribed to text** and voiced with Piper; campaign maps go into **extra Pages repos**
  (same origin); publish and keep pushing whatever passes taint.

## Done this session
- Engine/launcher (OpenCE `web`, commit f81d8f3d, built, checked headless with the real GPU at ~47 fps):
  - Levels download **on demand**: a map missing from the browser is fetched by the page while the game waits
    (no more "damaged disc" hang); the next campaign level is fetched ahead. Verified: `?level=a10` with only
    ui + bloodgulch stored downloads a10 and starts it.
  - Solo host no longer shows "could not agree on a host" (the room election is cancelled; alone and offline it
    ends as host).
  - Downloads stream piece by piece into OPFS with a hash per piece; maps are tracked per file (updates replace
    only changed maps); manifest entries can carry a `base` URL (map repos).
  - `?level=` starts under a player profile (saves, level progress); `game.test_script`, `?env=`, `?init=` hooks.
  - Keyboard: **1 or V switch weapons** (Tab is the scoreboard on web). `?fps=1` shows audio gaps.
- Tools: `extract_tags --add / --redo bitmaps` (598 alpha outlines kept in `spec/alpha2`), `generate` uses the
  outline, `hek.py` reads **every** kept tag through Invader's definitions (5218 of 5218), `build_maps.py`
  (extract / generate / build per map), `make_site.py --maps/--extra`, `cdp_shot.py` (no more lost shots, `--t0`).
- Assets (all verified on sheets and in Blood Gulch):
  - **Lightmaps are baked from the level's own geometry** (`bsp.py`: sun shadow map + sky light, numbers from the sky
    tag), carried on the kept 4x4 grid. Found on the way: unused lightmap texels are flat orange, which had tinted
    the old flat lighting; the lit colour is now solved against our own chart coverage.
  - **HUD from the kept outlines**: motion sensor, reticles, frames, ammo counter, message icons. **Shield and
    health bars fill** (the engine reads the fill ramp from brightness, the shape from alpha; it was the other way
    round). Text pieces stay re-typeset; hairline pieces keep their drawn briefs.
  - Effects, decals, foliage, sky ring and clouds keep their silhouettes; stains are no longer flowers.
  - **Level pictures** (menu thumbnails, map cards) are 3/4 renders of each level's geometry with our lighting.
- Campaign: **all ten levels extracted** into the dirty tree and the spec (9008 tags, 3751 images, 15834 sound
  permutations). Dialogue: `dialog.py` (dirty room: speech -> text only; clean room: Piper cast per character).

## Next (in order)
1. Running: bitmaps for the campaign tags (`generate --add --only bitmaps`), dialogue transcription (small.en; the
   cached medium.en model is incomplete and its download stalls).
2. `generate --only sounds` (all sounds, spoken lines from the text), `build_maps build campaign`.
3. Full taint scan -> 0 failing -> stage v0.3 (main site: menu + 13 MP + a10; map repos for the rest).
4. Browser check per level (loads, plays 60 s, `game_won` reaches the next level).
5. Practice pack for recording; remaining polish (camouflage / bump tables, galaxy, darker level pictures).

## Not done / still open
- Menu mouse pointer on web (menus are keyboard / pad only). Non-standard gamepad mappings. Per-level delete in
  the launcher. Audio gaps: the counter is high while a level loads (mixer idle); real gaps in play not judged yet.

## Pipeline (all under `games/halo/`, work dirs under `D:\n64work\halo\`)
| Step | Command | Output |
|---|---|---|
| Dirty: maps | `python -m games.halo.xiso_extract <xiso> D:/n64work/halo/dirty` | `dirty/maps` (24 maps, 1.86 GB) |
| Dirty: tags | `invader-extract -m dirty/maps -t dirty/tags -r dirty/maps/<map>.map` then `invader-bludgeon -T invalid-enums -T out-of-range -T invalid-indices -b "*"` + one lens flare index (`headlights scorpion` reflection 0 -> bitmap 0) | `dirty/tags` |
| Spec (kept facts) | `python -m games.halo.extract_tags dirty/tags spec` | `spec/tags` (kept tags + skeletons), `bitmaps.json`, `sounds.json` |
| Clean tags | `python -m games.halo.generate spec cc0 clean/tags [--only bitmaps --match <regex>] [--add]` | `clean/tags` |
| Maps | `invader-build -g xbox-ntsc -t clean/tags -m clean/maps "levels\ui\ui"` (and `levels\test\bloodgulch\bloodgulch`) | `clean/maps` |
| Taint | `python -m games.halo.taint dirty/tags clean/tags --index taint_index` | must print `0 failing` |
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

## Known gaps (asset side, from session 1; being worked through in "Next")
- Effect sprites are generic shapes; HUD message icons are plain shapes; waypoint arrow + "15m" over the motion
  sensor; level/map pictures are colour bands; lightmaps flat; camouflage / reference bump / P8 bumps smooth or
  flat; sky galaxy and ring dull; announcer plain Piper; no practice pack; gamepad not verified.

## For the morning
- Windows Terminal's memory swings to ~30 GB now and then (see above); restarting it would steady the machine.
- **HUD message icons** now come from the kept 2-bit outline, so the sheet shows the game's own pictograms and
  button letters as silhouettes (the rule you chose). Say so if you would rather have them redrawn from briefs.
- Play https://andrewnakas.github.io/halo-cleanroom/ (v0.2).
