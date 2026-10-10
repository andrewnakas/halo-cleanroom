#!/bin/sh
# Publish the Halo clean room: the tools repo (main) and the staged sites (gh-pages):
#   D:/n64work/halo/pages        -> andrewnakas/halo-cleanroom        (the game: menu, multiplayer, first level)
#   D:/n64work/halo/pages_maps1  -> andrewnakas/halo-cleanroom-maps1  (campaign maps)
#   D:/n64work/halo/pages_maps2  -> andrewnakas/halo-cleanroom-maps2  (campaign maps)
# Run only after `python -m games.halo.taint dirty/tags clean/tags --index taint_index` printed
# "0 failing" for the tags the staged maps were built from; its output is the scan log.
# It also runs the licence gate (games.halo.license_audit): every shipped asset CC0 or public domain.
set -e
WORK=/d/n64work/halo
# Refuse unless the scan log says 0 failing and is newer than every built map that is staged
# (scan log: TAINT_LOG, default taint_site.log).
LOG=${TAINT_LOG:-$WORK/taint_site.log}
grep -q "; 0 failing" "$LOG" || { echo "publish: $LOG does not say 0 failing"; exit 1; }
for site in pages pages_maps1 pages_maps2; do
  [ -d "$WORK/$site/clean" ] || continue
  for f in "$WORK/$site"/clean/*.map "$WORK/$site"/clean/*.part0; do
    [ -e "$f" ] || continue
    n=$(basename "$f"); n=${n%.part0}
    src=$WORK/clean/maps/$n
    if [ ! -e "$src" ] || [ "$src" -nt "$LOG" ]; then
      echo "publish: $n was built after $LOG (scan again)"; exit 1
    fi
  done
  if [ -n "$(find "$WORK/$site" -name .git -prune -o -type f \( -iname '*DIRTY*' -o -iname '*.iso' \) -print | head -1)" ]; then
    echo "publish: dirty files in $site"; exit 1
  fi
done

cd "$(dirname "$0")/.."
for site in pages pages_maps1 pages_maps2; do
  [ -d "$WORK/$site" ] || continue
  python -m games.halo.license_audit "$WORK/clean" "$WORK/$site" || { echo "publish: licence audit failed for $site"; exit 1; }
done
REPO=andrewnakas/halo-cleanroom
gh repo view $REPO >/dev/null 2>&1 || gh repo create $REPO --public \
  --description "Halo: Combat Evolved in the browser (WebAssembly) with clean-room maps: CC0 textures and sounds"
git remote get-url origin >/dev/null 2>&1 || git remote add origin https://github.com/$REPO.git
git push -u origin main

# each site is one fresh commit (no history of old maps), force-pushed to gh-pages,
# under this repository's git identity (a fresh `git init` has none)
NAME=$(git config user.name); EMAIL=$(git config user.email)
push_site() {
  dir=$WORK/$1; repo=$2; what=$3
  [ -d "$dir/clean" ] || return 0
  gh repo view "$repo" >/dev/null 2>&1 || gh repo create "$repo" --public --description "$what"
  cd "$dir"
  rm -rf .git
  git init -q -b gh-pages
  touch .nojekyll
  git add -A
  git -c user.name="$NAME" -c user.email="$EMAIL" commit -q -m "${SITE_MESSAGE:-Site}: taint 0 failing"
  git remote add origin "https://github.com/$repo.git"
  git push -q -f origin gh-pages
  gh api -X POST "repos/$repo/pages" -f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null 2>&1 || true
  echo "pushed $1 -> $repo ($(du -sh --exclude=.git . | cut -f1))"
}
# the map repos first: the game's manifest points at them
push_site pages_maps1 andrewnakas/halo-cleanroom-maps1 "Clean-room campaign maps for andrewnakas.github.io/halo-cleanroom (part 1)"
push_site pages_maps2 andrewnakas/halo-cleanroom-maps2 "Clean-room campaign maps for andrewnakas.github.io/halo-cleanroom (part 2)"
push_site pages $REPO "Halo: Combat Evolved in the browser (WebAssembly) with clean-room maps: CC0 textures and sounds"
echo "https://andrewnakas.github.io/halo-cleanroom/"
