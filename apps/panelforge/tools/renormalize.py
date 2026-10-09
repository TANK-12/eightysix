"""Re-clean the reader's text from `text_raw` with the current cleaner.

    .venv/bin/python tools/renormalize.py bad-born-blood            # all chapters
    .venv/bin/python tools/renormalize.py bad-born-blood 0003 0004

No OCR runs: only `normalize` and the learned glossary are applied to every
bubble that was not edited by hand. Prints what changed. The script lines
take the new text at the next script build (`tools/rebuild_chapter.py
--from script`).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from panelforge import paths, store  # noqa: E402
from panelforge.detect import normalize as N  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    series, chapters = argv[0], argv[1:]
    sdir = paths.series_dir(series)
    if not chapters:
        chapters = sorted(p.name for p in (sdir / "chapters").iterdir() if p.is_dir())
    total = 0
    for ch in chapters:
        cdir = sdir / "chapters" / ch
        doc = store.read(cdir / "bubbles.json", None)
        if not doc:
            continue
        N.learn_glossary(cdir)
        changed = 0
        for b in doc.get("bubbles", []):
            if b.get("edited") or not b.get("text_raw"):
                continue
            new = N.normalize(b["text_raw"])
            if new != b.get("text"):
                print(f"{ch} {b['id']}: {b.get('text')!r} -> {new!r}")
                b["text"] = new
                changed += 1
        if changed:
            store.write(cdir / "bubbles.json", doc)
        print(f"{ch}: {changed} texts re-cleaned")
        total += changed
    print(f"{total} texts changed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
