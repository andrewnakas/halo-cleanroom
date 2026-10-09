#!/bin/sh
# Publish the Halo clean room: the tools repo (main) and the staged site (gh-pages).
# Run only after `python -m games.halo.taint dirty/tags clean/tags` printed "0 failing"
# for the tags the staged maps were built from (STATUS.md records the run).
set -e
REPO=andrewnakas/halo-cleanroom
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
