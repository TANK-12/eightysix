"""Builds the mech surface textures listed in data/mech_surfaces.json (look part 3).

Each entry names an ambientCG CC0 set. The 1K JPG set is downloaded once into the shared
asset cache (~/Forge/shared/assets/ambientcg/<id>/) and turned into three textures in
assets/textures/mech/<entry>/: albedo.jpg (desaturated and brought to a set mean, so the
finish colour does the tinting), normal.jpg (OpenGL convention, as Godot wants) and orm.jpg
(R occlusion, G roughness brought to a mean of ROUGH_MEAN, so a finish's roughness reads as the
average it gets, B metalness). A .import beside each asks Godot for VRAM
compression and mipmaps. Usage: python3 tools/make_mech_textures.py [entry ...]
"""

import argparse
import io
import json
import pathlib
import urllib.request
import zipfile

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = pathlib.Path.home() / "Forge/shared/assets/ambientcg"
OUT = ROOT / "assets/textures/mech"
ROUGH_MEAN = 0.75  # scripts/look/finish.gd SURFACE_ROUGH_MEAN
MAPS = ("Color", "NormalGL", "Roughness", "Metalness", "AmbientOcclusion")
IMPORT = """[remap]

importer="texture"
type="CompressedTexture2D"

[params]

compress/mode=2
compress/normal_map={normal}
mipmaps/generate=true
detect_3d/compress_to=0
"""


def fetch(asset: str) -> pathlib.Path:
    """The cached 1K JPG maps of one ambientCG asset, downloaded on first use."""
    folder = CACHE / asset
    if (folder / f"{asset}_1K-JPG_Color.jpg").exists():
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    url = f"https://ambientcg.com/get?file={asset}_1K-JPG.zip"
    request = urllib.request.Request(url, headers={"User-Agent": "eightysix-tools/1.0"})
    with urllib.request.urlopen(request, timeout=60) as reply:
        data = reply.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if any(name.endswith(f"_{m}.jpg") for m in MAPS):
                (folder / name).write_bytes(z.read(name))
    (folder / "SOURCE.txt").write_text(
        f"ambientCG {asset}, CC0 1.0, https://ambientcg.com/a/{asset}\n"
    )
    return folder


def channel(folder: pathlib.Path, asset: str, name: str, fallback: float) -> np.ndarray:
    """One map as a float 0-1 array (greyscale), or a flat fallback when the set lacks it."""
    path = folder / f"{asset}_1K-JPG_{name}.jpg"
    if not path.exists():
        return np.full((1024, 1024), fallback, np.float32)
    return np.asarray(Image.open(path).convert("L"), np.float32) / 255.0


def albedo(colour: np.ndarray, desaturate: float, brightness: float) -> np.ndarray:
    """Pulls the colour toward its own grey, then scales it so the mean is brightness."""
    grey = colour @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    mixed = colour + (grey[..., None] - colour) * desaturate
    return np.clip(mixed * (brightness / max(float(mixed.mean()), 1e-4)), 0.0, 1.0)


def roughness(rough: np.ndarray) -> np.ndarray:
    """Keeps the map's variation but moves its mean to ROUGH_MEAN."""
    return np.clip(rough * (ROUGH_MEAN / max(float(rough.mean()), 1e-4)), 0.0, 1.0)


def build(entry_id: str, entry: dict) -> pathlib.Path:
    asset = str(entry["source"])
    folder = fetch(asset)
    out = OUT / entry_id
    out.mkdir(parents=True, exist_ok=True)
    colour = np.asarray(
        Image.open(folder / f"{asset}_1K-JPG_Color.jpg").convert("RGB"), np.float32
    )
    base = albedo(
        colour / 255.0,
        float(entry.get("desaturate", 0.0)),
        float(entry.get("brightness", 0.8)),
    )
    Image.fromarray((base * 255).astype(np.uint8)).save(out / "albedo.jpg", quality=92)
    Image.open(folder / f"{asset}_1K-JPG_NormalGL.jpg").convert("RGB").save(
        out / "normal.jpg", quality=95
    )
    orm = np.stack(
        [
            channel(folder, asset, "AmbientOcclusion", 1.0),
            roughness(channel(folder, asset, "Roughness", 0.5)),
            channel(folder, asset, "Metalness", 0.0),
        ],
        axis=-1,
    )
    Image.fromarray((orm * 255).astype(np.uint8)).save(out / "orm.jpg", quality=95)
    for name in ("albedo", "normal", "orm"):
        imp = out / f"{name}.jpg.import"
        if not imp.exists():
            imp.write_text(IMPORT.format(normal=1 if name == "normal" else 0))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().split("\n")[0])
    parser.add_argument("entries", nargs="*", help="entry ids (default: all)")
    args = parser.parse_args()
    data = json.loads((ROOT / "data/mech_surfaces.json").read_text())["entries"]
    for entry_id in args.entries or sorted(data):
        print(entry_id, "->", build(entry_id, data[entry_id]).relative_to(ROOT))


if __name__ == "__main__":
    main()
