#!/usr/bin/env bash
# One export into build/<platform>/ (default linux) from the preset named in tools/platforms.json.
# Needs Godot's official export templates for that platform; until they are installed this says so
# and exits 3. tools/play.sh and tools/builds.py share call the same code.
# Usage: tools/export.sh [linux|windows|macos] [--debug]
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM="linux"
case "${1:-}" in
linux | windows | macos) PLATFORM="$1" ; shift ;;
esac
python3 "$ROOT/tools/builds.py" export "$PLATFORM" "$@"
STATUS=$?
ls -la "$ROOT/build/$PLATFORM" 2>/dev/null
exit $STATUS
