#!/bin/sh
# detect + analyze for a list of chapters, one after another, on the scratch server
cd /home/ejb/Forge/apps/panelforge || exit 1
for c in "$@"; do
  .venv/bin/python tools/rebuild_chapter.py --port 8460 bad-born-blood "$c" --from detect --to analyze > "docs/crew/logs/rebuild-$c.log" 2>&1
done
