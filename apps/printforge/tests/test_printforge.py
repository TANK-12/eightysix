"""PrintForge tests: STL reading, the print checks, the library rules and the API."""

import struct
import sys
from pathlib import Path

import numpy as np
import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import library  # noqa: E402
import stl  # noqa: E402

CUBE = [  # 12 outward-facing triangles of a 10 mm cube
    ((0, 0, 0), (0, 10, 0), (10, 10, 0)), ((0, 0, 0), (10, 10, 0), (10, 0, 0)),
    ((0, 0, 10), (10, 0, 10), (10, 10, 10)), ((0, 0, 10), (10, 10, 10), (0, 10, 10)),
    ((0, 0, 0), (10, 0, 0), (10, 0, 10)), ((0, 0, 0), (10, 0, 10), (0, 0, 10)),
    ((0, 10, 0), (0, 10, 10), (10, 10, 10)), ((0, 10, 0), (10, 10, 10), (10, 10, 0)),
    ((0, 0, 0), (0, 0, 10), (0, 10, 10)), ((0, 0, 0), (0, 10, 10), (0, 10, 0)),
    ((10, 0, 0), (10, 10, 0), (10, 10, 10)), ((10, 0, 0), (10, 10, 10), (10, 0, 10)),
]  # fmt: skip


def write_binary(path, tris):
    with open(path, "wb") as f:
        f.write(b"test".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<3f", 0, 0, 0))
            for v in t:
                f.write(struct.pack("<3f", *v))
            f.write(b"\0\0")


def write_ascii(path, tris):
    lines = ["solid t"]
    for t in tris:
        lines += ["facet normal 0 0 0", "outer loop"]
        lines += [f"vertex {x} {y} {z}" for x, y, z in t]
        lines += ["endloop", "endfacet"]
    lines.append("endsolid t")
    Path(path).write_text("\n".join(lines))


def moved(tris, dx):
    return [tuple((x + dx, y, z) for x, y, z in t) for t in tris]


@pytest.fixture
def roots(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTFORGE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("PRINTFORGE_CACHE_DIR", str(tmp_path / "cache"))
    models = tmp_path / "Models"
    (models / "mech" / "print" / "stl" / "1-35").mkdir(parents=True)
    write_binary(models / "mech" / "print" / "stl" / "1-35" / "cube.stl", CUBE)
    write_ascii(models / "mech" / "open.stl", CUBE[:-1])
    (tmp_path / "outside.stl").write_bytes(b"")
    library.save_settings({"roots": [str(models)]})
    return models


def test_binary_and_ascii_read_the_same(tmp_path):
    write_binary(tmp_path / "b.stl", CUBE)
    write_ascii(tmp_path / "a.stl", CUBE)
    b = stl.read_triangles(tmp_path / "b.stl")
    a = stl.read_triangles(tmp_path / "a.stl")
    assert b.shape == (12, 3, 3)
    assert np.allclose(a, b)
    assert stl.triangle_count(tmp_path / "b.stl") == 12
    assert stl.triangle_count(tmp_path / "a.stl") is None


def test_cube_is_watertight_one_piece_1_cm3():
    r = stl.analyse(np.array(CUBE, dtype=np.float32))
    assert r["watertight"] and r["shells"] == 1 and r["open_edges"] == 0
    assert r["size_mm"] == [10, 10, 10]
    assert r["volume_cm3"] == 1.0 and not r["inside_out"]
    assert r["area_cm2"] == 6.0


def test_missing_face_is_not_watertight():
    r = stl.analyse(np.array(CUBE[:-1], dtype=np.float32))
    assert not r["watertight"] and r["open_edges"] == 3


def test_two_cubes_are_two_shells():
    r = stl.analyse(np.array(CUBE + moved(CUBE, 20), dtype=np.float32))
    assert r["watertight"] and r["shells"] == 2 and r["volume_cm3"] == 2.0


def test_inside_out_is_flagged():
    flipped = [(t[0], t[2], t[1]) for t in CUBE]
    assert stl.analyse(np.array(flipped, dtype=np.float32))["inside_out"]


def test_fits():
    assert stl.fits([172, 241, 90], [256, 256, 256]) == {
        "upright": True,
        "any_orientation": True,
    }
    assert stl.fits([241, 172, 90], [218, 123, 220])["upright"] is False
    assert stl.fits([20, 150, 10], [153, 77, 165])["any_orientation"] is True


def test_scan_finds_files_and_scale(roots):
    files = library.scan()
    names = {f["name"]: f for f in files}
    assert set(names) == {"cube", "open"}
    assert names["cube"]["project"] == "mech"
    assert names["cube"]["folder"] == "print/stl/1-35"
    assert names["cube"]["scale"] == "1:35"
    assert names["cube"]["triangles"] == 12


def test_allowed_rejects_outside_and_non_stl(roots, tmp_path):
    with pytest.raises(ValueError):
        library.allowed(str(tmp_path / "outside.stl"))
    with pytest.raises(ValueError):
        library.allowed(str(roots / "mech" / ".." / ".." / "outside.stl"))
    (roots / "notes.txt").write_text("x")
    with pytest.raises(ValueError):
        library.allowed(str(roots / "notes.txt"))


def test_info_is_cached(roots, monkeypatch):
    p = roots / "mech" / "print" / "stl" / "1-35" / "cube.stl"
    first = library.info(p)
    monkeypatch.setattr(stl, "analyse", lambda t: pytest.fail("cache missed"))
    assert library.info(p) == first


def test_settings_reject_bad_roots(roots):
    with pytest.raises(ValueError):
        library.save_settings({"roots": "not a list"})


def test_api(roots, tmp_path):
    from fastapi.testclient import TestClient

    import web_app

    c = TestClient(web_app.app)
    lib = c.get("/api/library").json()
    assert {f["name"] for f in lib["files"]} == {"cube", "open"}
    cube = next(f for f in lib["files"] if f["name"] == "cube")["path"]
    info = c.get("/api/info", params={"path": cube}).json()
    assert info["watertight"] and info["scale"] == "1:35"
    assert info["fits"]["filament 256 class"]["upright"]
    body = c.get("/api/stl", params={"path": cube})
    assert body.status_code == 200 and len(body.content) == 84 + 12 * 50
    assert (
        c.get("/api/stl", params={"path": str(tmp_path / "outside.stl")}).status_code
        == 404
    )
    s = c.post("/api/settings", json={"values": {"advanced_mode": True}}).json()
    assert s["advanced_mode"] is True
    assert c.get("/").status_code == 200
    assert c.get("/shared/vendor/three/three.module.min.js").status_code == 200


@pytest.mark.parametrize(
    "values",
    [
        {"light": "abc"},
        {"light": True},
        {"light": 99},
        {"beds": {}},
        {"beds": {"x": [1, 2]}},
        {"beds": {"x": [10, 10, "a"]}},
        {"bed": 5},
        {"color": "red; background:url(x)"},
        {"advanced_mode": "yes"},
        {"roots": ["ok", 3]},
        {"roots": ["x"] * 65},
    ],
)
def test_settings_refuse_wrong_types(roots, values):
    before = library.load_settings()
    with pytest.raises(ValueError):
        library.save_settings(values)
    assert library.load_settings() == before


def test_bad_stored_settings_fall_back_per_key(roots):
    (library.config_dir() / "settings.json").write_text(
        '{"light": "abc", "beds": {}, "bed": "gone", "color": "#123456"}'
    )
    s = library.load_settings()
    assert s["light"] == 1.0 and s["beds"] == library.DEFAULTS["beds"]
    assert s["bed"] in s["beds"] and s["color"] == "#123456"
    (library.config_dir() / "settings.json").write_text("[1, 2]")
    assert library.load_settings()["light"] == 1.0


def test_unknown_bed_falls_back_to_the_first(roots):
    s = library.save_settings({"bed": "no such bed"})
    assert s["bed"] == next(iter(s["beds"]))


def test_api_answers_bad_files_calmly(roots, tmp_path):
    from fastapi.testclient import TestClient

    import web_app

    models = tmp_path / "Models"
    (models / "junk.stl").write_text("solid x\nvertex 1 2\nendsolid\n")
    nan = [((0, 0, 0), (float("nan"), 0, 0), (0, 1, 0))]
    write_binary(models / "nan.stl", nan)
    (models / "empty.stl").write_bytes(b"")
    c = TestClient(web_app.app)
    for name in ("junk", "nan"):
        r = c.get("/api/info", params={"path": str(models / f"{name}.stl")})
        assert r.status_code == 422 and "could not read" in r.json()["detail"]
    r = c.get("/api/info", params={"path": str(models / "empty.stl")})
    assert r.status_code == 200 and r.json()["triangles"] == 0
    r = c.get("/api/info", params={"path": "/" + "a" * 5000 + ".stl"})
    assert r.status_code == 404
    r = c.post("/api/settings", json={"values": {"light": "abc"}})
    assert r.status_code == 422 and "light" in r.json()["detail"]
    r = c.post("/api/settings", json={"values": "nope"})
    assert r.status_code == 422


# U1 sweep critic follow-up (2026-10-08)


@pytest.mark.parametrize(
    "route,body",
    [
        ("/api/settings", b"1e999"),
        ("/api/settings", b'{"values": 1e999}'),
        ("/api/settings", b'{"values": NaN}'),
        ("/api/open-folder", b'{"path": 1e999}'),
    ],
)
def test_infinity_and_nan_bodies_are_a_422(roots, route, body):
    from fastapi.testclient import TestClient

    import web_app

    c = TestClient(web_app.app, raise_server_exceptions=False)
    r = c.post(route, content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 422, r.text


def test_links_and_fifos_in_a_root_skip_only_themselves(roots, tmp_path):
    import os

    (roots / "out.stl").symlink_to(tmp_path / "outside.stl")
    (roots / "broken.stl").symlink_to(tmp_path / "gone.stl")
    os.mkfifo(roots / "pipe.stl")
    names = {f["name"] for f in library.scan()}
    assert names == {"cube", "open"}


def test_unexpandable_home_root_is_refused_and_skipped(roots):
    with pytest.raises(ValueError):
        library.save_settings({"roots": ["~nosuchuserxyz/models"]})
    s = library.load_settings()
    assert library.roots({**s, "roots": ["~nosuchuserxyz/m", str(roots)]}) == [
        roots.resolve()
    ]
