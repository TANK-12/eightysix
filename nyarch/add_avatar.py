#!/usr/bin/env python3
"""Add a Live2D model to Nyarch Assistant's avatar choices.

    python3 ~/Forge/nyarch/add_avatar.py ~/Downloads/maid-cat-girl.zip [Name]
    python3 ~/Forge/nyarch/add_avatar.py ~/Downloads/SomeModelFolder

Nyarch lists every folder under its live2d/web/models/ that holds a Cubism 3+
model (a *.model3.json). This unpacks a zip (or copies a folder), finds the
model3.json inside however deeply the author nested it, and installs that
folder under the given name, or the model file's own name. Nothing else in
Nyarch changes; pick the new avatar in Nyarch's settings afterwards.

Cubism 2 models (*.model.json) work too: Nyarch's viewer bundles both
runtimes and its handler lists both kinds.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

MODELS = (
    Path.home() / ".var/app/moe.nyarchlinux.assistant/config/avatars/live2d/web/models"
)


def find_model(root: Path) -> Path | None:
    hits = sorted(root.rglob("*.model3.json"), key=lambda p: len(p.parts))
    hits = hits or sorted(root.rglob("*.model.json"), key=lambda p: len(p.parts))
    return hits[0] if hits else None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    source = Path(sys.argv[1]).expanduser()
    if not source.exists():
        print(f"{source} does not exist")
        return 1
    with tempfile.TemporaryDirectory(prefix="nyarch-avatar-") as work:
        root = Path(work)
        if source.is_file() and zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as z:
                z.extractall(root)
        elif source.is_dir():
            shutil.copytree(source, root / source.name)
        else:
            print("Give a .zip file or a folder.")
            return 1
        model = find_model(root)
        if model is None:
            print(
                "No *.model3.json or *.model.json inside, so this is not a Live2D model."
            )
            return 1
        stem = model.name.removesuffix(".model3.json").removesuffix(".model.json")
        name = sys.argv[2] if len(sys.argv) > 2 else stem
        target = MODELS / name
        if target.exists():
            print(
                f"{target} already exists; pass a different name as the second argument."
            )
            return 1
        MODELS.mkdir(parents=True, exist_ok=True)
        shutil.copytree(model.parent, target)
    print(f"Installed {name} -> {target}")
    print("Open Nyarch's settings, Avatar, and pick it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
