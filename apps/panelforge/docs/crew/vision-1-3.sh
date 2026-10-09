#!/bin/sh
# Emerson (02:05): speakers wrong in every way. Ask the picture about every
# line where two or more cast stand, chapters 1-3, one after the other (Jan).
# Must finish before revoice-all.sh reaches each chapter's voice step so the
# new speakers get their voices; revoice-all waits for tall-4-10 first.
cd /home/ejb/Forge/apps/panelforge || exit 1
for c in 0001 0002 0003; do
  echo "== $c vision-all $(date +%H:%M:%S)"
  j=$(curl -s -X POST http://127.0.0.1:8460/api/chapters/bad-born-blood/$c/script/llm -H 'Content-Type: application/json' -d '{"vision_only": true, "vision_all": true}' | python3 -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
  i=0
  while [ $i -lt 360 ]; do
    st=$(curl -s http://127.0.0.1:8460/api/jobs/$j | python3 -c "import json,sys;print(json.load(sys.stdin).get('state'))")
    case "$st" in done|failed|cancelled) break ;; esac
    sleep 10; i=$((i+1))
  done
  curl -s http://127.0.0.1:8460/api/jobs/$j | python3 -c "import json,sys;d=json.load(sys.stdin);print('   ', d.get('state'), d.get('result'))"
done
echo "== vision-1-3 done $(date +%H:%M:%S)"
