"""Lay OpenStreetMap data onto a real-place map made by heightmap.py (whose source.json holds the
crop's projected centre and UTM zone). Writes, in the map's folder:
  osm.json   roads ({kind, width_m, points [[x, z], ...]}: real width x --road-scale) and buildings
             ({h, kind, levels, p [x0, z0, x1, z1, ...]}), world metres (+x east, +z south, centre 0, 0)
  woods.png  where trees may grow (white), one pixel per --woods-px metres, row 0 at the north edge
OSM data is (c) OpenStreetMap contributors, ODbL: credit it in assets/SOURCES.md.
Usage: python3 tools/maps/osm_map.py <map dir> [--raw /tmp/x.json] [--fetch] [--road-scale 1.3]
           [--woods default-on|default-off] [--woods-px 4] [--margin 60]
--fetch asks the Overpass API for the map's box and saves the answer to --raw; without it --raw is
read. default-on woods: trees everywhere except on other land use (fields, towns, water); default-off:
only inside OSM forest and wood.
"""

import argparse
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

OVERPASS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
AGENT = "eightysix-mapbuilder/0.1 (personal game)"
# real carriageway width (m) when the way has no width or lanes tag
WIDTHS = {
    "motorway": 11.0,
    "trunk": 9.0,
    "primary": 7.5,
    "secondary": 7.0,
    "tertiary": 6.5,
    "unclassified": 5.5,
    "residential": 5.5,
    "living_street": 5.0,
    "pedestrian": 6.0,
    "service": 4.0,
    "track": 3.5,
    "busway": 6.0,
    "raceway": 8.0,
}
for _k in ("motorway", "trunk", "primary", "secondary", "tertiary"):
    WIDTHS[_k + "_link"] = WIDTHS[_k] - 1.5
# metres per level and the levels a building has when OSM does not say
LEVEL_M = 3.0
LEVELS = {
    "apartments": 4,
    "residential": 3,
    "commercial": 3,
    "retail": 2,
    "office": 4,
    "school": 3,
    "hospital": 4,
    "hotel": 3,
    "church": 4,
    "chapel": 2,
    "garage": 1,
    "garages": 1,
    "shed": 1,
    "carport": 1,
    "hut": 1,
    "barn": 2,
    "farm_auxiliary": 2,
    "industrial": 2,
    "warehouse": 2,
}
SKIP_BUILDINGS = {"roof", "no", "ruins_no", "construction_site", "bridge", "carport"}
NOT_WOODS = {
    "farmland",
    "meadow",
    "grass",
    "residential",
    "commercial",
    "industrial",
    "retail",
    "quarry",
    "cemetery",
    "orchard",
    "allotments",
    "farmyard",
    "recreation_ground",
    "railway",
    "construction",
    "brownfield",
    "reservoir",
    "basin",
}


# --- UTM (Krüger series, GRS80/WGS84: the difference is far under a metre) ---
_A = 6378137.0
_F = 1 / 298.257222101
_K0 = 0.9996
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)


def to_utm(lat: float, lon: float, zone: int) -> tuple[float, float]:
    phi, lam = math.radians(lat), math.radians(lon)
    lam0 = math.radians(zone * 6 - 183)
    n = _A / math.sqrt(1 - _E2 * math.sin(phi) ** 2)
    t = math.tan(phi) ** 2
    c = _EP2 * math.cos(phi) ** 2
    a = math.cos(phi) * (lam - lam0)
    e2 = _E2
    m = _A * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * phi
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * phi)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * phi)
        - (35 * e2**3 / 3072) * math.sin(6 * phi)
    )
    east = (
        _K0
        * n
        * (
            a
            + (1 - t + c) * a**3 / 6
            + (5 - 18 * t + t * t + 72 * c - 58 * _EP2) * a**5 / 120
        )
        + 500000.0
    )
    north = _K0 * (
        m
        + n
        * math.tan(phi)
        * (
            a * a / 2
            + (5 - t + 9 * c + 4 * c * c) * a**4 / 24
            + (61 - 58 * t + t * t + 600 * c - 330 * _EP2) * a**6 / 720
        )
    )
    return east, north


def from_utm(east: float, north: float, zone: int) -> tuple[float, float]:
    """Inverse of to_utm by Newton steps (good to millimetres, enough for a bounding box)."""
    lat, lon = north / 111000.0, zone * 6 - 183 + (east - 500000.0) / 75000.0
    for _ in range(8):
        e, n = to_utm(lat, lon, zone)
        lat += (north - n) / 111000.0
        lon += (east - e) / (111000.0 * math.cos(math.radians(lat)))
    return lat, lon


# --- reading OSM ---


def fetch(box: tuple[float, float, float, float], raw: Path) -> None:
    s, w, n, e = box
    bb = f"({s:.5f},{w:.5f},{n:.5f},{e:.5f})"
    # land-use relations are left out: a forest multipolygon can span a whole region and stall the server
    query = f"""[out:json][timeout:180];
(
  way["highway"]{bb};
  way["building"]{bb};
  relation["building"]{bb};
  way["landuse"]{bb};
  way["natural"~"wood|water|scrub|heath|grassland"]{bb};
);
out geom;"""
    err: Exception | None = None
    for url in OVERPASS:
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode({"data": query}).encode(),
            headers={"User-Agent": AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                raw.write_bytes(r.read())
                return
        except OSError as e:  # busy server: try the next mirror
            err = e
    raise SystemExit(f"Overpass: {err}")


def rings(members: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Ways joined end to end into closed rings (multipolygon members come in pieces)."""
    open_ = [list(m) for m in members if len(m) >= 2]
    out = []
    while open_:
        ring = open_.pop()
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, m in enumerate(open_):
                if m[0] == ring[-1]:
                    ring += m[1:]
                elif m[-1] == ring[-1]:
                    ring += m[::-1][1:]
                elif m[-1] == ring[0]:
                    ring = m[:-1] + ring
                elif m[0] == ring[0]:
                    ring = m[::-1][:-1] + ring
                else:
                    continue
                open_.pop(i)
                changed = True
                break
        if len(ring) >= 4:
            out.append(ring)
    return out


def simplify(pts: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker."""
    if len(pts) < 3:
        return pts
    ax, az = pts[0]
    bx, bz = pts[-1]
    dx, dz = bx - ax, bz - az
    ln = math.hypot(dx, dz) or 1e-9
    worst, at = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = abs((pts[i][0] - ax) * dz - (pts[i][1] - az) * dx) / ln
        if d > worst:
            worst, at = d, i
    if worst <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[: at + 1], tol)[:-1] + simplify(pts[at:], tol)


def number(v: str | None) -> float | None:
    try:
        return float(str(v).split(";")[0].replace(",", ".").replace("m", "").strip())
    except (TypeError, ValueError):
        return None


def road_width(tags: dict) -> float | None:
    kind = tags.get("highway", "")
    if kind not in WIDTHS or tags.get("service") in ("driveway", "parking_aisle"):
        return None
    if tags.get("tunnel") in ("yes", "building_passage") or tags.get("area") == "yes":
        return None
    w = number(tags.get("width"))
    lanes = number(tags.get("lanes"))
    if w is None and lanes:
        w = lanes * 3.25
    if w is None or not 2.0 <= w <= 30.0:
        w = WIDTHS[kind]
    return w


def building_height(tags: dict) -> tuple[float, int]:
    kind = tags.get("building", "yes")
    lv = number(tags.get("building:levels"))
    levels = int(lv) if lv and 0 < lv < 40 else LEVELS.get(kind, 2)
    h = number(tags.get("height"))
    if h is None or not 2.0 <= h <= 120.0:
        h = levels * LEVEL_M + (1.0 if levels > 1 else 0.4)
    return round(h, 1), levels


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("map_dir", type=Path)
    ap.add_argument("--raw", type=Path, default=None)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--road-scale", type=float, default=1.3)
    ap.add_argument(
        "--woods", choices=("default-on", "default-off"), default="default-off"
    )
    ap.add_argument("--woods-px", type=float, default=4.0)
    ap.add_argument(
        "--margin", type=float, default=60.0, help="keep buildings this far in"
    )
    a = ap.parse_args()
    src = json.loads((a.map_dir / "source.json").read_text())
    zone = int(src["utm_zone"])
    ce, cn = src["centre_utm"]
    half = float(src["size_m"]) / 2
    raw = a.raw or Path("/tmp") / f"osm_{a.map_dir.name}.json"
    if a.fetch:
        corners = [
            from_utm(ce + sx * half, cn + sz * half, zone)
            for sx in (-1, 1)
            for sz in (-1, 1)
        ]
        lats = [c[0] for c in corners]
        lons = [c[1] for c in corners]
        fetch((min(lats), min(lons), max(lats), max(lons)), raw)
    data = json.loads(raw.read_text())

    def xz(g: dict) -> tuple[float, float]:
        e, n = to_utm(g["lat"], g["lon"], zone)
        return round(e - ce, 2), round(cn - n, 2)

    def inside(p: tuple[float, float], m: float) -> bool:
        return abs(p[0]) < half - m and abs(p[1]) < half - m

    roads, buildings = [], []
    px = int(round(src["size_m"] / a.woods_px))
    woods = Image.new("L", (px, px), 255 if a.woods == "default-on" else 0)
    draw = ImageDraw.Draw(woods)
    no_woods, yes_woods = [], []

    def to_px(r: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [((x + half) / a.woods_px, (z + half) / a.woods_px) for x, z in r]

    for el in data["elements"]:
        tags = el.get("tags", {})
        pts: list[tuple[float, float]] = []
        if el["type"] == "way":
            pts = [xz(g) for g in el.get("geometry", [])]
            outers, inners = [pts], []
        else:
            mem = el.get("members", [])
            outers = rings(
                [
                    [xz(g) for g in m.get("geometry", [])]
                    for m in mem
                    if m.get("role") == "outer" and m["type"] == "way"
                ]
            )
            inners = rings(
                [
                    [xz(g) for g in m.get("geometry", [])]
                    for m in mem
                    if m.get("role") == "inner" and m["type"] == "way"
                ]
            )
        if "highway" in tags and el["type"] == "way":
            w = road_width(tags)
            if w is None or len(pts) < 2:
                continue
            keep = [p for p in pts if inside(p, 4.0)]
            if len(keep) < 2:
                continue
            # cut at the map edge: keep the runs of points inside
            run: list[tuple[float, float]] = []
            for p in pts + [(1e9, 1e9)]:
                if inside(p, 4.0):
                    run.append(p)
                    continue
                if len(run) >= 2:
                    roads.append(
                        {
                            "kind": tags["highway"],
                            "width_m": round(w * a.road_scale, 2),
                            "points": [list(q) for q in simplify(run, 0.6)],
                        }
                    )
                run = []
        elif "building" in tags:
            if tags.get("building") in SKIP_BUILDINGS or tags.get("location") in (
                "underground",
            ):
                continue
            h, levels = building_height(tags)
            for ring in outers:
                if ring[0] == ring[-1]:
                    ring = ring[:-1]
                if len(ring) < 3 or not all(inside(p, a.margin) for p in ring):
                    continue
                k = len(ring) // 2
                ring = (
                    simplify(ring[: k + 1], 0.25)[:-1]
                    + simplify(ring[k:] + [ring[0]], 0.25)[:-1]
                )
                if len(ring) < 3:
                    continue
                buildings.append(
                    {
                        "h": h,
                        "levels": levels,
                        "kind": tags.get("building", "yes"),
                        "p": [c for p in ring for c in p],
                    }
                )
        else:
            lu = tags.get("landuse", "") or tags.get("natural", "")
            if lu in ("forest", "wood"):
                yes_woods.append((outers, inners))
            elif lu in NOT_WOODS or lu in ("water", "scrub", "heath", "grassland"):
                no_woods.append((outers, inners))
    for group, fill in ((no_woods, 0), (yes_woods, 255)):
        for outers, inners in group:
            for r in outers:
                if len(r) >= 3:
                    draw.polygon(to_px(r), fill=fill)
            for r in inners:
                if len(r) >= 3:
                    draw.polygon(to_px(r), fill=255 - fill)
    a.map_dir.mkdir(parents=True, exist_ok=True)
    woods.save(a.map_dir / "woods.png")
    out = {
        "_about": "OpenStreetMap data laid onto this map by tools/maps/osm_map.py: (c) OpenStreetMap contributors, ODbL. World metres, +x east, +z south.",
        "road_scale": a.road_scale,
        "roads": roads,
        "buildings": buildings,
    }
    (a.map_dir / "osm.json").write_text(json.dumps(out, separators=(",", ":")) + "\n")
    cover = sum(woods.histogram()[128:]) / (px * px)
    print(
        json.dumps(
            {
                "roads": len(roads),
                "road_points": sum(len(r["points"]) for r in roads),
                "buildings": len(buildings),
                "woods_cover": round(cover, 3),
            }
        )
    )


if __name__ == "__main__":
    main()
