"""Free 3D assets on demand: CC0 HDRI skies, photo textures and scanned models
from Poly Haven, downloaded once into ~/Forge/shared/assets and reused by
Blender (forge.use_hdri / forge.import_asset / forge.texture) and Godot.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated

from ..registry import ToolError, tool

SHARED = Path(os.environ.get("FORGE_SHARED_DIR", Path.home() / "Forge" / "shared"))
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

import forge_assets  # noqa: E402  # pyright: ignore[reportMissingImports]

TOOLSET = "assets"
TOOLSET_SUMMARY = (
    "Free CC0 3D assets: HDRI skies for lighting, photo textures and scanned"
    " models from Poly Haven, for Blender and Godot"
)
TOOLSET_KEYWORDS = ("asset", "hdri", "texture", "model", "polyhaven", "sky", "material")
TOOLSET_EXAMPLES = [
    (
        "find a sunset sky for my blender scene",
        "assets_search",
        {"kind": "hdris", "query": "sunset"},
    ),
]


@tool(TOOLSET, example={"kind": "models", "query": "rock"}, voice="ok")
def assets_search(
    kind: Annotated[str, "hdris, textures or models"],
    query: Annotated[str, "Words that must all match name, tags or category"] = "",
    limit: Annotated[int, "How many results"] = 12,
) -> str:
    """Search Poly Haven's free CC0 assets. Returns ids to pass to assets_get."""
    try:
        hits = forge_assets.search(kind, query, limit)
    except ValueError as e:
        raise ToolError(str(e)) from e
    if not hits:
        return f"No {kind} match '{query}'. Try fewer or broader words."
    return "\n".join(
        f"{h['id']}  ({h['name']}; {', '.join(h['tags'])})"
        + ("  [downloaded]" if h["cached"] else "")
        for h in hits
    )


@tool(TOOLSET, example={"asset_id": "abandoned_bakery", "res": "1k"}, voice="ok")
def assets_get(
    asset_id: Annotated[str, "Id from assets_search"],
    res: Annotated[str, "Resolution: 1k (default, small), 2k or 4k"] = "1k",
) -> str:
    """Download one asset (once; later calls reuse it) and return its manifest.
    "main" is the file to load in Blender or Godot."""
    try:
        return json.dumps(forge_assets.get(asset_id, res), indent=1)
    except ValueError as e:
        raise ToolError(str(e)) from e


@tool(TOOLSET, show=True, voice="ok")
def assets_local() -> str:
    """List assets already downloaded, with their kind and main file."""
    got = forge_assets.local()
    if not got:
        return "No assets downloaded yet."
    return "\n".join(f"{m['id']} [{m['kind']}, {m['res']}] {m['main']}" for m in got)
