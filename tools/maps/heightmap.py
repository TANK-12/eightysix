"""Turn a public elevation survey tile (GeoTIFF, 1 m, one float band) into a streamed map's heightmap.

Writes <out>/height.f32 (n x n little-endian float32 metres above the crop's lowest point, row 0 at
the north edge, column 0 at the west edge, the format BigTerrain._load_heightmap reads), a shaded
preview.png to look at, and source.json (where it came from, the crop, the height range).

Usage: python3 tools/maps/heightmap.py <tile.tif> <out dir> --size 4096 --points 2049
           [--centre highest | --centre COL,ROW] [--offset DX,DZ] [--source TEXT]
--centre highest puts the crop around the tile's highest point; --offset then moves the crop (metres,
+x east, +z south) so a landmark need not sit dead in the middle.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def load(tile: Path) -> np.ndarray:
    with Image.open(tile) as im:
        if im.mode not in ("F", "I;16", "I"):
            raise SystemExit(f"{tile}: expected one float band, got mode {im.mode}")
        return np.asarray(im, dtype=np.float32)


def crop(dem: np.ndarray, centre: tuple[int, int], size: int) -> np.ndarray:
    col, row = centre
    half = size // 2
    c0 = min(max(col - half, 0), dem.shape[1] - size)
    r0 = min(max(row - half, 0), dem.shape[0] - size)
    return dem[r0 : r0 + size, c0 : c0 + size]


def resample(a: np.ndarray, points: int) -> np.ndarray:
    """Bilinear resample of a square array to points x points, corners kept."""
    n = a.shape[0]
    t = np.linspace(0.0, n - 1.0, points)
    i0 = np.clip(np.floor(t).astype(int), 0, n - 2)
    f = (t - i0).astype(np.float32)
    rows = a[i0] * (1 - f)[:, None] + a[i0 + 1] * f[:, None]
    return rows[:, i0] * (1 - f)[None, :] + rows[:, i0 + 1] * f[None, :]


def shade(h: np.ndarray, step: float) -> Image.Image:
    gz, gx = np.gradient(h, step)
    n = np.dstack([-gx, -gz, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    light = np.array([-0.5, -0.5, 0.7]) / np.linalg.norm([-0.5, -0.5, 0.7])
    lit = np.clip(n @ light, 0, 1)
    tint = (h - h.min()) / max(float(np.ptp(h)), 1e-3)
    rgb = (
        np.dstack([0.35 + 0.5 * tint, 0.45 + 0.35 * tint, 0.3 + 0.2 * tint])
        * lit[..., None]
    )
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("tile", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument(
        "--size", type=int, default=4096, help="crop edge in metres (1 m pixels)"
    )
    ap.add_argument(
        "--points", type=int, default=2049, help="heightmap points per side"
    )
    ap.add_argument("--centre", default="highest")
    ap.add_argument("--offset", default="0,0")
    ap.add_argument("--source", default="")
    a = ap.parse_args()
    dem = load(a.tile)
    nodata = dem < -1000.0
    if nodata.any():
        dem = np.where(nodata, np.nan, dem)
    if a.centre == "highest":
        row, col = np.unravel_index(np.nanargmax(dem), dem.shape)
    else:
        col, row = (int(v) for v in a.centre.split(","))
    dx, dz = (int(v) for v in a.offset.split(","))
    part = crop(dem, (int(col) + dx, int(row) + dz), a.size)
    if np.isnan(part).any():
        raise SystemExit(
            "the crop reaches the tile's no-data edge: move it with --offset"
        )
    h = resample(part, a.points)
    h -= h.min()
    a.out.mkdir(parents=True, exist_ok=True)
    h.astype("<f4").tofile(a.out / "height.f32")
    step = a.size / (a.points - 1)
    shade(h, step).save(a.out / "preview.png")
    info = {
        "source": a.source or str(a.tile.name),
        "tile": a.tile.name,
        "crop_centre_px": [int(col) + dx, int(row) + dz],
        "size_m": a.size,
        "points": a.points,
        "step_m": step,
        "relief_m": round(float(h.max()), 2),
    }
    (a.out / "source.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps(info))


if __name__ == "__main__":
    main()
