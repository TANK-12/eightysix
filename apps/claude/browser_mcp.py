"""An MCP server (stdio) that gives Claude the Forge Browser.

The Claude panel starts `claude` with this server in its MCP config. Each tool
is one command to the Browser app's queue (POST /api/agent/do on its port);
the Browser page inside Forge carries it out on real pages and answers. So
Claude sees what the user sees in the Browser, logins included, and the user
watches it happen.

Standard library only: MCP over stdio is JSON-RPC 2.0, one JSON object per
line. Only what Claude Code needs is implemented: initialize, tools/list,
tools/call and ping.

    python3 browser_mcp.py            (FORGE_BROWSER_URL overrides the port)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import panel_commands

BROWSER = os.environ.get("FORGE_BROWSER_URL", "http://127.0.0.1:8444")
BROWSER_WAIT = 25  # seconds to wait for a closed Browser that Forge is opening
PROTOCOL = "2025-06-18"
# The conversation's command queue (panel_commands.py); set by the panel per
# conversation. Without it the panel_command tool is not offered.
QUEUE = os.environ.get("FORGE_PANEL_QUEUE", "")

TAB = {
    "type": ["integer", "string"],
    "description": "Tab index (0 is the first) or tab id. Omit for the tab in front.",
}

# name -> (description, input schema properties, required). The tool name is
# also the Browser command, so adding a tool is one row here plus the op in
# the Browser page.
TOOLS = {
    "open": (
        "Open a web address in the Forge Browser and wait for it to load. Returns the tab.",
        {
            "url": {
                "type": "string",
                "description": "An address, or words to search for.",
            },
            "new_tab": {
                "type": "boolean",
                "description": "Open in a new tab instead of the one in front.",
            },
        },
        ["url"],
    ),
    "search": (
        "Search the web with the Browser's search engine and show the results page.",
        {
            "query": {"type": "string"},
            "new_tab": {"type": "boolean"},
        },
        ["query"],
    ),
    "read": (
        "Read a tab: its title, address, visible text and links. Use after open or search.",
        {
            "tab": TAB,
            "max_chars": {
                "type": "integer",
                "description": "Longest text to return, default 40000.",
            },
        },
        [],
    ),
    "tabs": ("List the open tabs with their index, title and address.", {}, []),
    "back": ("Go back in a tab.", {"tab": TAB}, []),
    "forward": ("Go forward in a tab.", {"tab": TAB}, []),
    "reload": ("Reload a tab.", {"tab": TAB}, []),
    "switch": ("Bring a tab to the front.", {"tab": TAB}, ["tab"]),
    "close": ("Close a tab.", {"tab": TAB}, ["tab"]),
}


PANEL_TOOL = "panel_command"


def panel_tool() -> dict:
    listed = "; ".join(
        f"{name}: {spec['help']}" for name, spec in panel_commands.COMMANDS.items()
    )
    return {
        "name": PANEL_TOOL,
        "description": "Run a Claude Code command on this session in the Forge panel. "
        "It runs as the next message once this turn ends (so end your turn after "
        f"asking). Commands: {listed}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": list(panel_commands.COMMANDS),
                },
                "args": {
                    "type": "string",
                    "description": "Words after the command, if it takes any.",
                },
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    }


def run_panel_command(arguments: dict, queue: str | None = None) -> dict:
    path = queue if queue is not None else QUEUE
    if not path:
        return {"ok": False, "error": "Only available in the Forge Claude panel"}
    try:
        line = panel_commands.queue(
            Path(path), arguments.get("command", ""), arguments.get("args") or ""
        )
    except (ValueError, OSError) as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "queued": line,
        "note": "It runs as the next message when this turn ends.",
    }


def tool_list() -> list[dict]:
    panel = [panel_tool()] if QUEUE else []
    return panel + [
        {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        }
        for name, (description, properties, required) in TOOLS.items()
    ]


def call_browser(
    op: str,
    arguments: dict,
    opener=urllib.request.urlopen,
    wait: float | None = None,
    sleep=time.sleep,
    now=time.monotonic,
) -> dict:
    """One command to the Browser. When the Browser is closed, the panel page
    asks Forge to open it as soon as it sees the tool call, so wait up to `wait`
    seconds for it to come up instead of failing at once."""
    body = json.dumps({**arguments, "op": op, "timeout": 45}).encode()
    request = urllib.request.Request(
        f"{BROWSER}/api/agent/do",
        data=body,
        headers={"Content-Type": "application/json", "X-Forge": "1"},
    )
    wait = BROWSER_WAIT if wait is None else wait
    deadline = now() + wait
    while True:
        try:
            with opener(request, timeout=60) as response:
                return json.loads(response.read())
        except urllib.error.URLError as e:
            if now() >= deadline:
                return {
                    "ok": False,
                    "error": f"The Forge Browser did not open in {int(wait)} s ({e.reason}). "
                    "Open the Browser app in Forge and try again.",
                }
            sleep(1)
        except (ValueError, OSError) as e:
            return {"ok": False, "error": str(e)}


def handle(message: dict, opener=urllib.request.urlopen) -> dict | None:
    """One JSON-RPC message in, its reply out (None for notifications)."""
    method = message.get("method")
    mid = message.get("id")
    if mid is None:
        return None
    if method == "initialize":
        requested = (message.get("params") or {}).get("protocolVersion") or PROTOCOL
        result = {
            "protocolVersion": requested,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "forge-browser", "version": "1"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        if name == PANEL_TOOL and QUEUE:
            answer = run_panel_command(params.get("arguments") or {})
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(answer)}],
                    "isError": not answer["ok"],
                },
            }
        if name not in TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32602, "message": f"Unknown tool {name}"},
            }
        answer = call_browser(name, params.get("arguments") or {}, opener)
        result = {
            "content": [
                {"type": "text", "text": json.dumps(answer, ensure_ascii=False)}
            ],
            "isError": not answer.get("ok", False),
        }
    else:
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        reply = handle(message)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
