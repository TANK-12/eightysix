"""The window behind "show the terminal": watch a headless shell and type into it.

Runs in a real terminal (gnome-terminal or kitty) with the system Python;
stdlib only. It prints the shell's transcript as it grows and sends every
line you type to the shell through Acchan (POST /api/shells/<name>/input).
Ctrl+C is passed on to whatever the shell is running; Ctrl+D closes only this
window. It exits by itself when the shell ends, so the window closes with the
shell and with Acchan.

    python3 shell_window.py <name> <log file> <bash pid> [port]
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import urllib.request


def send(port: int, name: str, text: str) -> None:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/shells/{name}/input",
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5).read()
    except OSError as exc:
        print(f"\n(could not reach Acchan: {exc})", flush=True)


def follow(log: str, pid: int) -> None:
    """Print the transcript as it grows; exit the window when the shell ends."""
    with open(log, encoding="utf-8", errors="replace") as f:
        while True:
            chunk = f.read()
            if chunk:
                sys.stdout.write(chunk)
                sys.stdout.flush()
            elif not os.path.exists(f"/proc/{pid}"):
                print("\n(the shell has ended)", flush=True)
                time.sleep(1.5)
                os._exit(0)
            else:
                time.sleep(0.15)


def main(argv: list[str]) -> int:
    name, log, pid = argv[1], argv[2], int(argv[3])
    port = int(argv[4]) if len(argv) > 4 else 8451
    print(f"Acchan shell '{name}': type a command and press Enter.", end=" ")
    print("Ctrl+C stops what it runs, Ctrl+D closes this window.\n", flush=True)
    signal.signal(signal.SIGINT, lambda *_: send(port, name, "\x03"))
    threading.Thread(target=follow, args=(log, pid), daemon=True).start()
    while True:
        try:
            line = sys.stdin.readline()
        except InterruptedError:
            continue
        if not line:  # Ctrl+D
            return 0
        send(port, name, line.rstrip("\n"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
