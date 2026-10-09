"""Starting apps and opening files or links with the right program.

Apps are found from their .desktop entries (system, user and Flatpak), the
same list the app launcher shows, so "open file explorer", "open qobuz" or
"open steam" work without a hardcoded table. Launching goes through the
desktop (Hyprland's own `exec` there, a detached process on GNOME), so the app
gets the session's environment even when the request came from a sandboxed
caller such as Nyarch.
"""

from __future__ import annotations

import configparser
import difflib
import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Annotated

from ..desktop import current
from ..registry import ToolError, tool
from ..sysutil import path as to_path

sys.path.insert(
    0, os.environ.get("FORGE_SHARED_DIR", str(Path.home() / "Forge" / "shared"))
)
import forge_open  # noqa: E402

TOOLSET = "apps"
TOOLSET_SUMMARY = (
    "start apps, open files/folders/links in their default app, list installed apps"
)

TOOLSET_KEYWORDS = (
    "open",
    "launch",
    "start",
    "run",
    "app",
    "program",
    "explorer",
    "steam",
    "qobuz",
    "spotify",
    "discord",
    "calculator",
    "settings",
    "editor",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_EXAMPLES = [
    ("open the file explorer", "launch_app", {"name": "file explorer"}),
    (
        "open my resume pdf in Documents",
        "open_item",
        {"target": "~/Documents/resume.pdf"},
    ),
]

DESKTOP_DIRS = [
    Path.home() / ".local/share/applications",
    Path.home() / ".local/share/flatpak/exports/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
]

# Words people use for a kind of app, mapped to the desktop Categories that
# mean it. Used only when no app name matches.
KINDS = {
    "file explorer": "FileManager",
    "file manager": "FileManager",
    "files": "FileManager",
    "explorer": "FileManager",
    "terminal": "TerminalEmulator",
    "browser": "WebBrowser",
    "web browser": "WebBrowser",
    "text editor": "TextEditor",
    "editor": "TextEditor",
    "music": "Audio",
    "music player": "Audio",
    "video player": "Video",
    "calculator": "Calculator",
    "settings": "Settings",
    "image viewer": "Viewer",
    "email": "Email",
}
# The user's own choices from hyprland.conf binds, preferred over the first
# app of a kind.
# What people call an app when its launcher name differs.
NICKNAMES = {
    "qobuz": "qbz",
    "vs code": "code",
    "vscode": "code",
    "file browser": "file explorer",
}
PREFERRED = {
    "FileManager": "dolphin",
    "TerminalEmulator": "gnome.terminal",
    "WebBrowser": "firefox",
}


def _entries() -> list[dict]:
    seen, found = set(), []
    for folder in DESKTOP_DIRS:
        if not folder.is_dir():
            continue
        for file in sorted(folder.glob("*.desktop")):
            if file.name in seen:
                continue
            seen.add(file.name)
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                parser.read(file, encoding="utf-8")
                entry = parser["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                continue
            if entry.get("Type", "Application") != "Application":
                continue
            found.append(
                {
                    "id": file.stem,
                    "file": str(file),
                    "name": entry.get("Name", file.stem),
                    "generic": entry.get("GenericName", ""),
                    "keywords": entry.get("Keywords", ""),
                    "categories": entry.get("Categories", ""),
                    "exec": entry.get("Exec", ""),
                    "hidden": entry.get("NoDisplay", "false").lower() == "true"
                    or entry.get("Hidden", "false").lower() == "true",
                }
            )
    return found + _forge_entries()


def _forge_entries() -> list[dict]:
    """Forge's own apps, discovered from their forge_app.json. They open
    inside the Forge window (forge_open), not as separate programs."""
    return [
        {
            "id": f"forge:{app['name']}",
            "file": "",
            "name": app["label"],
            "generic": "Forge app",
            "keywords": f"forge {app['tagline']}",
            "categories": "Forge;",
            "exec": f"/usr/bin/python3 {forge_open.FORGE_PY} --app {app['name']}",
            "hidden": False,
            "forge": app["name"],
            "aliases": (app["name"], f"forge {app['name']}", f"forge {app['label']}"),
        }
        for app in forge_open.forge_apps()
    ]


def find_app(query: str, strict: bool = False) -> dict | None:
    """The installed app a person most likely means by `query`. strict=True
    accepts only a near-certain match (used by the no-model fast path)."""
    q = query.strip().lower()
    q = re.sub(r"^(the|a|an|my)\s+", "", q)
    q = re.sub(r"\s+(app|application|program)$", "", q)
    q = NICKNAMES.get(q, q)
    apps = _entries()
    visible = [a for a in apps if not a["hidden"]] or apps

    def score(app: dict) -> float:
        name = app["name"].lower()
        ident = app["id"].lower().split(".")[-1]
        aliases = [a.lower() for a in app.get("aliases", ())]
        if q in (name, ident, app["id"].lower(), *aliases):
            return 1.0
        best = max(
            difflib.SequenceMatcher(None, q, name).ratio(),
            difflib.SequenceMatcher(None, q, ident).ratio(),
        )
        if name.startswith(q) or ident.startswith(q):
            best = max(best, 0.9)
        elif q in name or q in app["keywords"].lower() or q in app["generic"].lower():
            best = max(best, 0.8)
        return best

    ranked = sorted(((score(a), a) for a in visible), key=lambda p: -p[0])
    # A system app's exact name first ("files", "terminal"), then a kind of
    # app ("browser" is the user's Firefox, not Forge's Browser app), then the
    # closest name, Forge apps included.
    for value, app in ranked:
        if value < 1.0:
            break
        if not app.get("forge"):
            return app
    category = KINDS.get(q)
    if category:
        kind = [a for a in visible if category in a["categories"].split(";")]
        preferred = PREFERRED.get(category, "")
        for app in kind:
            if preferred and preferred in app["id"].lower():
                return app
        if kind:
            return kind[0]
    if ranked and ranked[0][0] >= (0.88 if strict else 0.72):
        return ranked[0][1]
    return None


def _exec_line(app: dict) -> str:
    # Field codes (%U, %f ...) are for file arguments; drop them.
    return re.sub(r"\s*%[a-zA-Z]", "", app["exec"]).strip()


def hypr_exec(command: str) -> None:
    """Start a command through the desktop (Hyprland's exec, or detached)."""
    current().exec(command)


@tool(
    TOOLSET,
    example={"name": "firefox"},
    phrases=[
        "open {name}",
        "launch {name}",
        "start {name}",
        "fire up {name}",
        "bring up {name}",
        "load up {name}",
        "open up {name}",
        "start up {name}",
    ],
    voice="fast",
)
def launch_app(
    name: Annotated[
        str, "App name or kind, like firefox, file explorer, terminal, qobuz, steam"
    ],
    arguments: Annotated[str, "Optional file, folder or URL to open in it"] = "",
) -> str:
    """Start an installed desktop app by name or by kind (file explorer, terminal, browser, music player...)."""
    app = find_app(name)
    if app is None:
        if shutil.which(name.strip()):
            # the arguments are words from a chat, never shell syntax
            extra = shlex.quote(arguments.strip()) if arguments.strip() else ""
            hypr_exec(f"{shlex.quote(name.strip())} {extra}".strip())
            return f"Started {name}."
        close = [
            a["name"] for a in _entries() if name.lower()[:3] in a["name"].lower()
        ][:5]
        hint = (
            f" Similar: {', '.join(close)}."
            if close
            else " Use list_apps to see what is installed."
        )
        raise ToolError(f"No installed app matches {name!r}.{hint}")
    if app.get("forge"):
        return _open_in_forge(app)
    if (
        "TerminalEmulator" in app["categories"]
        and arguments
        and not re.match(r"^[a-z]+://", arguments)
    ):
        from .terminal import open_terminal

        return open_terminal(folder=arguments)
    command = _exec_line(app)
    if arguments:
        command += " " + _quote(arguments)
    hypr_exec(command)
    return f"Started {app['name']}."


def _open_in_forge(app: dict) -> str:
    label = app["name"]
    answer = forge_open.request_open(app["forge"])
    if answer == "ok":
        return f"Opened {label} in Forge."
    if answer == "unknown":
        _focus_forge()
        return (
            f"Forge does not list {label} yet; it picks up new apps within "
            "about 15 seconds, so try again in a moment."
        )
    if forge_open.forge_running():
        # A Forge started before it could take requests: never start a second.
        _focus_forge()
        return (
            f"Forge is open, but it was started before it could switch apps on "
            f"request: pick {label} there. After Forge restarts I can switch to "
            "it for you."
        )
    hypr_exec(_exec_line(app))
    return f"Starting Forge on {label}."


def _focus_forge() -> None:
    from .windows import focus_window

    try:
        focus_window("Forge")
    except ToolError:
        pass


def _quote(text: str) -> str:
    text = text.strip()
    if re.match(r"^[a-z]+://", text):
        return "'" + text.replace("'", "%27") + "'"
    return "'" + str(to_path(text)).replace("'", "'\\''") + "'"


@tool(TOOLSET, example={"target": "~/Documents/report.pdf"}, voice="fast")
def open_item(
    target: Annotated[str, "A file, folder or web address"],
) -> str:
    """Open a file, folder or web address in its default app (PDF viewer, file manager, browser...)."""
    text = target.strip()
    if re.match(r"^(https?|file|mailto)://|^www\.", text):
        url = text if "://" in text else "https://" + text
        hypr_exec("xdg-open " + _quote(url))
        return f"Opened {url}."
    item = to_path(text)
    if not item.exists():
        raise ToolError(f"{item} does not exist. Use find_files to locate it.")
    hypr_exec("xdg-open " + _quote(str(item)))
    return f"Opened {item}."


@tool(TOOLSET, example={"filter": "music"}, show=True, voice="ok")
def list_apps(
    filter: Annotated[str, "Only apps whose name or category contains this"] = "",
) -> str:
    """List installed desktop apps (name and category)."""
    rows = []
    for app in _entries():
        if app["hidden"]:
            continue
        text = f"{app['name']} [{app['categories'].split(';')[0] if app['categories'] else ''}]"
        if (
            filter
            and filter.lower() not in (text + app["keywords"] + app["id"]).lower()
        ):
            continue
        rows.append(text)
    return "\n".join(sorted(set(rows))) or "No apps match."
