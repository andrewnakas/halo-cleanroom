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
- **Campaign: all ten levels are extracted, generated (bitmaps), built and PLAY in the browser** (headless check per
  level with the real GPU: load through `?level=`, on-demand download, cinematic skipped, 90 s of play, no error
  lines; shots in `D:/n64work/halo/shots/smoke/<level>/`, sheets `campaign1.png`, `campaign2.png`). a10 runs the cryo
  tutorial ("Use [stick] to look around"). Maps so far are silent in places: the campaign sounds are generated
  after the transcription.
- The "cinematic is stuck" / "slow motion" of session 1 was the test harness: a headless page turns `hidden` about
  20 s in and the game then idles. `cdp_shot.py` now keeps the page visible; the game itself was fine.
- Two repairs were needed on kept tags before Invader builds the levels (`build_maps.py repair`): lens-flare
  bitmap indices past the bitmap count, and Windows-1252 bytes in three script sources.
- Dialogue: `dialog.py` (dirty room: speech -> text only, small.en; clean room: Piper cast per character).
  The level scripts' own debug prints ("cortana: [radio] roger that...") show as green text in this build: free
  subtitles, and a second text source for the story lines.

## v0.3 (being scanned; staged in `pages`, `pages_maps1`, `pages_maps2`)
- Main site: wasm build + menu + 13 multiplayer maps + a10 (430 MB). Map repos: a30 a50 b30 b40 (565 MB) and
  c10 c20 c40 d20 d40 (572 MB), served from `/halo-cleanroom-maps1/clean/` and `-maps2`; checked locally with the
  three folders side by side (level download across the repos, next level fetched ahead).
- **Campaign from the main menu works**: Campaign -> name a profile -> difficulty -> a10 downloads -> plays. It used
  to stop the game ("unreachable"): four local prototypes had other types than their definitions, which link-time
  optimization turns into traps. Fixed, and `tools/web_prototype_check.py` (OpenCE) lists such declarations.
- Story dialogue is spoken (1070 lines: level folders, cinematics, named characters; Piper cast); combat chatter is
  still the murmur (transcription of ~3500 lines continues; v0.4).
- First full scan of the final tree: 25638 streams, **2 failing by one byte each** (a 65-byte run in one baked
  lightmap page, a 33-byte run in one wave sound: our own noise meeting a retail window by chance). Lightmaps now
  carry grain and the sound is listed in `games/halo/taint_reseed.json`; everything was rebuilt and the full scan is
  running again. Nothing is pushed until it prints `0 failing`.
- The taint scan is now a partitioned join (the campaign index is 15 GB in 197 chunks; the old scan would have run
  for hours). Dirty-vs-dirty control: 26 of 27 streams fail.

## Next
1. v0.3: scan -> `0 failing` -> `sh tools/publish_halo.sh` (three repos) -> live check.
2. v0.4: voiced combat chatter (after transcription), then the polish list.

## Not done / still open
- Menu mouse pointer on web (menus are keyboard / pad only). Non-standard gamepad mappings; a real gamepad was not
  tried. Per-level delete in the launcher. Camouflage / reference bump tables, galaxy texture, some dark level
  pictures. A full playthrough of each level (only the first 90 s were run). Frame rate under load was 8-10 fps in
  the checks (the machine was saturated by other jobs); 47-80 fps when it was not.

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
- Play https://andrewnakas.github.io/halo-cleanroom/ : Campaign from the menu (Enter/Space = A, Backspace/F = B,
  1 or V = switch weapon, Tab = scoreboard).
- **Record voices**: `D:
64work\halo\practice_pack\<character>\` (cortana, keyes, chief, sarge, pilot, monitor,
  marine, grunt, crewman): `SCRIPT.txt` + `practice_<who>_call_and_response.wav` (local only, from your disc).
- **HUD message icons** come from the kept 2-bit outline, so the sheet shows the game's own pictograms and button
  letters as silhouettes (the rule you chose). Say so if you would rather have them redrawn from briefs.
- Windows Terminal's memory swings to ~30 GB now and then; restarting it would steady the machine.
- Look at `D:
64work\halo\shots\smoke\campaign1.png`, `campaign2.png`, `clean_hud2.png`, `clean_pics.png`.
