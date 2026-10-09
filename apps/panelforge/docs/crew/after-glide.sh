#!/bin/sh
# waits for no-ring.sh, then renders the six scroll films again so the shots
# with lines get the glide (22:30); unchanged shots come from the cache
cd /home/ejb/Forge/apps/panelforge || exit 1
p=$(cat docs/crew/no-ring.pid 2>/dev/null)
while [ -n "$p" ] && kill -0 "$p" 2>/dev/null; do sleep 15; done
for a in 16x9 9x16; do
  for c in 0001 0002 0003; do
    echo "== $c scroll-$a glide $(date +%H:%M:%S)"
    .venv/bin/python tools/scroll_render.py bad-born-blood "$c" scroll-$a 0 $(echo $a | tr x :)
  done
done
echo "== after-glide done $(date +%H:%M:%S)"
