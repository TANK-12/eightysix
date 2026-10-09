#!/usr/bin/env python3
"""
anime_library.py -- companion report for the anime library the sorter builds.

    anime_library.py [LIBRARY_ROOT]

Prints: every series, year, season/episode counts, size, missing-episode gaps,
episodes that still hold both an .mkv and an .mp4, and files with no SxxExx.
With no argument it uses `library_root` from ~/MediaForgeData/settings.json.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mediaforge.config import load_settings                     # noqa: E402
from mediaforge.modules.anime_library import library_report     # noqa: E402


def main():
    if len(sys.argv) > 1:
        root = sys.argv[1]
    else:
        root = load_settings().get("library_root")
    if not root or not Path(root).is_dir():
        sys.exit(f"library root not found: {root}")
    text, lib = library_report(root)
    print(text)
    out = Path(root) / "_library_report.txt"
    try:
        out.write_text(text, "utf-8")
        print(f"\n(written to {out})")
    except Exception:
        pass


if __name__ == "__main__":
    main()
