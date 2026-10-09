#!/bin/sh
# 9:16 scroll films for chapters 2-3 (chapter 1's is done), one after the other
cd /home/ejb/Forge/apps/panelforge || exit 1
for c in 0002 0003; do
  echo "== $c scroll-9x16 final $(date +%H:%M:%S)"
  .venv/bin/python tools/scroll_render.py bad-born-blood "$c" scroll-9x16 0 9:16
done
echo "== tall-films done $(date +%H:%M:%S)"
