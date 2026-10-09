#!/bin/sh
# 9:16 scroll films for chapters 4-10 (their 16:9 ones came from the bulk run)
cd /home/ejb/Forge/apps/panelforge || exit 1
for c in 0004 0005 0006 0007 0008 0009 0010; do
  echo "== $c scroll-9x16 $(date +%H:%M:%S)"
  .venv/bin/python tools/scroll_render.py bad-born-blood "$c" scroll-9x16 0 9:16
done
echo "== tall-4-10 done $(date +%H:%M:%S)"
