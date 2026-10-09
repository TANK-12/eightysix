#!/bin/sh
# waits for after-voices.sh, then renders chapters 1-2 again with the resting
# scroll (the window holds on each balloon while its line plays, 20:18);
# chapter 3 already gets it (its render starts after the change)
cd /home/ejb/Forge/apps/panelforge || exit 1
p=$(cat docs/crew/after-voices.pid 2>/dev/null)
while [ -n "$p" ] && kill -0 "$p" 2>/dev/null; do sleep 15; done
for c in 0001 0002; do
  echo "== $c scroll-16x9 resting scroll $(date +%H:%M:%S)"
  .venv/bin/python tools/scroll_render.py bad-born-blood "$c" scroll-16x9 0 16:9
done
echo "== after-rest done $(date +%H:%M:%S)"
