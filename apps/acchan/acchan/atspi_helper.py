"""Read and press the controls of any accessible app, through AT-SPI.

Runs under the SYSTEM python (/usr/bin/python3), because PyGObject and the
Atspi typelib come from the distro and the app's .venv does not have them.
Called by tools/ui.py as a subprocess; prints one JSON object.

    atspi_helper.py list  <pid> [filter]
    atspi_helper.py press <pid> <name> [role]
    atspi_helper.py text  <pid> <name> <text>
    atspi_helper.py read  <pid>
    atspi_helper.py windows          (every app's top-level windows)
"""

from __future__ import annotations

import json
import sys

import gi  # type: ignore  # system python's PyGObject, not in the venv

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # type: ignore  # noqa: E402

ACTIONABLE = {
    "push button",
    "toggle button",
    "check box",
    "radio button",
    "menu item",
    "check menu item",
    "radio menu item",
    "link",
    "page tab",
    "list item",
    "tree item",
    "combo box",
    "entry",
    "text",
    "password text",
    "spin button",
    "slider",
    "icon",
    "table cell",
}
MAX_NODES = 4000


def app_for(pid: int):
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        try:
            if app is not None and app.get_process_id() == pid:
                return app
        except Exception:
            continue
    return None


def walk(node, depth=0, out=None, budget=None):
    out = [] if out is None else out
    budget = budget if budget is not None else [MAX_NODES]
    if node is None or budget[0] <= 0 or depth > 40:
        return out
    budget[0] -= 1
    try:
        states = node.get_state_set()
        if depth > 0 and not states.contains(Atspi.StateType.SHOWING):
            return out
        role = node.get_role_name()
        name = (node.get_name() or "").strip()
        out.append((node, role, name, depth))
        for i in range(node.get_child_count()):
            walk(node.get_child_at_index(i), depth + 1, out, budget)
    except Exception:
        pass
    return out


def matches(name: str, want: str) -> float:
    n, w = name.lower(), want.lower().strip()
    if not n:
        return 0
    if n == w:
        return 1.0
    if n.startswith(w) or w in n:
        return 0.8
    return 0


def windows() -> list[dict]:
    desktop = Atspi.get_desktop(0)
    found = []
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app is None:
            continue
        try:
            app_name, pid = app.get_name(), app.get_process_id()
            count = app.get_child_count()
        except Exception:
            continue
        if app_name == "gnome-shell":
            continue
        for j in range(min(count, 30)):
            frame = app.get_child_at_index(j)
            if frame is None:
                continue
            try:
                if frame.get_role_name() not in ("frame", "window", "dialog"):
                    continue
                states = frame.get_state_set()
                if not states.contains(Atspi.StateType.SHOWING) and not states.contains(
                    Atspi.StateType.ACTIVE
                ):
                    continue
                found.append(
                    {
                        "class": app_name,
                        "pid": pid,
                        "title": frame.get_name() or "",
                        "active": states.contains(Atspi.StateType.ACTIVE),
                        "address": f"{pid}:{j}",
                    }
                )
            except Exception:
                continue
    return found


def main() -> None:
    if sys.argv[1] == "windows":
        print(json.dumps({"windows": windows()}))
        return
    cmd, pid = sys.argv[1], int(sys.argv[2])
    app = app_for(pid)
    if app is None:
        print(
            json.dumps({"error": "app does not expose accessibility (AT-SPI) controls"})
        )
        return
    nodes = walk(app)
    if cmd == "list":
        flt = (sys.argv[3] if len(sys.argv) > 3 else "").lower()
        rows = []
        for _node, role, name, _depth in nodes:
            if role in ACTIONABLE and (name or role in ("entry", "text")):
                if flt and flt not in name.lower() and flt not in role:
                    continue
                rows.append(f"{role}: {name}" if name else role)
        seen, unique = set(), []
        for row in rows:
            if row not in seen:
                seen.add(row)
                unique.append(row)
        print(json.dumps({"controls": unique[:250], "total": len(unique)}))
    elif cmd == "read":
        texts = []
        for node, role, name, _depth in nodes:
            if role in ("label", "heading", "paragraph", "static", "text") and name:
                texts.append(name)
            elif role in ("text", "paragraph", "document text"):
                try:
                    t = node.get_text_iface()
                    if t:
                        texts.append(t.get_text(0, min(t.get_character_count(), 4000)))
                except Exception:
                    pass
        print(json.dumps({"text": "\n".join(texts)[:12000]}))
    elif cmd in ("press", "text"):
        want = sys.argv[3]
        role_want = sys.argv[4] if cmd == "press" and len(sys.argv) > 4 else ""
        best, best_score = None, 0.0
        for node, role, name, _depth in nodes:
            if role not in ACTIONABLE:
                continue
            if cmd == "text" and role not in (
                "entry",
                "text",
                "password text",
                "spin button",
                "combo box",
            ):
                continue
            if role_want and role_want not in role:
                continue
            score = matches(name, want)
            if cmd == "text" and not want:
                score = 0.5
            if score > best_score:
                best, best_score = (node, role, name), score
        if best is None:
            print(json.dumps({"error": f"no control named {want!r}"}))
            return
        node, role, name = best
        if cmd == "text":
            iface = node.get_editable_text_iface()
            if iface is None:
                print(json.dumps({"error": f"{role} {name!r} cannot take text"}))
                return
            iface.set_text_contents(sys.argv[5] if len(sys.argv) > 5 else "")
            print(json.dumps({"ok": f"set text of {role} {name!r}"}))
            return
        action = node.get_action_iface()
        if action is None or action.get_n_actions() == 0:
            try:
                node.get_component_iface().grab_focus()
                print(
                    json.dumps(
                        {"ok": f"focused {role} {name!r} (it has no press action)"}
                    )
                )
            except Exception:
                print(json.dumps({"error": f"{role} {name!r} cannot be pressed"}))
            return
        action.do_action(0)
        print(
            json.dumps({"ok": f"pressed {role} {name!r} ({action.get_action_name(0)})"})
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
