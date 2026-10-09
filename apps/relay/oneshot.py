"""One lean Claude answer: a single turn with no tools, Relay's own system
prompt and none of the user's settings, hooks, CLAUDE.md or MCP servers.

Measured 2026-10-07 (sonnet, low, "say hi"): a plain `claude -p` wrote 31,555
tokens to the prompt cache before answering; this lean form sent 405. So a
short answer costs about the prompt you give it and nothing more.
"""

from __future__ import annotations

import subprocess
import time

import meters
import picker
import store


def account_for(readings: dict, settings: dict) -> tuple[str | None, str]:
    """An account with room, ignoring launch spacing (one turn is tiny)."""
    relaxed = {**settings, "launch_gap_minutes": 0, "slow_gap_minutes": 0}
    return picker.pick_account(readings, {}, time.time(), relaxed)


def ask(
    prompt: str,
    system: str,
    account: str,
    model: str = "sonnet",
    effort: str = "low",
    timeout: float = 240,
) -> str:
    """The model's answer text; raises RuntimeError when Claude fails."""
    from claude_launch import find_claude  # the boss's PATH has no ~/.local/bin

    claude = find_claude("RELAY_CLAUDE_BIN")
    if not claude:
        raise RuntimeError("claude not found")
    try:
        done = subprocess.run(
            [
                claude,
                "-p",
                prompt,
                "--system-prompt",
                system,
                "--model",
                store.model_id(model),
                "--effort",
                effort,
                "--max-turns",
                "1",
                "--no-session-persistence",
                "--tools",
                "",
                "--setting-sources",
                "",
                "--strict-mcp-config",
            ],
            cwd="/tmp",
            env=meters.env_for(account),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"claude did not answer: {e}") from e
    if done.returncode or not done.stdout.strip():
        raise RuntimeError(f"claude failed: {(done.stderr or done.stdout)[-200:]}")
    return done.stdout
