#!/bin/sh
# Cloudflare Pages build: copies only the site's own files to dist/.
# png/ (the icons, ~900 MB) and tools/ stay out: Cloudflare can't hold the icons,
# so icons.html loads them straight from the GitHub repo.
#
# Cloudflare Pages settings:  Build command: sh tools/cloudflare_build.sh
#                             Build output directory: dist
set -e
rm -rf dist
mkdir dist
cp *.html *.js *.json *.jsonl *.txt dist/
cp -r vendor dist/
