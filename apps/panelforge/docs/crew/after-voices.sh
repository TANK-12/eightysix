#!/bin/sh
# waits for after-glow.sh, then renders chapters 1-3 once more: the 42 lines
# moved from the narrator to their characters (tools/replay_llm.py, 20:00)
# were voiced after those renders started
cd /home/ejb/Forge/apps/panelforge || exit 1
p=$(cat docs/crew/after-glow.pid 2>/dev/null)
while [ -n "$p" ] && kill -0 "$p" 2>/dev/null; do sleep 15; done
for c in 0001 0002 0003; do
  echo "== $c scroll-16x9 final (moved thoughts) $(date +%H:%M:%S)"
  .venv/bin/python tools/scroll_render.py bad-born-blood "$c" scroll-16x9 0 16:9
done
echo "== after-voices done $(date +%H:%M:%S)"
