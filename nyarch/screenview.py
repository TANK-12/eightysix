#!/usr/bin/env python3
"""Let Nyarch Assistant see the screen and scroll it, on GNOME 50 Wayland.

GNOME 50 refuses the two obvious ways to grab a screenshot: `gnome-screenshot`
gets "Screenshot is not allowed" from the shell's D-Bus service, and `grim`
fails because GNOME does not implement the wlr-screencopy protocol.  The only
route left is the desktop's own screen-share portal, so that is what this uses:
it asks the portal once, stores the "restore token" the portal hands back, and
every capture after that is silent because the portal remembers the grant.

Frames come out of PipeWire through GStreamer.  Scrolling goes through ydotool,
which is already running as a system service on this machine.

Usage:
    screenview.py shot   [--out PATH] [--width N]
    screenview.py scroll [--amount N] [--direction up|down]
    screenview.py setup
"""

import argparse
import os
import subprocess
import sys
import time

import gi

gi.require_version("Gio", "2.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gio, GLib, Gst  # type: ignore  # noqa: E402

STATE_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
    "forge-nyarch",
)
TOKEN_FILE = os.path.join(STATE_DIR, "screencast-token")
DEFAULT_SHOT = os.path.join(STATE_DIR, "screen.png")
YDOTOOL_SOCKET = f"/run/user/{os.getuid()}/.ydotool_socket"

PORTAL_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"

# The portal drops the first frames while the stream negotiates, so read a few
# and keep the last one.
FRAMES_TO_SETTLE = 8


def read_token() -> str:
    try:
        with open(TOKEN_FILE) as handle:
            return handle.read().strip()
    except OSError:
        return ""


def write_token(token: str) -> None:
    if not token:
        return
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w") as handle:
        handle.write(token)


class PortalSession:
    """One screen-share session, opened and closed around a single capture."""

    def __init__(self, bus: Gio.DBusConnection):
        self.bus = bus
        self.unique = bus.get_unique_name()[1:].replace(".", "_")
        self.counter = 0
        self.session_handle = ""

    def _request(self, method: str, build_args, timeout_ms: int = 120000) -> dict:
        """Call a portal method and wait for its asynchronous Response signal."""
        self.counter += 1
        token = f"fnv{os.getpid()}_{self.counter}"
        path = f"/org/freedesktop/portal/desktop/request/{self.unique}/{token}"
        loop = GLib.MainLoop()
        result: dict = {}

        def on_response(_c, _s, _p, _i, _sig, params):
            code, payload = params.unpack()
            result["code"] = code
            result["payload"] = payload
            loop.quit()

        subscription = self.bus.signal_subscribe(
            PORTAL_NAME,
            "org.freedesktop.portal.Request",
            "Response",
            path,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
        )
        try:
            self.bus.call_sync(
                PORTAL_NAME,
                PORTAL_PATH,
                SCREENCAST_IFACE,
                method,
                build_args(token),
                None,
                Gio.DBusCallFlags.NONE,
                timeout_ms,
                None,
            )
            GLib.timeout_add(timeout_ms + 1000, lambda: (loop.quit(), False)[1])
            loop.run()
        finally:
            self.bus.signal_unsubscribe(subscription)

        if result.get("code") != 0:
            raise RuntimeError(
                f"{method} refused by the portal (code {result.get('code')})"
            )
        return result.get("payload", {})

    def open(self, interactive: bool) -> None:
        payload = self._request(
            "CreateSession",
            lambda token: GLib.Variant(
                "(a{sv})",
                (
                    {
                        "handle_token": GLib.Variant("s", token),
                        "session_handle_token": GLib.Variant("s", token + "s"),
                    },
                ),
            ),
        )
        self.session_handle = payload["session_handle"]

        options = {
            "types": GLib.Variant("u", 1),  # monitors
            "multiple": GLib.Variant("b", False),
            "cursor_mode": GLib.Variant("u", 2),  # draw the pointer into the frame
            "persist_mode": GLib.Variant("u", 2),  # remember across restarts
        }
        token = read_token()
        if token and not interactive:
            options["restore_token"] = GLib.Variant("s", token)

        self._request(
            "SelectSources",
            lambda handle: GLib.Variant(
                "(oa{sv})",
                (
                    self.session_handle,
                    {**options, "handle_token": GLib.Variant("s", handle)},
                ),
            ),
        )

        started = self._request(
            "Start",
            lambda handle: GLib.Variant(
                "(osa{sv})",
                (
                    self.session_handle,
                    "",
                    {"handle_token": GLib.Variant("s", handle)},
                ),
            ),
        )
        write_token(started.get("restore_token", ""))
        streams = started.get("streams") or []
        if not streams:
            raise RuntimeError("The portal granted no video stream")
        self.node_id = streams[0][0]
        # The portal reports the monitor size here; without it videoscale has
        # nothing to preserve the aspect ratio against and collapses the height.
        self.size = tuple(streams[0][1].get("size") or ()) or None

    def pipewire_fd(self) -> int:
        reply, fd_list = self.bus.call_with_unix_fd_list_sync(
            PORTAL_NAME,
            PORTAL_PATH,
            SCREENCAST_IFACE,
            "OpenPipeWireRemote",
            GLib.Variant("(oa{sv})", (self.session_handle, {})),
            GLib.VariantType("(h)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )
        return fd_list.steal_fds()[reply.unpack()[0]]

    def close(self) -> None:
        if not self.session_handle:
            return
        try:
            self.bus.call_sync(
                PORTAL_NAME,
                self.session_handle,
                "org.freedesktop.portal.Session",
                "Close",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                5000,
                None,
            )
        except GLib.Error:
            pass


def grab_frame(fd: int, node_id: int, out_path: str, width: int, size=None) -> None:
    """Pull frames from the PipeWire node and write the last one as a PNG."""
    Gst.init(None)
    scale = ""
    if width and size and size[0] and size[0] > width:
        height = max(1, round(size[1] * width / size[0]))
        height -= height % 2
        scale = (
            f"videoscale add-borders=false ! "
            f"video/x-raw,width={width},height={height} ! "
        )
    description = (
        f"pipewiresrc fd={fd} path={node_id} always-copy=true "
        f"! videoconvert ! {scale}videoconvert "
        f"! pngenc snapshot=false ! appsink name=sink max-buffers=2 drop=true"
    )
    pipeline = Gst.parse_launch(description)
    sink = pipeline.get_by_name("sink")
    pipeline.set_state(Gst.State.PLAYING)

    last = None
    deadline = time.monotonic() + 20
    seen = 0
    try:
        while time.monotonic() < deadline and seen < FRAMES_TO_SETTLE:
            sample = sink.emit("try-pull-sample", 2 * Gst.SECOND)
            if sample is None:
                break
            last = sample
            seen += 1
    finally:
        pipeline.set_state(Gst.State.NULL)

    if last is None:
        raise RuntimeError("PipeWire produced no frames")

    buffer = last.get_buffer()
    ok, info = buffer.map(Gst.MapFlags.READ)
    if not ok:
        raise RuntimeError("Could not read the captured frame")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        with open(out_path, "wb") as handle:
            handle.write(info.data)
    finally:
        buffer.unmap(info)


def take_shot(out_path: str, width: int, interactive: bool, attempts: int = 3) -> str:
    """Capture the screen, retrying if the compositor is busy.

    While a model is generating on the Iris Xe, that same GPU is also encoding
    this stream, and PipeWire sometimes delivers no frames at all before the
    timeout. Waiting a moment and asking again clears it.
    """
    last_error = None
    for attempt in range(attempts):
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        session = PortalSession(bus)
        try:
            session.open(interactive)
            grab_frame(
                session.pipewire_fd(),
                session.node_id,
                out_path,
                width,
                session.size,
            )
            return out_path
        except Exception as error:
            last_error = error
        finally:
            session.close()
        if attempt < attempts - 1:
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"Screen capture failed after {attempts} tries: {last_error}")


def scroll(amount: int, direction: str) -> str:
    steps = -abs(amount) if direction == "down" else abs(amount)
    env = dict(os.environ, YDOTOOL_SOCKET=YDOTOOL_SOCKET)
    subprocess.run(
        ["ydotool", "mousemove", "-w", "-x", "0", "-y", str(steps)],
        env=env,
        check=True,
        capture_output=True,
        timeout=10,
    )
    return f"Scrolled {direction} by {abs(amount)} notches."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    shot_parser = sub.add_parser("shot", help="capture the screen to a PNG")
    shot_parser.add_argument("--out", default=DEFAULT_SHOT)
    shot_parser.add_argument("--width", type=int, default=1024)

    scroll_parser = sub.add_parser("scroll", help="scroll the focused window")
    scroll_parser.add_argument("--amount", type=int, default=5)
    scroll_parser.add_argument("--direction", choices=("up", "down"), default="down")

    sub.add_parser("setup", help="ask for screen-share permission and store it")

    args = parser.parse_args()
    try:
        if args.command == "shot":
            print(take_shot(args.out, args.width, interactive=False))
        elif args.command == "scroll":
            print(scroll(args.amount, args.direction))
        else:
            path = take_shot(DEFAULT_SHOT, 1024, interactive=True)
            print(f"Screen sharing approved and remembered. Test capture: {path}")
    except Exception as error:  # surfaced to the assistant as tool output
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
