"""MCP server (stdio) exposing every Acchan tool, for Claude Code, Nyarch
Assistant or any MCP client.

The tools are the registry's own, so a tool added under acchan/tools/ shows
up here with no change. MCP over stdio is JSON-RPC 2.0, one object per line;
only initialize, tools/list, tools/call and ping are needed.

    ~/Forge/apps/acchan/.venv/bin/python ~/Forge/apps/acchan/mcp_server.py

ACCHAN_MCP_TOOLSETS=windows,apps limits which toolsets are offered.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acchan import registry  # noqa: E402

PROTOCOL = "2025-06-18"


def offered() -> list[registry.Tool]:
    registry.load_all()
    only = {
        s.strip()
        for s in os.environ.get("ACCHAN_MCP_TOOLSETS", "").split(",")
        if s.strip()
    }
    return [t for t in registry.TOOLS.values() if not only or t.toolset in only]


def tool_list() -> list[dict]:
    return [
        {
            "name": t.name,
            "description": f"[{t.toolset}] {t.description}",
            "inputSchema": {
                "type": "object",
                "properties": t.properties,
                "required": t.required,
            },
        }
        for t in offered()
    ]


def handle(message: dict) -> dict | None:
    method = message.get("method")
    mid = message.get("id")
    if mid is None:
        return None  # a notification
    if method == "initialize":
        result = {
            "protocolVersion": message.get("params", {}).get(
                "protocolVersion", PROTOCOL
            ),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "acchan", "version": "1.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name", "")
        allowed = {t.name for t in offered()}
        if registry.resolve_name(name) not in allowed:
            result = {
                "content": [{"type": "text", "text": f"Unknown tool {name}"}],
                "isError": True,
            }
        else:
            try:
                text = registry.call(name, params.get("arguments") or {})
                result = {"content": [{"type": "text", "text": text}], "isError": False}
            except registry.ToolError as exc:
                result = {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                }
    else:
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "error": {"code": -32601, "message": f"no method {method}"},
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
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
