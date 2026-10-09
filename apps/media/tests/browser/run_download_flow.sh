#!/usr/bin/env bash
# Click through Media's Download tab in headless Chrome (Flatpak).
#
#   tests/browser/run_download_flow.sh          # fake yt-dlp, no network
#   tests/browser/run_download_flow.sh --real   # real yt-dlp, 19 s public video
#
# Starts its own Media on a free port with a scratch data folder, serves
# download_flow.html from a copy of shared/, prints PASS/FAIL lines, and
# stops the server. Exit code = number of failures.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$(cd "$HERE/../.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/media-flow.XXXXXX")"
mkdir -p "$TMP/shared" "$TMP/bin" "$TMP/out"
cp "$APP"/../../shared/*.js "$APP"/../../shared/*.css "$TMP/shared/"
cp "$HERE/download_flow.html" "$TMP/shared/"

URL="https://www.youtube.com/watch?v=abc123"
if [ "${1:-}" = "--real" ]; then
  URL="https://www.youtube.com/watch?v=jNQXAC9IVRw"
else
  "$APP/.venv/bin/python" -c "
import re, sys
s = open('$APP/tests/test_downloader.py').read()
sys.stdout.write(re.search(r'FAKE_YTDLP = r\"\"\"(.*?)\"\"\"', s, re.S).group(1))" > "$TMP/bin/yt-dlp"
  chmod +x "$TMP/bin/yt-dlp"
fi

PORT="$("$APP/.venv/bin/python" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
(cd "$APP" && PATH="$TMP/bin:$PATH" FORGE_SHARED_DIR="$TMP/shared" FORGE_MEDIA_DATA="$TMP/data" \
  exec .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port "$PORT" >"$TMP/server.log" 2>&1) &
PID=$!
trap 'kill $PID 2>/dev/null; rm -rf "$TMP"' EXIT
for _ in $(seq 60); do curl -s -o /dev/null "http://127.0.0.1:$PORT/api/settings" && break; sleep 0.5; done

lines="$(flatpak run --share=network --filesystem="$TMP" --command=/app/extra/google-chrome com.google.Chrome \
  --headless=new --disable-gpu --no-sandbox --virtual-time-budget=90000 --dump-dom \
  "http://127.0.0.1:$PORT/shared/download_flow.html?u=$URL&dir=$TMP/out" 2>/dev/null \
  | sed -n '/<pre id=/,/<\/pre>/p' | grep -o '\(PASS\|FAIL\) :: .*')"
if [ -z "$lines" ]; then
  echo "FAIL :: the page reported nothing (did not load, or its script threw)"
  exit 1
fi
echo "$lines"
ls "$TMP/out"
exit "$(printf '%s\n' "$lines" | grep -c '^FAIL')"
