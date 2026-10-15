# Halo: Combat Evolved clean room: status

## 2026-10-14 evening: v0.6 PUBLISHED and checked live (sound)
- **Engine bug fixed (OpenCE web da715f3b):** the port's mixer decoded Xbox ADPCM wrongly (64 nibbles per block
  instead of header sample + 63 nibbles): a click every 1.45 ms block, worst in music. Proven with `?record=SECONDS`
  (the page records what it plays; `cdp_shot.py` keeps `REC` console lines whole): engine output went from 14.4
  clicks/s to 0.02/s (source file 0.0). Retail tags confirm header-first (smooth joins only read that way). Also:
  blend across packet joins, 128 ms audio lead with soft refill in the worklet, mixer starvation log.
- **Sounds (halo-cleanroom 13a555b):** music = 21 recorded CC0 tracks from OpenGameArt (`cc0/music/<style>/`,
  `SOURCES.json`, `assets/LICENSES.csv`; menu = Gregorian chant), one steady gain to the original's average
  loudness; no retail notes used (owner asked to copy melodies; declined: a cover of the score). Ambience = smooth
  synthesised wind/room tone. Effects: quiet band shaping (no noise fill, <= 12 dB lift) applied to each whole
  permutation chain (per-chunk shaping clicked at every 1.3 s join). Dialogue unchanged.
- Rejected by ear: CC0 SFX shaped as music (buzz), a numpy music synthesiser (sounded wrong).
- Taint `0 failing` (18:32). Live 20:16: manifest 0.6, a30 played from maps1, live menu recording 0 clicks in 25 s.

## 2026-10-14: launcher = one "Load into menu" button (live, checked)
- The owner could not load the site: a first visit waited for the service worker to cache the 6 MB shell
  before the page did anything (Pages served files in up to 15 s each, so a blank launcher for a minute+).
  Now the first worker activates at once and caches in the background; the page shows one big
  "Load into menu" button (fetches ui.map, starts the main menu); multiplayer, downloads, disc and settings sit
  in a collapsed section below. OpenCE `web` 25f8e834. Live check with a fresh profile: button ready at 4 s,
  click -> main menu (`D:/n64work/halo/shots/simple_live/`).

## HANDOFF 2026-10-13: v0.5 PUBLISHED and checked live
- Live 22:46: manifest 0.5; a30 (maps1) and c10 (maps2) pieces match the manifest; c10 downloaded and played 90 s
  from the live page, 0 error lines (`D:/n64work/halo/shots/live_v05/`). The owner ran the publish
  (`D:/n64work/halo/publish_v05.sh`: the first try got HTTP 408 on the maps1 push; a 1 GB `http.postBuffer` fixed it).
  Pages deploys of the 430-590 MB sites sat at "building" for ~20 min and then finished by themselves.
  The steps listed below as not done were all done.
- **What v0.5 is:** every sound follows a coarse band outline of its original (8 bands x <= 64 windows, 3 dB;
  `bands.py`). Loops, ambience and music use a smoothed outline and no added noise (the static the owner heard in
  `0.5-local2`); noise fill only in bands within 24 dB of the loudest. Launcher removes maps stored from an earlier
  clean version (OpenCE `web` commit cb36cd22).
- **Taint on the final tree:** `25638 generated streams scanned against 25638 retail streams; 13892 with short
  coincidental matches; 0 failing` (`D:/n64work/halo/taint_v05_full.log`, copied to `taint_site.log`, 20:36, newer
  than every map built 19:52). Four sounds needed reseeding on the way (`taint_reseed.json`): covydrop,
  light_rings, index (twice: seed 2). All were 33-49 B runs on the ADPCM decoder's fixed-step slew ramps at a
  sound's start, not content. Thresholds unchanged. `D:/n64work/halo/v05_chain.ps1` = reseed one sound -> scan it
  -> rebuild all -> full scan.
- **Staged:** `D:/n64work/halo/pages` (manifest 0.5, 15 maps, 441 MB), `pages_maps1` (587 MB), `pages_maps2`
  (596 MB). Local test root `D:/n64work/halo/stage_root` served on 8073.
- **Smoke (headless, real GPU, staged site):** a10, a30 (maps1), c10, d40 (maps2) download on demand and play 90 s
  with 0 error lines; Blood Gulch quick play runs. Sheet `D:/n64work/halo/shots/smoke_v05/sheet.png`. 7-24 fps
  (machine busy with other sessions).
- **Not done (auto mode denied git commit and publish in this session):**
  1. `cd /d/n64work/halo-cleanroom && git add games/halo/taint_reseed.json STATUS.md && git commit -m "v0.5: reseeds, status"`
  2. `SITE_MESSAGE="v0.5" sh /d/n64work/halo-cleanroom/tools/publish_halo.sh > /d/n64work/halo/publish_v05.log 2>&1`
  3. `cd /d/n64work/halo/OpenCE && git push mine web`
  4. Live check: manifest says 0.5, one campaign level downloads from each map repo.
- No Windows exe of OpenCE has been built here (`OpenCE/build/windows` holds only empty folders); the clean maps
  are plain Xbox `.map` files, so a native build could load `D:/n64work/halo/clean/maps` directly.

## Now (2026-10-09, end of session 2)
- **PUBLISHED v0.4**: https://andrewnakas.github.io/halo-cleanroom/ : menu, 13 multiplayer maps and the whole
  campaign (10 levels, downloaded as you reach them), taint 0 failing. Repos `andrewnakas/halo-cleanroom` (main =
  tools, gh-pages = site), `halo-cleanroom-maps1`, `halo-cleanroom-maps2` (campaign maps). `tools/publish_halo.sh`
  pushes all three and refuses unless `D:/n64work/halo/taint_site.log` says `0 failing` and is newer than every
  staged map's build.
- **Machine memory comes and goes**: `WindowsTerminal.exe` (PID 25988) swings between 2 and 30 GB; while it is high,
  free commit is under 1 GB (even `import numpy` fails) and the page file fills C:. Heavy jobs run one at a time
  and are resumable; code-only work fills the gaps. Two jobs died to it and were rerun.
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

## v0.3: PUBLISHED and checked live (2026-10-09 evening)
- https://andrewnakas.github.io/halo-cleanroom/ : wasm build + menu + 13 multiplayer maps + a10 (430 MB). Campaign
  maps a30 a50 b30 b40 in `andrewnakas/halo-cleanroom-maps1` and c10 c20 c40 d20 d40 in `-maps2` (same origin).
  Live check: the published page downloaded a30 from the maps1 repo (one network error, retried by itself) and
  played it (`D:/n64work/halo/shots/live_v03/`).
- **Taint: `25638 generated streams scanned against 25638 retail streams; 11898 with short coincidental matches;
  0 failing`** (`D:/n64work/halo/taint_site.log`). The first full scan had 2 failing by one byte each (a 65-byte run
  in one baked lightmap page, a 33-byte run in one wave sound: our own noise meeting a retail window by chance);
  lightmaps got grain, the sound is in `games/halo/taint_reseed.json`, everything was rebuilt and scanned again.
  Thresholds unchanged. Dirty-vs-dirty control: 26 of 27 streams fail.
- **Campaign from the main menu works**: Campaign -> name a profile -> difficulty -> a10 downloads -> plays. It used
  to stop the game ("unreachable"): four local prototypes had other types than their definitions, which link-time
  optimization turns into traps. Fixed; `tools/web_prototype_check.py` (OpenCE) lists such declarations.
- Story dialogue is spoken (1070 lines: level folders, cinematics, named characters; Piper cast). Combat chatter
  was still the murmur in v0.3.
- Gamepad: checked with a stubbed standard pad (left stick walks, right stick turns). A real pad was not tried.
- The taint scan is a partitioned join now (the campaign index is 15 GB); a full scan took 50 min to 3 h depending
  on how busy the disk was. It keeps a bucketed copy of the index from now on (sequential reads).

## v0.4: PUBLISHED and checked live (2026-10-09 night)
- Adds: **every transcribed line is spoken** (5228 lines: story + marines, sergeants, grunts; aliens without words
  keep the murmur), galaxy sky texture.
- Taint on the final tree: `25638 generated streams scanned against 25638 retail streams; 11850 with short
  coincidental matches; 0 failing` (`D:/n64work/halo/taint_site.log`); no tag changed between the build and the scan.
- Live check: manifest 0.4, a map piece of `-maps2` matches the manifest's hash, c10 downloaded and played from
  the published page (`D:/n64work/halo/shots/live_v04/`).
- Seen on the live site both times: the first attempt of a level download ends with "network error" and the
  retry (4 s later) succeeds. It heals itself; the cause was not looked into.

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

## Known gaps (asset side)
- Fixed this session: HUD shapes and meters, message icons, effect sprites, foliage, level pictures, lightmaps,
  palettized bump maps, sky ring and clouds, practice pack.
- Open: camouflage distortion and reference bump tables (smooth grids), the galaxy texture, announcer is plain Piper,
  effect sheets whose picture lives in the colour (no outline kept) are still shapes by name.

## For the morning
- Play https://andrewnakas.github.io/halo-cleanroom/ : Campaign from the menu (Enter/Space = A, Backspace/F = B,
  1 or V = switch weapon, Tab = scoreboard).
- **Record voices**: `D:/n64work/halo/practice_pack/<character>/` (cortana, keyes, chief, sarge, pilot, monitor,
  marine, grunt, crewman): `SCRIPT.txt` + `practice_<who>_call_and_response.wav` (local only, from your disc).
- **HUD message icons** come from the kept 2-bit outline, so the sheet shows the game's own pictograms and button
  letters as silhouettes (the rule you chose). Say so if you would rather have them redrawn from briefs.
- Windows Terminal's memory swings to ~30 GB now and then; restarting it would steady the machine.
- Look at `D:/n64work/halo/shots/smoke/campaign1.png`, `campaign2.png` and `D:/n64work/halo/shots/clean_hud2.png`,
  `clean_pics.png`.
