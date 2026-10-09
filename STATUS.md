# Halo: Combat Evolved clean room: status

## Now
- Step 0 done. **Step 1 builds**: `ninja web` -> `build/web/site` (halo.wasm 7.3 MB). Headless Chrome
  shows the launcher with all checks green (threads, WebGL2 in worker, OPFS, memory).
  Gameplay cannot be tested until there are maps (XISO or clean maps).
- Launcher has a **"Download clean maps"** path: reads `clean/maps.json`
  (`{version, files:[{name,size,sha256}]}`), downloads `clean/*.map` into OPFS `maps/`, checks SHA-256,
  writes the `.complete` marker; only `ui.map` is required to start. BYO XISO import unchanged.
- Clean-room tools ready (games/halo): `xiso_extract.py` (dirty: XDVDFS -> maps/), `codecs.py`
  (DXT1/3/5 + Xbox ADPCM encode/decode, self-test), `fetch_cc0.py` (ambientCG CC0 library ->
  `D:\n64work\halo\cc0\textures`, rows in `assets/LICENSES.csv`).
- Step 2 (dirty room): **BLOCKED on XISO** (owner drops it in `D:\n64work\halo\`).

## Decisions (2026-10-08)
- **Step 0 (Hynes):** mitchellhynes.com/halo has no source link or license; not usable.
  Found instead **OpenCE PR #12** by fqlx (Ben Burns): source-built WASM/WebGL2 port,
  branch `fqlx/browser-webgl-stream-batching` of `fqlx/halo-ce-universal`, CC0 (same LICENSE.md),
  live at fqlx.github.io/halo-ce-universal. **Base the web port on it** (plan step 0 rule).
  - Its runtime: game in a Web Worker, pthreads + `PROXY_TO_PTHREAD`, WASMFS + OPFS,
    WebGL2 via OffscreenCanvas, service worker for COOP/COEP (works on GitHub Pages),
    XISO import in-page (`xiso-worker.js`), maps cached in OPFS. Our plan's "avoid pthreads"
    is moot: its sw.js already supplies cross-origin isolation on Pages.
  - Also seen: PR #3 (web plan + XISO import, no build), PR #64 (Apple, reuses #12).
- Work tree: `D:\n64work\halo\OpenCE`, branch `web` = fqlx branch + our fixes.
  Merge base with OpenCE main is 284 commits behind; rebase later once it runs.
- emsdk `D:\n64work\emsdk` is 6.0.10 = exactly fqlx's CI version.
- Fixes so far: `tools/web_build.py` used the old `sln.projects` API -> port.json
  `game_sources()`; object paths forced to `/` (emcc reads rsp backslashes as escapes);
  configure with `--web-emcc .../emcc.exe` (no emcc.bat in this emsdk).
- Map builder: Invader 0.55.0 (GPL tool, output untainted) in `D:\n64work\halo\tools\invader`;
  `invader-build -g xbox-ntsc` builds Xbox cache files, so clean maps can target the native
  Xbox format the decomp loads.

- Upstream `port/assets/hud` = traced redraws of retail HUD sheets: **left out of the clean build**
  via new `configure.py --web-clean` (embeds the 35 re-typeset titles + fonts only; we draw our own HUD); they are CRC-gated to retail pixels anyway. `port/assets/fonts`
  (Overpass OFL, Newtown PD) are clean: keep, they draw all text at display resolution.
- Clean bitmaps/sounds: rewrite the pixel/sample blobs of the extracted tags in the tag's own format
  (codecs.py) and keep every other field, rather than rebuilding through invader-bitmap colour plates.

## Build
```
cd D:\n64work\halo\OpenCE
set EM_CACHE=D:/n64work/emcache
python configure.py --release --web-clean --web-emcc D:/n64work/emsdk/upstream/emscripten/emcc.exe
ninja -j6 web      (needs Git usr\bin on PATH for cp)
```
Output: `build/web/site`.

## Clean-room plan (after XISO)
1. Dirty: OpenCE/xiso extract `maps/` -> `invader-extract` tags (dirty, never committed).
2. Facts: geometry/collision/scenario/scripts/numerics/strings kept; bitmaps -> 4x4 grid + alpha
   class; sounds -> length/loudness outline.
3. Clean: rewrite tags: bitmaps from CC0 (ambientCG/Poly Haven) + procedural via `invader-bitmap`,
   sounds from CC0 + Piper via `invader-sound`, fonts from OFL/CC0 via `invader-font`,
   then `invader-build -g xbox-ntsc`. Blood Gulch first, then a30.
4. Site: "Play (clean maps)" downloads our maps into OPFS; "BYO XISO" keeps fqlx's import.

## For the morning
- The CC0 texture fetch (`python -m games.halo.fetch_cc0 D:/n64work/halo/cc0/textures`) was stopped by
  Claude Code under low system memory; not restarted automatically. It resumes where it stopped.
- Drop the Xbox XISO into `D:\n64work\halo\`.
