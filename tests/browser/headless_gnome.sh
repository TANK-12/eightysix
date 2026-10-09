#!/usr/bin/env bash
# A private, headless GNOME Shell for checks that need a real, shown GL window
# (task 63, 2026-10-07). WebKitGTK only paints, and so only shows a stuck
# compositor, in a window a compositor really presents; headless Chrome and a
# window that is never shown cannot. It has its own runtime dir, session bus,
# config, data and cache dirs, so it never touches Emerson's desktop.
#
#   tests/browser/headless_gnome.sh start          # 3072x1728 (his screen)
#   tests/browser/headless_gnome.sh run <command...>
#   tests/browser/headless_gnome.sh stop
#
# GNOME_RIG (default /tmp/forge-gnome-rig) is where it lives, GNOME_RIG_SIZE
# (WxH) the virtual monitor. It uses the GPU, so post on the crew board first.
set -u
RIG="${GNOME_RIG:-/tmp/forge-gnome-rig}"
SIZE="${GNOME_RIG_SIZE:-3072x1728}"
SOCKET=forge-rig-wl

running() { [ -S "$RIG/run/$SOCKET" ] && [ -s "$RIG/bus" ]; }

case "${1:-}" in
start)
  if running; then echo "already running in $RIG"; exit 0; fi
  mkdir -p "$RIG/run" "$RIG/data" "$RIG/config" "$RIG/cache" && chmod 700 "$RIG/run"
  : > "$RIG/bus"
  XDG_RUNTIME_DIR="$RIG/run" XDG_DATA_HOME="$RIG/data" XDG_CONFIG_HOME="$RIG/config" \
    XDG_CACHE_HOME="$RIG/cache" setsid env -u DISPLAY -u WAYLAND_DISPLAY dbus-run-session -- bash -c '
      gsettings set org.gnome.shell welcome-dialog-last-shown-version "999"
      echo "$DBUS_SESSION_BUS_ADDRESS" > "$1/bus"
      exec gnome-shell --headless --no-x11 --wayland-display "$2" --virtual-monitor "$3" --mode=user' \
    _ "$RIG" "$SOCKET" "$SIZE" > "$RIG/shell.log" 2>&1 < /dev/null &
  for _ in $(seq 150); do running && break; sleep 0.2; done
  running || { echo "gnome-shell did not start; see $RIG/shell.log"; exit 1; }
  echo "running ($SIZE) in $RIG"
  ;;
run)
  shift
  running || { echo "not running: $0 start"; exit 1; }
  XDG_RUNTIME_DIR="$RIG/run" WAYLAND_DISPLAY=$SOCKET GDK_BACKEND=wayland \
    XDG_DATA_HOME="$RIG/data" XDG_CACHE_HOME="$RIG/cache" \
    DBUS_SESSION_BUS_ADDRESS="$(cat "$RIG/bus")" exec env -u DISPLAY "$@"
  ;;
stop)
  # end only the processes whose environment carries this rig's runtime dir
  for d in /proc/[0-9]*; do
    p=${d#/proc/}
    [ "$p" = "$$" ] && continue
    tr '\0' '\n' 2>/dev/null < "$d/environ" | grep -qx "XDG_RUNTIME_DIR=$RIG/run" && kill "$p" 2>/dev/null
  done
  [ -d "$RIG" ] && : > "$RIG/bus"
  echo "stopped"
  ;;
*)
  sed -n '2,13p' "$0"
  exit 2
  ;;
esac
