#!/bin/sh
# Emerson (21:47): "yellow boxes around the text" -- the ring round the spoken
# balloon is off by default now (style version 2, so no cached clip with it is reused); every scroll film again without it
cd /home/ejb/Forge/apps/panelforge || exit 1
for c in 0001 0002 0003; do
  echo "== $c scroll-16x9 no ring $(date +%H:%M:%S)"
  .venv/bin/python tools/scroll_render.py bad-born-blood "$c" scroll-16x9 0 16:9
done
for c in 0001 0002 0003; do
  echo "== $c scroll-9x16 no ring $(date +%H:%M:%S)"
  .venv/bin/python tools/scroll_render.py bad-born-blood "$c" scroll-9x16 0 9:16
done
echo "== no-ring done $(date +%H:%M:%S)"
