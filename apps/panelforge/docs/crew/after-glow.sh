#!/bin/sh
# waits for the chapter-1 glow render (PID in scroll-render.pid), then renders
# chapters 1-3 scroll films again with the new music plan (4-8 segments a
# chapter instead of 50-95) and the glow
cd /home/ejb/Forge/apps/panelforge || exit 1
p=$(cat docs/crew/scroll-render.pid 2>/dev/null)
while [ -n "$p" ] && kill -0 "$p" 2>/dev/null; do sleep 10; done
for c in 0001 0002 0003; do
  echo "== $c scroll-16x9 music+glow $(date +%H:%M:%S)"
  .venv/bin/python tools/scroll_render.py bad-born-blood "$c" scroll-16x9 0 16:9
done
echo "== after-glow done $(date +%H:%M:%S)"
