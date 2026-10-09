"""Switch the laptop panel's refresh rate on GNOME through Mutter's DisplayConfig D-Bus API.

Run with the system Python (`/usr/bin/python3 display_gnome.py <hz>`), which has
the GObject bindings the app's venv lacks; `plan` is pure so the venv can test it.
Prints one line saying what happened.
"""

from __future__ import annotations

import sys

BUS_NAME = "org.gnome.Mutter.DisplayConfig"
OBJECT_PATH = "/org/gnome/Mutter/DisplayConfig"
TEMPORARY = 1  # applied now, not written to monitors.xml


def _current_mode(modes: list) -> tuple | None:
    return next((m for m in modes if m[6].get("is-current")), None)


def plan(state: tuple, hz: int) -> tuple[list, str]:
    """The logical-monitor layout for ApplyMonitorsConfig, or [] and a reason to skip.

    `state` is GetCurrentState's (serial, monitors, logical_monitors, properties)
    with variants already unpacked. Every monitor keeps its current mode except
    the built-in eDP panel, which gets the same size at `hz`.
    """
    _serial, monitors, logical_monitors, _props = state
    chosen: dict[str, str] = {}
    changed = False
    for spec, modes, _mprops in monitors:
        current = _current_mode(modes)
        if current is None:
            continue
        pick = current
        if spec[0].startswith("eDP"):
            if round(current[3]) == hz:
                return [], f"already {hz} Hz"
            pick = next(
                (
                    m
                    for m in modes
                    if m[1] == current[1] and m[2] == current[2] and round(m[3]) == hz
                ),
                None,
            )
            if pick is None:
                return [], f"the panel has no {hz} Hz mode"
            changed = True
        chosen[spec[0]] = pick[0]
    if not changed:
        return [], "no laptop panel found"
    layout = []
    for x, y, scale, transform, primary, specs, _lprops in logical_monitors:
        outs = [(s[0], chosen[s[0]], {}) for s in specs if s[0] in chosen]
        if outs:
            layout.append((x, y, scale, transform, primary, outs))
    return layout, f"switched to {hz} Hz"


def main(argv: list[str]) -> int:
    import gi  # pyright: ignore[reportMissingImports]  (system Python only)

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib  # pyright: ignore  (system Python only)

    hz = int(argv[1])
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            None,
            BUS_NAME,
            OBJECT_PATH,
            BUS_NAME,
            None,
        )
        state = proxy.call_sync("GetCurrentState", None, 0, 5000, None).unpack()
        layout, note = plan(state, hz)
        if layout:
            args = GLib.Variant(
                "(uua(iiduba(ssa{sv}))a{sv})", (state[0], TEMPORARY, layout, {})
            )
            proxy.call_sync("ApplyMonitorsConfig", args, 0, 10000, None)
    except GLib.Error as exc:
        print(f"GNOME display config unavailable: {exc.message}")
        return 1
    print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
