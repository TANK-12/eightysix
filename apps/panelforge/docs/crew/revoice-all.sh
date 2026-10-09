#!/bin/sh
# Emerson's sound policy (02:20): dry voices, no auto sound effects, no auto
# music. Waits for tall-4-10.sh, then for each chapter 1-10: speaks every
# line again (the policy is applied at synthesis), then renders both scroll
# films. Uses the scratch server on 8460 for the voice job.
cd /home/ejb/Forge/apps/panelforge || exit 1
p=$(cat docs/crew/tall-4-10.pid 2>/dev/null)
while [ -n "$p" ] && kill -0 "$p" 2>/dev/null; do sleep 20; done
for c in 0001 0002 0003 0004 0005 0006 0007 0008 0009 0010; do
  echo "== $c voice (policy) $(date +%H:%M:%S)"
  j=$(curl -s -X POST http://127.0.0.1:8460/api/chapters/bad-born-blood/$c/voice -H 'Content-Type: application/json' -d '{}' | python3 -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
  i=0
  while [ $i -lt 240 ]; do
    st=$(curl -s http://127.0.0.1:8460/api/jobs/$j | python3 -c "import json,sys;print(json.load(sys.stdin).get('state'))")
    case "$st" in done|failed|cancelled) break ;; esac
    sleep 10; i=$((i+1))
  done
  echo "   voice job $j $st"
  for a in 16x9 9x16; do
    echo "== $c scroll-$a policy $(date +%H:%M:%S)"
    .venv/bin/python tools/scroll_render.py bad-born-blood "$c" scroll-$a 0 $(echo $a | tr x :)
  done
done
echo "== revoice-all done $(date +%H:%M:%S)"
