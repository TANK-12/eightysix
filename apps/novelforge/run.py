#!/usr/bin/env python3
"""
NovelForge launcher.

If customtkinter isn't importable but a NovelForge venv exists next to this
file, re-exec inside it. Otherwise print exactly what to run.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")


def _reexec_in_venv():
    if (os.path.exists(VENV_PY)
            and os.path.realpath(sys.executable) != os.path.realpath(VENV_PY)):
        os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__), *sys.argv[1:]])


def main():
    try:
        import customtkinter  # noqa: F401
    except Exception:
        _reexec_in_venv()
        try:
            import customtkinter  # noqa: F401
        except Exception:
            sys.stderr.write(
                "\nNovelForge needs a few packages.\n"
                "Run the one-time setup:\n\n"
                f"    bash {os.path.join(HERE, 'install.sh')}\n\n"
                "or install manually:\n"
                "    pip install --user customtkinter requests pypdf reportlab\n\n")
            sys.exit(1)

    sys.path.insert(0, HERE)
    from novelforge.app import main as run_app
    run_app()


if __name__ == "__main__":
    main()
