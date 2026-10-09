#!/bin/sh
# re-read chapters 1-3 with the fixed classifier, rebuild them script -> model -> voice -> audio -> timeline,
# then re-read chapters 4-10 and re-clean their text (their scripts are rebuilt by the bulk run later)
cd /home/ejb/Forge/apps/panelforge || exit 1
SD=/home/ejb/PanelForgeData/series/bad-born-blood
for c in 0001 0002 0003; do
  echo "== detect $c $(date +%H:%M:%S)"
  .venv/bin/python -m panelforge.subjob detect $SD/chapters/$c 2>&1 | grep -v "^PROGRESS" | tail -2
done
for c in 0001 0002 0003; do
  echo "== chain $c $(date +%H:%M:%S)"
  .venv/bin/python tools/rebuild_chapter.py --port 8460 bad-born-blood $c --from script --to timeline 2>&1 | grep --line-buffered -v "running [0-9]*%$"
done
for c in 0004 0005 0006 0007 0008 0009 0010; do
  echo "== detect $c $(date +%H:%M:%S)"
  .venv/bin/python -m panelforge.subjob detect $SD/chapters/$c 2>&1 | grep -v "^PROGRESS" | tail -2
done
.venv/bin/python tools/renormalize.py bad-born-blood | tail -1
echo "== all done $(date +%H:%M:%S)"
