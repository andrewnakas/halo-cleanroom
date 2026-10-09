# Halo: Combat Evolved — clean-room web build

## THIS GAME OVERRIDES THE N64 TEMPLATE BELOW (owner-approved plan 2026-10-08)
Full plan: `C:\Users\andre\.claude\plans\dapper-booping-bee.md` section 1. Summary:
- **Engine:** fork `OpenCommunityEdition/OpenCE` (CC0 Halo CE Xbox decomp port; SDL3; OpenGL 4.5 or GLES3 via `--gles`; 32-bit; ninja + configure.py). Clone it to `D:\n64work\halo\OpenCE`.
- **Step 0:** look for the source of Mitchell Hynes' wasm build (mitchellhynes.com/halo; his X posts; OpenCE issues and PRs). If it is public and the license is compatible, base the port on it.
- **Step 1, web port (start now):** add `port/web` + a `ninja web` target using emcc (emsdk at `D:\n64work\emsdk`). SDL3 emscripten, GLES3 → WebGL2 (`-sMAX_WEBGL_VERSION=2 -sFULL_ES3`), no `-march=native`, C fallbacks for x86 intrinsics/asm, `emscripten_set_main_loop` or ASYNCIFY, `maps/` fetched into MEMFS and cached in IndexedDB. Avoid pthreads if possible (else coi-serviceworker on Pages).
- **Step 2, dirty room:** the owner is downloading the Xbox XISO and will drop it in `D:\n64work\halo\`. Until then write `STATUS.md: BLOCKED on XISO` for this step and keep working on step 1. `extract_tags` → JSON facts. Kept: BSP + collision, scenario scripts and placements, tag numeric data, model geometry, unicode strings. Coarse only: bitmap colour grid + alpha class; sound length/loudness outline.
- **Step 3, clean room:** bitmaps from CC0 textures (ambientCG, Poly Haven) chosen by coarse colour and material class, plus procedural detail; sounds from CC0 (Kenney, OGA CC0, freesound CC0-only) + Piper TTS for dialogue; rebuild `.map` files with Invader (`invader-build`, Xbox target or Custom Edition, which OpenCE loads). Record every CC0 source in `assets/LICENSES.csv`. Start with Blood Gulch, then a30 "Halo".
- **Publish:** `andrewnakas/halo-cleanroom` + Pages. Clean maps by default, plus a "BYO XISO" local mode. Taint scan 0 first. Never commit the XISO, extracted maps, or tags.
- Work/scratch dirs go on **D:** (`D:\n64work\halo`), not C:.

You are running **unattended overnight**. The user prompts once (decomp link, ROM path) and checks in the morning. Work autonomously: decide with the defaults below, log every decision in `STATUS.md`, and never stop to ask unless something is truly blocking (then write the question in STATUS.md and continue with anything else).

## Goal
A playable **web build** of Halo: Combat Evolved, built from the community decomp, where **every asset the decomp extracts from the ROM is regenerated** (clean room), published as `andrewnakas/halo-cleanroom` + GitHub Pages. Same result as Super Mario 64 (https://andrewnakas.github.io/sm64-cleanroom/) and Pilotwings 64.

## Priorities tonight (user's words: "get all the visuals and gameplay and images/sprites correct")
1. Game boots and is playable in the browser (keyboard + gamepad), audio engine working (no dropouts).
2. **Everything readable**: fonts, HUD, dialog, text inside textures (re-typeset).
3. **Faces, sprites, pictures correct**: eyes/mouths/portraits/icons/sprites via briefs (`cleanroom.gfx.facepaint`), illustrations via renders of the game's own geometry (`cleanroom.gfx.c_render`), HUD widgets drawn per state.
4. Textures: kept colour grid + alpha outline (default), better where it matters.
5. Voices: **placeholder** TTS character voices only; build the practice pack so the user can record in the morning. Do not spend long on voices.

## Pre-answered scope (same as SM64; do not ask)
- Keep as facts: decomp code/geometry/text, texture format+size+4x4 grid+2-bit alpha, sample length/rate/loops/coarse outline/median pitch, **note sequences** (melodies), demo inputs.
- Regenerate everything else. No retail pixels/samples in outputs. Taint scan must be 0 failing.
- **No voice cloning** of real actors, no models trained on retail audio (placeholders = Piper TTS, see cleanroom.voice.voices).
- Web route: see docs/DECOMP_PLAYBOOK.md §4. Prefer a PC port with Emscripten; otherwise **clean ROM + WASM N64 emulator**; N64Recomp+ports/wasm only as last resort. Decide within the first hour and log why.
- Publish when it boots, plays and taint passes: new public repo + gh-pages (gh CLI is logged in as andrewnakas). Push updates as you improve. Never publish dirty trees, dev builds, ROMs or retail clips.

## Where things are
- This folder: your repo. `cleanroom/` shared library (copy; extend freely here), `ports/`, `tools/`, `docs/DECOMP_PLAYBOOK.md` (**read first**, it is the checklist of traps), `docs/HARNESS.md` (PW64 lessons), `reference/sm64/` (the finished SM64 game module to copy patterns from: generate.py, drawn.py, facepaint briefs, paintings.py, level_render.py, voices).
- Work dirs: `C:/Users/andre/n64work/halo/` (pristine, dirty, clean, build). **E: is nearly full**: build on C:. emsdk: `E:/n64web/emsdk` (EM_CACHE=E:/n64web/emcache).
- Toolchain: `tools/setup_winbin.sh` (zig cc as gcc, clang as `as`, llvm-objcopy, hexdump, python3, make). IDO 5.3 native: `C:/Users/andre/n64work/idowin` (see PW64 `tools/idowin`); IDO 7.1 if needed from ido-static-recomp releases (Windows builds). Zig: `~/.local/zig-x86_64-windows-0.16.0`, LLVM: `~/.local/clang+llvm-23.1.2-x86_64-pc-windows-msvc`.
- Python 3.12 with numpy, scipy, librosa, pyworld, piper-tts (voices: `C:/Users/andre/n64work/piper_voices`), faster-whisper, av, websocket-client.
- Browser checks: `python ports/wasm/serve.py <site> <port>` + `python ports/wasm/headless_shot.py <out> --base http://localhost:<port>/index.html --secs 5,10 --query "keys=..." --webgl`; hangs: `ports/wasm/cdp_stack.py`. Page template with dev hooks: `ports/web/shell.html`.

## How to work (token-minimal)
- Scripts print one-screen summaries; background long jobs and wait for the notification; one contact sheet per question; fixes as patch lists / JSON briefs.
- Clone decomps with `-c core.autocrlf=false -c core.eol=lf`.
- Keep `STATUS.md` current: what works, decisions, what's next, and a short "for the morning" list (what to record, what to look at).
- Commit often (end commit messages with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`).

## ROM / decomp
- ROM: TBD (owner is downloading the Xbox XISO; will drop it in D:/n64work/halo/)
- Decomp: https://github.com/OpenCommunityEdition/OpenCE (CC0 decomp port)
