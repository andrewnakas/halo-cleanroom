"""Browser check of campaign levels: each is started through ?level= (which downloads it on
demand), played for a while with scripted keys, and summarised in one line.

    python -m games.halo.smoke <site url> <out dir> a10 a30 ... [--secs 45,90] [--next]

--next adds `game_won` after the last screenshot and waits for the following level to load
(the transition, with its on-demand download). The site must be served already
(python ports/wasm/serve.py <site> 8072).
"""
import os
import re
import subprocess
import sys
import urllib.parse

ORDER = ["a10", "a30", "a50", "b30", "b40", "c10", "c20", "c40", "d20", "d40"]


def main():
    args = sys.argv[1:]
    secs = args[args.index("--secs") + 1] if "--secs" in args else "45,90"
    follow = "--next" in args
    base, out = args[0], args[1]
    levels = [a for a in args[2:] if a in ORDER]
    last = max(float(s) for s in secs.split(","))
    for level in levels:
        script = "2:cheat_deathless_player 1"
        nxt = ORDER[ORDER.index(level) + 1] if follow and level != ORDER[-1] else None
        if nxt:
            script += f";{int(last) + 5}:game_won"
        query = urllib.parse.urlencode({"auto": 1, "menu": 1, "level": level, "fps": 1,
                                        "env": "HALO_TEST_SCRIPT=" + script})
        folder = os.path.join(out, level)
        shots = secs + (f",{int(last) + 60}" if nxt else "")
        keys = ",".join(f"Enter@{t}" for t in (12, 20, 28, 36)) + f",KeyW@{int(last) - 12}-{int(last) - 4}"
        run = subprocess.run([sys.executable, "ports/wasm/cdp_shot.py", folder, "--url", f"{base}?{query}",
                              "--t0", f"map {level}: downloaded", "--secs", shots, "--keys", keys,
                              "--port", "9483"], capture_output=True, text=True)
        log = open(os.path.join(folder, "console.txt"), encoding="utf-8", errors="replace").read()
        bad = len(re.findall(r"cannot compile|EXCEPTION|assert|Aborted|The game stopped", log))
        fetched = re.findall(r"map (\w+): downloaded", log)
        loading = re.findall(r"map (\w+): loading", log)
        print(f"{level}: {run.stdout.strip().splitlines()[-1] if run.stdout.strip() else run.stderr.strip()[-120:]}; "
              f"maps fetched {fetched}; {bad} error lines" + (f"; next {'loading seen' if nxt in loading else 'NOT LOADED'}" if nxt else ""))


if __name__ == "__main__":
    main()
