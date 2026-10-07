#!/usr/bin/env bash
# Plays a bot script (tools/bot/<name>.json) in a real game window on the real GPU and saves its
# screenshots and report.json in the next numbered check-image folder, images/NNN-<name>/.
# Off-screen by default: the game runs inside a private headless mutter (GNOME's compositor) with one
# virtual monitor, on its own D-Bus, so nothing appears on the desktop and no sound plays.
# --visible opens the window on the desktop instead. --build plays the exported game
# (build/linux/eightysix.x86_64 from tools/export.sh, or the binary in $GAME_BIN) instead of the project folder.
# A game that stops writing its heartbeat for 30 s has stalled (seen now and then off screen,
# cause not found yet): its thread states go to stall.txt and the run is retried once in a new folder.
# Usage: tools/bot_run.sh <script name, res:// or absolute path> [--visible] [--name=label] [--timeout=S]
#                         [--hz=60] [--retries=1] [--preset=low|medium|high|ultra] [--size=1920x1080]
#                         [--build]
# Prints the folder on the last line. Exit 0 when the run finished with no errors.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT:-godot}"
if [ $# -lt 1 ]; then
	sed -n '2,9p' "$0"
	exit 2
fi
SCRIPT="$1"
shift
case "$SCRIPT" in
res://* | /*) ;;
*) SCRIPT="res://tools/bot/${SCRIPT%.json}.json" ;;
esac
SCRIPT_FILE="$SCRIPT"
[ "${SCRIPT#res://}" != "$SCRIPT" ] && SCRIPT_FILE="$ROOT/${SCRIPT#res://}"
if [ ! -f "$SCRIPT_FILE" ]; then
	echo "bot_run: no such script $SCRIPT" >&2
	exit 2
fi
ORIGINAL_ARGS=("$@")
VISIBLE=0
BUILD=0
RETRIES=1
STALL_S=30
NAME="$(basename "$SCRIPT" .json)"
TIMEOUT=240
SIZE="1920x1080"
# The virtual monitor's refresh. Runs present in mailbox mode (below), so it does not cap the frame
# rate. 120 and 240 stalled in early tries, before the FIFO stall was found; untested since.
HZ=60
EXTRA=()
for a in "$@"; do
	case "$a" in
	--visible) VISIBLE=1 ;;
	--build) BUILD=1 ;;
	--name=*) NAME="${a#--name=}" ;;
	--timeout=*) TIMEOUT="${a#--timeout=}" ;;
	--hz=*) HZ="${a#--hz=}" ;;
	--retries=*) RETRIES="${a#--retries=}" ;;
	--size=*)
		SIZE="${a#--size=}"
		EXTRA+=("$a")
		;;
	*) EXTRA+=("$a") ;;
	esac
done
NAME="$(printf '%s' "$NAME" | tr -c 'A-Za-z0-9_-' '-')"
# The exported game has no project folder and its pack leaves out tools/, so it gets the script
# as a file path.
PATH_ARGS=(--path "$ROOT")
if [ "$BUILD" = 1 ]; then
	GODOT="${GAME_BIN:-$ROOT/build/linux/eightysix.x86_64}"
	if [ ! -x "$GODOT" ]; then
		echo "bot_run: no build at $GODOT; run tools/export.sh first" >&2
		exit 2
	fi
	PATH_ARGS=()
	SCRIPT="$SCRIPT_FILE"
fi

mkdir -p "$ROOT/images"
LAST="$(find "$ROOT/images" -mindepth 1 -maxdepth 1 -type d -regex '.*/[0-9][0-9][0-9]-.*' -printf '%f\n' | sort | tail -1 | cut -c1-3)"
NEXT="$(printf '%03d' $((10#${LAST:-0} + 1)))"
OUT="$ROOT/images/$NEXT-$NAME"
mkdir -p "$OUT"

if [ "$BUILD" = 0 ] && [ ! -d "$ROOT/.godot/imported" ]; then
	"$GODOT" --headless --path "$ROOT" --import >/dev/null 2>&1
fi

GAME_PID=""
WD=""
cleanup() {
	if [ -n "$GAME_PID" ] && kill -0 "$GAME_PID" 2>/dev/null; then
		kill -CONT "$GAME_PID" 2>/dev/null
		kill "$GAME_PID" 2>/dev/null
		for _ in 1 2 3; do
			kill -0 "$GAME_PID" 2>/dev/null || break
			sleep 1
		done
		kill -0 "$GAME_PID" 2>/dev/null && kill -KILL "$GAME_PID" 2>/dev/null
	fi
	if [ -n "$WD" ]; then
		local mp
		mp="$(pgrep -f -- "[m]utter --headless --wayland --no-x11 --wayland-display=$WD( |$)")"
		[ -n "$mp" ] && kill $mp 2>/dev/null
	fi
}
trap cleanup EXIT

GAME_ARGS=("${PATH_ARGS[@]}" --audio-driver Dummy -- "--bot=$SCRIPT" "--out=$OUT" "${EXTRA[@]}")
if [ "$VISIBLE" = 1 ]; then
	"$GODOT" "${GAME_ARGS[@]}" >"$OUT/godot.log" 2>&1 &
	GAME_PID=$!
	WHERE="on screen"
else
	WD="eightysix-bots-$$"
	dbus-run-session -- mutter --headless --wayland --no-x11 --wayland-display="$WD" \
		--virtual-monitor "${SIZE}@${HZ}" >"$OUT/mutter.log" 2>&1 &
	for _ in $(seq 1 40); do
		[ -S "$XDG_RUNTIME_DIR/$WD" ] && break
		sleep 0.25
	done
	if [ ! -S "$XDG_RUNTIME_DIR/$WD" ]; then
		echo "bot_run: the off-screen compositor did not start (see $OUT/mutter.log); try --visible" >&2
		echo "$OUT"
		exit 1
	fi
	# Mailbox presentation: the game never waits on the headless compositor's vsync (FIFO waits
	# stalled about one run in three, 2026-09-30) and the frame rate is not held to its refresh.
	env -u DISPLAY WAYLAND_DISPLAY="$WD" MESA_VK_WSI_PRESENT_MODE=mailbox \
		"$GODOT" --display-driver wayland "${GAME_ARGS[@]}" >"$OUT/godot.log" 2>&1 &
	GAME_PID=$!
	WHERE="off screen, ${SIZE}@${HZ}"
fi
echo "bot_run: $NAME ($WHERE), output $OUT"

# Bounded wait for the report (or the game ending without one, or a stall).
DEADLINE=$((SECONDS + TIMEOUT))
STALLED=0
until [ -f "$OUT/report.json" ] || ! kill -0 "$GAME_PID" 2>/dev/null || [ $SECONDS -ge $DEADLINE ]; do
	sleep 1
	BEAT="$OUT/heartbeat.json"
	if [ -f "$BEAT" ] && [ $(($(date +%s) - $(stat -c %Y "$BEAT"))) -ge $STALL_S ]; then
		STALLED=1
		break
	fi
	if [ ! -f "$BEAT" ] && [ $SECONDS -ge $((STALL_S * 3)) ]; then
		STALLED=1
		break
	fi
done
if [ "$STALLED" = 1 ] && [ ! -f "$OUT/report.json" ]; then
	{
		echo "stalled at $(date +%T): no heartbeat for ${STALL_S}s"
		echo "last heartbeat: $(cat "$OUT/heartbeat.json" 2>/dev/null)"
		ps -o pid,stat,pcpu,etime,wchan:32,cmd -p "$GAME_PID"
		echo "threads (name state wait-channel):"
		for t in /proc/"$GAME_PID"/task/*; do
			printf '%s | %s | %s\n' "$(cat "$t/comm")" "$(sed 's/.*) //' "$t/stat" | cut -d' ' -f1)" "$(cat "$t/wchan" 2>/dev/null)"
		done | sort | uniq -c | sort -rn
		echo "compositor:"
		pgrep -fa -- "[m]utter --headless --wayland --no-x11 --wayland-display=$WD( |$)"
		pgrep -fa '[b]lender -b' | cut -c1-120
	} >"$OUT/stall.txt" 2>&1
	echo "bot_run: the game stalled; details in $OUT/stall.txt" >&2
	cleanup
	trap - EXIT
	if [ "$RETRIES" -gt 0 ]; then
		echo "bot_run: retrying once" >&2
		exec "$0" "$SCRIPT" "${ORIGINAL_ARGS[@]}" "--retries=$((RETRIES - 1))"
	fi
	echo "$OUT"
	exit 4
fi
if [ ! -f "$OUT/report.json" ]; then
	echo "bot_run: no report (game ended or ${TIMEOUT}s passed); log in $OUT/godot.log" >&2
	echo "$OUT"
	exit 1
fi
# The game quits itself after the report; under the headless compositor Godot can hang on exit,
# so give it a few seconds and then stop it (cleanup does that).
for _ in 1 2 3 4 5; do
	kill -0 "$GAME_PID" 2>/dev/null || break
	sleep 1
done
SHOTS="$(find "$OUT" -maxdepth 1 -name '*.png' | wc -l)"
ERRORS="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("errors", [])))' "$OUT/report.json")"
echo "bot_run: $SHOTS screenshots, $ERRORS errors"
echo "$OUT"
[ "$ERRORS" = 0 ]
