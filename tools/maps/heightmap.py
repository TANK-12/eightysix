"""Turn public elevation survey tiles (GeoTIFF, 1 m, one float band) into a streamed map's heightmap.

Writes <out>/height.f32 (n x n little-endian float32 metres above the crop's lowest point, row 0 at
the north edge, column 0 at the west edge, the format BigTerrain._load_heightmap reads), a shaded
preview.png to look at, and source.json (where it came from, the crop, the height range).

Usage: python3 tools/maps/heightmap.py <tile.tif> [<tile.tif> ...] <out dir> --size 4096 --points 2049
           [--centre highest | --centre COL,ROW | --centre-utm E,N] [--offset DX,DZ] [--source TEXT]
Several tiles side by side (e.g. 1 km state survey tiles) are joined into one mosaic by their
GeoTIFF positions first. --centre highest puts the crop around the highest point; --centre-utm puts
it on a projected (UTM) position; --offset then moves the crop (metres, +x east, +z south) so a
landmark need not sit dead in the middle. source.json records the crop's projected centre and UTM
zone, so tools/maps/osm_map.py can lay OpenStreetMap data onto the same ground.
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


def georef(tile: Path) -> dict:
    """Top-left corner (projected metres), pixel size and EPSG code of a GeoTIFF."""
    with Image.open(tile) as im:
        tags = getattr(im, "tag_v2")  # GeoTIFF tags (TiffImageFile only)
        tie = tags.get(33922)
        scale = tags.get(33550)
        keys = list(tags.get(34735) or [])
        epsg = 0
        for i in range(keys[3] if keys else 0):
            if keys[4 + i * 4] == 3072:
                epsg = keys[4 + i * 4 + 3]
        return {
            "x0": float(tie[3]),
            "y0": float(tie[4]),
            "px": float(scale[0]),
            "w": im.size[0],
            "h": im.size[1],
            "epsg": epsg,
        }


def utm_zone(epsg: int) -> int:
    """UTM zone of a NAD83 (269xx), ETRS89 (258xx) or WGS84 (326xx) UTM code, else 0."""
    for base in (26900, 25800, 32600):
        if base < epsg < base + 61:
            return epsg - base
    return 0


def mosaic(tiles: list[Path]) -> tuple[np.ndarray, dict]:
    """The tiles joined by their positions (all 1 m, same projection); gaps are no-data."""
    refs = [georef(t) for t in tiles]
    if len(tiles) == 1:
        return load(tiles[0]), refs[0]
    if len({r["epsg"] for r in refs}) != 1 or any(r["px"] != 1.0 for r in refs):
        raise SystemExit("mosaic: every tile must be 1 m in the same projection")
    x0 = min(r["x0"] for r in refs)
    y0 = max(r["y0"] for r in refs)
    w = int(round(max(r["x0"] + r["w"] for r in refs) - x0))
    h = int(round(y0 - min(r["y0"] - r["h"] for r in refs)))
    out = np.full((h, w), np.nan, dtype=np.float32)
    for t, r in zip(tiles, refs):
        c = int(round(r["x0"] - x0))
        row = int(round(y0 - r["y0"]))
        out[row : row + r["h"], c : c + r["w"]] = load(t)
    return out, {**refs[0], "x0": x0, "y0": y0, "w": w, "h": h}


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
    ap.add_argument("paths", type=Path, nargs="+", help="tile(s), then the out dir")
    ap.add_argument(
        "--size", type=int, default=4096, help="crop edge in metres (1 m pixels)"
    )
    ap.add_argument(
        "--points", type=int, default=2049, help="heightmap points per side"
    )
    ap.add_argument("--centre", default="highest")
    ap.add_argument("--centre-utm", default="", help="E,N in the tiles' projection")
    ap.add_argument("--offset", default="0,0")
    ap.add_argument("--source", default="")
    a = ap.parse_args()
    if len(a.paths) < 2:
        raise SystemExit("give at least one tile and the out dir")
    tiles, a.out = a.paths[:-1], a.paths[-1]
    dem, ref = mosaic(tiles)
    nodata = dem < -1000.0
    if nodata.any():
        dem = np.where(nodata, np.nan, dem)
    if a.centre_utm:
        e, n = (float(v) for v in a.centre_utm.split(","))
        col, row = int(round(e - ref["x0"])), int(round(ref["y0"] - n))
    elif a.centre == "highest":
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
    c0 = min(max(int(col) + dx - a.size // 2, 0), dem.shape[1] - a.size)
    r0 = min(max(int(row) + dz - a.size // 2, 0), dem.shape[0] - a.size)
    info = {
        "source": a.source or str(tiles[0].name),
        "tile": tiles[0].name if len(tiles) == 1 else [t.name for t in tiles],
        "crop_centre_px": [int(col) + dx, int(row) + dz],
        "epsg": ref["epsg"],
        "utm_zone": utm_zone(ref["epsg"]),
        "centre_utm": [
            round(ref["x0"] + (c0 + a.size / 2) * ref["px"], 1),
            round(ref["y0"] - (r0 + a.size / 2) * ref["px"], 1),
        ],
        "size_m": a.size,
        "points": a.points,
        "step_m": step,
        "relief_m": round(float(h.max()), 2),
    }
    (a.out / "source.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps(info))


if __name__ == "__main__":
    main()
