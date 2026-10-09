#!/bin/sh
# waits for chain-all.sh, restarts the scratch server on the newest code, then re-reads
# chapter 1 with the model (off-panel speakers), re-voices it and renders lookie-09
cd /home/ejb/Forge/apps/panelforge || exit 1
until grep -q "== all done" docs/crew/logs/chain-all.log; do sleep 30; done
echo "== restart server $(date +%H:%M:%S)"
kill "$(cat docs/crew/scratch-8460.pid)" 2>/dev/null
i=0; while ss -ltnH "sport = :8460" | grep -q . && [ $i -lt 30 ]; do sleep 1; i=$((i+1)); done
nohup .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8460 >> docs/crew/logs/scratch-8460.log 2>&1 &
echo $! > docs/crew/scratch-8460.pid
i=0; until curl -sf localhost:8460/api/health >/dev/null || [ $i -ge 40 ]; do sleep 1; i=$((i+1)); done
echo "== chapter 1 from the model pass $(date +%H:%M:%S)"
.venv/bin/python tools/rebuild_chapter.py --port 8460 bad-born-blood 0001 --from llm --to timeline 2>&1 | grep --line-buffered -v "running [0-9]*%$"
echo "== render lookie-09 $(date +%H:%M:%S)"
.venv/bin/python tools/rebuild_chapter.py --port 8460 bad-born-blood 0001 --from render --to render --out lookie-09 2>&1 | grep --line-buffered -v "running [0-9]*%$"
echo "== after-chain done $(date +%H:%M:%S)"
