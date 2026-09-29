#!/usr/bin/env bash
# Builds the Linux release into build/linux/ (eightysix.x86_64 plus eightysix.pck) from the "Linux"
# preset in export_presets.cfg. Needs Godot's official 4.7.2 export templates; only the two Linux
# x86_64 files are used. Until they are installed this says so and exits 3.
# Usage: tools/export.sh [--debug]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT:-godot}"
VERSION="$("$GODOT" --version | sed -E 's/^([0-9]+\.[0-9]+(\.[0-9]+)?)\.([a-z]+).*/\1.\3/')"
TEMPLATES="${XDG_DATA_HOME:-$HOME/.local/share}/godot/export_templates/$VERSION"
MODE="release"
[ "${1:-}" = "--debug" ] && MODE="debug"
if [ ! -f "$TEMPLATES/linux_$MODE.x86_64" ]; then
	echo "export: no Godot export template at $TEMPLATES/linux_$MODE.x86_64" >&2
	echo "export: install the official $VERSION templates (Linux x86_64 files) first; see README" >&2
	exit 3
fi
mkdir -p "$ROOT/build/linux"
"$GODOT" --headless --path "$ROOT" "--export-$MODE" "Linux" "$ROOT/build/linux/eightysix.x86_64"
STATUS=$?
ls -la "$ROOT/build/linux"
exit $STATUS
