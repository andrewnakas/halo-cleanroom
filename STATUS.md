# Halo: Combat Evolved clean room: status

## Now
- Step 0 done, step 1 in progress (web build of OpenCE).
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

## Build
```
cd D:\n64work\halo\OpenCE
set EM_CACHE=D:/n64work/emcache
python configure.py --release --web-emcc D:/n64work/emsdk/upstream/emscripten/emcc.exe
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
- Drop the Xbox XISO into `D:\n64work\halo\`.
