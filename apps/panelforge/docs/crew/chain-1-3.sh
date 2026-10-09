#!/bin/sh
# re-read chapters 1-3 with the new cleaner, then script -> model -> voice -> audio -> timeline
cd /home/ejb/Forge/apps/panelforge || exit 1
SD=/home/ejb/PanelForgeData/series/bad-born-blood
for c in 0001 0002 0003; do
  echo "== detect $c $(date +%H:%M:%S)"
  .venv/bin/python -m panelforge.subjob detect $SD/chapters/$c 2>&1 | grep -v "^PROGRESS" | tail -3
done
.venv/bin/python tools/renormalize.py bad-born-blood 0001 0002 0003 | tail -3
for c in 0001 0002 0003; do
  echo "== chain $c $(date +%H:%M:%S)"
  .venv/bin/python tools/rebuild_chapter.py --port 8460 bad-born-blood $c --from script --to timeline
done
echo "== all done $(date +%H:%M:%S)"
