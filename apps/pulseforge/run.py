#!/usr/bin/env python3
"""
Standalone launcher for PulseForge (outside the Forge hub).

    .venv/bin/python run.py            # serve on http://127.0.0.1:8436

Forge itself launches the app via uvicorn against `web_app:app`; this is for
running it on its own during development.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")


def main():
    if os.path.exists(VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(
        VENV_PY
    ):
        os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__), *sys.argv[1:]])

    os.environ.setdefault("FORGE_SHARED_DIR", os.path.join(HERE, "..", "..", "shared"))
    sys.path.insert(0, HERE)
    import uvicorn

    uvicorn.run("web_app:app", host="127.0.0.1", port=8436, reload=False)


if __name__ == "__main__":
    main()
