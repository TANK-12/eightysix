"""The Python half of Attractors: the same vectors.json the JS tests read,
the play.py commands, the PNG and the keepsake they write."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
V = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))


@pytest.fixture
def m(load_curio):
    return load_curio("attractors")


def close(a, b, tol, msg):
    if a is None or b is None:
        assert a == b, msg
    else:
        assert abs(a - b) <= tol, f"{msg}: {a} vs {b}"


def png_size(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    idat = data.index(b"IDAT")
    (n,) = struct.unpack(">I", data[idat - 4 : idat])
    return w, h, zlib.decompress(data[idat + 4 : idat + 4 + n])


def test_nothing_happens_at_import(m, data_dir):
    assert not data_dir.exists()
    assert set(m.COMMANDS) == {"hunt", "render", "keep"}


def test_rng_matches_the_kit(m):
    r = m.mulberry32(1)
    assert [r() for _ in V["rng_seed_1"]] == V["rng_seed_1"]


def test_named_cases(m):
    for c in V["cases"]:
        t = m.try_code(c["code"])
        assert t["result"]["status"] == c["status"], c["code"]
        assert t["result"]["at"] == c["at"]
        close(t["result"]["lyapunov"], c["lyapunov"], 1e-12, c["code"])
        close(t["dimension"], c["dimension"], 1e-12, c["code"])
        assert m.describe(t["result"]["lyapunov"], t["dimension"]) == c["describe"]


def test_sprotts_example_and_the_rejects(m):
    f = m.try_code("FIRCDERRPVLD")
    assert f["result"]["status"] == "chaotic" and f["result"]["lyapunov"] > m.CHAOS
    assert f["accepted"]
    assert m.try_code("MMMMMMMMMMMM")["result"]["status"] == "fixed"
    assert not m.try_code("MMMMMMMMMMMM")["accepted"]
    assert m.try_code("YYYYYYYYYYYY")["result"]["status"] == "escapes"
    for c in V["cases"]:
        if c["status"] != "chaotic":
            assert not m.try_code(c["code"])["accepted"], c["code"]


def test_sweep_of_400_codes(m):
    assert len(V["sweep"]) == 400
    seen = set()
    for s in V["sweep"]:
        t = m.try_code(s["code"])
        seen.add(t["result"]["status"])
        assert t["result"]["status"] == s["status"]
        assert t["accepted"] == s["accepted"]
        close(t["result"]["lyapunov"], s["lyapunov"], 1e-12, s["code"])
        close(t["dimension"], s["dimension"], 1e-12, s["code"])
        if t["accepted"]:
            assert t["result"]["lyapunov"] > m.CHAOS
            assert t["dimension"] >= m.MIN_DIMENSION
    assert seen == {"chaotic", "loop", "cycle", "fixed", "escapes"}


def test_hunts_match(m):
    for h in V["hunts"]:
        f = m.hunt(h["seed"])
        assert f is not None
        assert (f["code"], f["tried"]) == (h["code"], h["tried"])
    assert m.hunt(1, min_dimension=5, max_tries=3) is None


def test_codes(m):
    assert m.encode(m.decode("FIRCDERRPVLD")) == "FIRCDERRPVLD"
    assert m.decode("fircderrpvld") == m.decode("FIRCDERRPVLD")
    assert m.decode("AMY" + "M" * 9)[:3] == [-1.2, 0.0, 1.2]
    assert m.encode([5, -5, 0.04, 0.06, -0.04, 0, 0, 0, 0, 0, 0, 0]) == "YAMNMMMMMMMM"
    for bad in ["", "ABC", "FIRCDERRPVLDX", "FIRCDERRPVLZ", None, 12]:
        assert not m.is_code(bad)
        with pytest.raises(ValueError):
            m.decode(bad)  # type: ignore[arg-type]


def test_palettes_and_tone(m):
    pals = m.palettes()
    assert set(pals) == {"ember", "dusk", "ice", "ink"}
    assert all(len(p["stops"]) == 5 for p in pals.values())
    assert m.tone_index(0, 100) == 0
    assert m.tone_index(100, 100, 1.0, 1.0) == 255
    steps = [m.tone_index(c, 1000, 0.8, 1.7) for c in range(1, 1001)]
    assert steps == sorted(steps) and steps[-1] <= 255


def test_render_rgb(m):
    rgb = m.render_rgb(m.decode("JCFHLVWNJDLG"), 120, 80, 60000, "ink")
    assert len(rgb) == 120 * 80 * 3
    paper = tuple(m.palettes()["ink"]["stops"][0])
    assert tuple(rgb[:3]) == paper  # the corner is empty paper
    colours = {bytes(rgb[i : i + 3]) for i in range(0, len(rgb), 3)}
    assert len(colours) > 20
    with pytest.raises(ValueError):
        m.render_rgb(m.decode("YYYYYYYYYYYY"), 10, 10, 100)


def test_cli_hunt_writes_a_png(m, data_dir, capsys):
    assert m.cli_hunt(["--seed", "1"]) == 0
    out = capsys.readouterr().out
    assert "NJTGCYYAVCJP" in out and "Lyapunov exponent 0.289" in out
    assert "It looks like" in out
    path = data_dir / "attractors" / "NJTGCYYAVCJP.png"
    assert str(path) in out
    w, h, raw = png_size(path)
    assert (w, h) == (900, 600)
    assert len(raw) == h * (1 + w * 3)


def test_cli_hunt_keep_saves_a_keepsake(m, data_dir, capsys):
    import store

    assert m.cli_hunt(["--seed", "4", "--keep", "Seed four", "--note", "test"]) == 0
    rows = store.list_keepsakes("attractors")
    mine = [r for r in rows if not r["seed"]]
    assert [r["name"] for r in mine] == ["Seed four"]
    full = store.load_keepsake("attractors", mine[0]["slug"])
    assert full["data"]["code"] == V["hunts"][3]["code"]
    assert full["author"] == "Claude"
    assert full["thumb"]


def test_thumb_is_small(m):
    url = m.thumb_url(m.decode("JCFHLVWNJDLG"))
    assert url.startswith("data:image/png;base64,")
    assert len(url) < 200_000


def test_cli_render_and_keep(m, data_dir, capsys):
    import store

    assert m.cli_render(["FIRCDERRPVLD", "--size", "64x48", "--palette", "ice"]) == 0
    w, h, _ = png_size(data_dir / "attractors" / "FIRCDERRPVLD-ice.png")
    assert (w, h) == (64, 48)
    assert m.cli_render(["YYYYYYYYYYYY"]) == 1
    with pytest.raises(SystemExit):
        m.cli_render(["NOTACODE"])
    with pytest.raises(SystemExit):
        m.cli_render(["FIRCDERRPVLD", "--size", "big"])
    assert m.cli_keep(["FIRCDERRPVLD", "--name", "Sprott's own", "--note", "the book"]) == 0
    assert m.cli_keep(["YYYYYYYYYYYY", "--name", "Gone"]) == 1
    names = [r["name"] for r in store.list_keepsakes("attractors") if not r["seed"]]
    assert names == ["Sprott's own"]
    # nothing written outside the data folder
    assert all(str(p).startswith(str(data_dir)) for p in data_dir.rglob("*"))


def test_api_analyse(m):
    from fastapi import HTTPException

    res = m.api_analyse("fircderrpvld")
    assert res["status"] == "chaotic" and res["code"] == "FIRCDERRPVLD"
    assert len(res["describe"]) == 2
    with pytest.raises(HTTPException):
        m.api_analyse("nope")


def test_seeds_are_good(m):
    for path in sorted((HERE.parent / "seeds").glob("*.json")):
        assert path.stat().st_size < 100_000
        seed = json.loads(path.read_text(encoding="utf-8"))
        assert seed["author"] == "Claude" and seed["made"].startswith("2026-10-09T")
        f = m.try_code(seed["data"]["code"])
        assert f["accepted"], path.name
        assert f["coeffs"] == seed["data"]["coeffs"]
        assert seed["data"]["palette"] in m.palettes()
