#!/usr/bin/env bash
# Runs the game's tests headless (no window) and writes logs/tests-last.json.
# Usage: tools/run_tests.sh [name filter]     e.g. tools/run_tests.sh test_settings
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT:-godot}"
if [ ! -d "$ROOT/.godot/imported" ]; then
	"$GODOT" --headless --path "$ROOT" --import >/dev/null 2>&1
fi
# --fixed-fps 120: every frame advances exactly one 1/120 s physics tick and headless runs them as
# fast as the CPU allows, so physics tests step exactly like the game (no time_scale tricks).
exec "$GODOT" --headless --fixed-fps 120 --path "$ROOT" res://tests/runner.tscn -- "$@"
