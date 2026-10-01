#!/usr/bin/env bash
# Plays Eighty Six, always up to date: rebuilds the game first if its source changed (a few seconds),
# then runs it (numbered versions are only saved by tools/builds.py save). The launcher and the hub call this.
# Usage: tools/play.sh                  the latest game
#        tools/play.sh --version NNN    a saved version (or: latest, previous); see tools/builds.py list
#        tools/play.sh --source         straight from the project folder (godot --path), no build
# Anything after "--" goes to the game.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/play.log"
echo "== $(date '+%F %T') play.sh $*" >>"$LOG"
MODE="auto"
WHICH=""
case "${1:-}" in
--version) MODE="version" WHICH="${2:-latest}" ; shift 2 ;;
--source) MODE="source" ; shift ;;
esac
[ "${1:-}" = "--" ] && shift
if [ "$MODE" = "source" ]; then
	exec godot --path "$ROOT" "$@" >>"$LOG" 2>&1
fi
if [ "$MODE" = "version" ]; then
	BIN="$(python3 "$ROOT/tools/builds.py" path "$WHICH" 2>>"$LOG")"
else
	BIN="$(python3 "$ROOT/tools/builds.py" ensure --notify 2>>"$LOG")"
fi
if [ -z "$BIN" ] || [ ! -x "$BIN" ]; then
	echo "play: no build to run, running from the project folder" >>"$LOG"
	exec godot --path "$ROOT" "$@" >>"$LOG" 2>&1
fi
echo "play: $BIN" >>"$LOG"
exec "$BIN" "$@" >>"$LOG" 2>&1
