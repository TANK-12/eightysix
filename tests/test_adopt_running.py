"""A backend already answering on its port is adopted, not launched again.

Acchan runs as an always-on user service (Nyarch and the terminal use it
without Forge open), so when Forge starts, port 8451 is already taken. Before
2026-09-22 Forge launched a second uvicorn, which could only fail to bind and
left the app marked failed. Run with /usr/bin/python3: forge.py imports gi.
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import forge  # noqa: E402


def test_running_backend_is_adopted_and_left_running():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".venv", "bin"))
        open(os.path.join(root, ".venv", "bin", "python"), "w").close()
        backend = forge.Backend(
            {"name": "svc", "port": port, "module": "web_app:app"}, root
        )
        assert backend.start() is True
        assert backend.state == "up"
        assert backend.proc is None  # nothing launched, so nothing to kill later
    listener.close()


if __name__ == "__main__":
    test_running_backend_is_adopted_and_left_running()
    print("ALL PASS")
