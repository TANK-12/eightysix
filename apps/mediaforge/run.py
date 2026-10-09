#!/usr/bin/env python3
"""MediaForge launcher. Re-execs into the bundled .venv if customtkinter isn't
importable here."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")


def main():
    try:
        import customtkinter  # noqa
    except Exception:
        if os.path.exists(VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(VENV_PY):
            os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__), *sys.argv[1:]])
        sys.stderr.write("\nMediaForge needs setup. Run:\n    bash %s\n\n"
                         % os.path.join(HERE, "install.sh"))
        sys.exit(1)
    sys.path.insert(0, HERE)
    from mediaforge.app import main as run
    run()


if __name__ == "__main__":
    main()
