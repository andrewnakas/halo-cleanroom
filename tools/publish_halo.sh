#!/bin/sh
# Publish the Halo clean room: the tools repo (main) and the staged site (gh-pages).
# Run only after `python -m games.halo.taint dirty/tags clean/tags` printed "0 failing"
# for the tags the staged maps were built from (STATUS.md records the run).
set -e
REPO=andrewnakas/halo-cleanroom
# Refuse unless the scan log says 0 failing and is newer than every staged map and every
# generated tag the maps could contain (scan log: TAINT_LOG, default taint_site.log).
LOG=${TAINT_LOG:-/d/n64work/halo/taint_site.log}
grep -q "; 0 failing" "$LOG" || { echo "publish: $LOG does not say 0 failing"; exit 1; }
for f in /d/n64work/halo/pages/clean/*.map /d/n64work/halo/pages/clean/*.part0; do
  [ -e "$f" ] || continue
  n=$(basename "$f"); n=${n%.part0}
  src=/d/n64work/halo/clean/maps/$n
  if [ ! -e "$src" ] || [ "$src" -nt "$LOG" ]; then
    echo "publish: $n was built after $LOG (scan again)"; exit 1
  fi
done
if [ -n "$(find /d/n64work/halo/pages -name .git -prune -o -type f \( -iname '*DIRTY*' -o -iname '*.iso' \) -print | head -1)" ]; then
  echo "publish: dirty files in the staged site"; exit 1
fi
cd "$(dirname "$0")/.."
gh repo view $REPO >/dev/null 2>&1 || gh repo create $REPO --public \
  --description "Halo: Combat Evolved in the browser (WebAssembly) with clean-room maps: CC0 textures and sounds"
git remote get-url origin >/dev/null 2>&1 || git remote add origin https://github.com/$REPO.git
git push -u origin main
cd /d/n64work/halo/pages
git remote get-url origin >/dev/null 2>&1 || git remote add origin https://github.com/$REPO.git
git push -f origin gh-pages
gh api -X POST repos/$REPO/pages -f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null 2>&1 || true
echo "https://andrewnakas.github.io/halo-cleanroom/"
