"""The Python half of Garden: the garden file, the routes, real-time growth,
bad input, and the play.py commands. The clock is injected, never slept on."""

from __future__ import annotations

import importlib.util
import json
import struct
import threading
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
CURIO = HERE.parent
STARTERS = json.loads((CURIO / "starters.json").read_text(encoding="utf-8"))
API = "/api/curio/garden"
HEAD = {"X-Forge": "1"}
ODD = [
    'say "hi"',
    "a/b\\c",
    "../../etc/passwd",
    "🌱 sprout 🔥",
    "<b>bold</b>",
    "O'Neil & co",
    "null",
]


@pytest.fixture
def m(load_curio):
    return load_curio("garden")


@pytest.fixture
def client():
    import web_app

    return TestClient(web_app.app, raise_server_exceptions=False)


@pytest.fixture
def clock(m, monkeypatch):
    """Sets the garden's clock: clock.now is what datetime.now() returns."""

    class Clock:
        now = datetime(2026, 10, 9, 21, 0, tzinfo=timezone(timedelta(hours=1)))

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return Clock.now if tz is None else Clock.now.astimezone(tz)

    monkeypatch.setattr(m, "datetime", FakeDatetime)
    return Clock


def fresh_module():
    """A second, separate import of server.py, as a restarted app would have."""
    spec = importlib.util.spec_from_file_location(
        "garden_fresh_copy", CURIO / "server.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files_under(folder: Path) -> set[str]:
    return {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()}


def png_info(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    idat = data.index(b"IDAT")
    (n,) = struct.unpack(">I", data[idat - 4 : idat])
    return w, h, len(zlib.decompress(data[idat + 4 : idat + 4 + n]))


def test_nothing_happens_at_import(m, data_dir):
    before = threading.active_count()
    fresh_module()
    assert not data_dir.exists()
    assert threading.active_count() == before
    assert set(m.COMMANDS) == {"look", "plant", "cross", "render"}


def test_starters_appear_once_on_a_fresh_data_folder(m, data_dir):
    results: list[int] = []

    def first_look():
        results.append(len(m.load_garden()["plants"]))

    threads = [threading.Thread(target=first_look) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    want = [p["name"] for p in STARTERS["plants"]]
    assert results == [len(want)] * 8
    for _ in range(3):
        assert [p["name"] for p in m.load_garden()["plants"]] == want
    assert [p["id"] for p in m.load_garden()["plants"]] == ["p1", "p2", "p3", "p4"]
    assert files_under(data_dir) == {"garden/garden.json"}


def test_routes_need_the_header_for_writes(client, data_dir):
    r = client.get(f"{API}/plants")
    assert r.status_code == 200
    body = r.json()
    assert len(body["plants"]) == 4 and body["max"] == 40
    for path, payload in (
        ("plant", {"name": "Sneaky"}),
        ("cross", {"a": "p1", "b": "p2", "name": "Sneaky"}),
        ("rename", {"id": "p1", "name": "Sneaky"}),
    ):
        r = client.post(f"{API}/{path}", json=payload)
        assert r.status_code == 403, path
    assert len(client.get(f"{API}/plants").json()["plants"]) == 4


def test_plant_cross_and_rename_persist_across_a_fresh_load(client, data_dir):
    r = client.post(
        f"{API}/plant",
        json={"name": "Test fern", "by": "pytest", "seed": 7},
        headers=HEAD,
    )
    assert r.status_code == 200, r.text
    planted = r.json()
    assert (
        planted["id"] == "p5"
        and planted["by"] == "pytest"
        and planted["parents"] is None
    )
    r = client.post(
        f"{API}/cross",
        json={"a": "p1", "b": "Dusk willow", "name": "Ember willow", "seed": 125},
        headers=HEAD,
    )
    assert r.status_code == 200, r.text
    child = r.json()
    assert child["id"] == "p6"
    assert child["parents"] == [
        {"id": "p1", "name": "Ember fern"},
        {"id": "p3", "name": "Dusk willow"},
    ]
    r = client.post(
        f"{API}/rename", json={"id": "p5", "name": "Renamed fern"}, headers=HEAD
    )
    assert r.status_code == 200 and r.json()["name"] == "Renamed fern"

    again = fresh_module().load_garden()
    names = {p["id"]: p["name"] for p in again["plants"]}
    assert names["p5"] == "Renamed fern" and names["p6"] == "Ember willow"
    assert again["next_id"] == 7
    assert {p["id"]: p for p in again["plants"]}["p6"]["genome"] == child["genome"]
    assert files_under(data_dir) == {"garden/garden.json"}


def test_crossing_is_fixed_by_its_seed_and_takes_after_the_parents(m):
    garden = m.load_garden()
    a, b = garden["plants"][0]["genome"], garden["plants"][2]["genome"]
    assert m.cross(a, b, 9) == m.cross(a, b, 9)
    for seed in range(60):
        child = m.cross(a, b, seed)
        assert m.clean_genome(child) == child
        assert 1 <= m.effective_max_gen(child) <= child["max_gen"]
        for sym, variants in child["rules"].items():
            parents = set(a["rules"].get(sym, [])) | set(b["rules"].get(sym, []))
            assert parents, sym
            for v in variants:  # a parent's version, or one with a single turn flipped
                assert any(one_turn_apart(v, p) for p in parents), (sym, v)


def one_turn_apart(v: str, p: str) -> bool:
    if len(v) != len(p):
        return False
    diff = [(x, y) for x, y in zip(v, p) if x != y]
    return not diff or (len(diff) == 1 and set(diff[0]) == {"+", "-"})


def test_growth_follows_the_real_clock(m, clock):
    plant = m.plant_seed("Clock fern", "pytest", seed=3)
    top = m.effective_max_gen(plant["genome"])
    hpg = plant["genome"]["hours_per_gen"]
    assert m.hours_grown(plant) == 0
    assert m.growth_stage(plant, top) == 0
    assert "generation 0 of" in m.describe(plant)
    last = 0.0
    for step in range(1, 200):
        clock.now += timedelta(hours=hpg / 4)
        stage = m.growth_stage(plant, top)
        assert last <= stage <= top
        last = stage
    assert last == top
    assert f"generation {top} of {top}" in m.describe(plant)
    clock.now -= timedelta(days=400)  # a clock set back never shrinks below zero
    assert m.growth_stage(plant, top) == 0


def test_a_plant_a_generation_later(m, clock):
    plant = m.plant_seed("Later fern", "pytest", seed=4)
    clock.now += timedelta(hours=plant["genome"]["hours_per_gen"] * 1.5)
    assert m.growth_stage(plant, 6) == pytest.approx(1.5)
    assert "generation 1 of" in m.describe(plant)
    assert m.stage_parts(1.5, 6)[0] == 2


@pytest.mark.parametrize(
    ("path", "payload", "status"),
    [
        ("plant", {"name": ""}, 400),
        ("plant", {"name": "   "}, 400),
        ("plant", {"name": "x" * 41}, 400),
        ("plant", {}, 422),
        ("plant", {"name": "Junk", "genome": "F[+X]"}, 422),
        ("plant", {"name": "Junk", "genome": {"rules": {"X": ["F["]}}}, 400),
        ("plant", {"name": "Junk", "genome": {"rules": {"X": ["f+x"]}}}, 400),
        ("plant", {"name": "Junk", "genome": {"rules": {"X": ["F\n"]}}}, 400),
        ("plant", {"name": "Junk", "genome": {"rules": {}}}, 400),
        (
            "plant",
            {
                "name": "Junk",
                "genome": {"rules": {"X": ["F"], "Y": ["F"], "Z": ["F"], "W": ["F"]}},
            },
            400,
        ),
        ("plant", {"name": "Junk", "genome": {"rules": {"XY": ["F"]}}}, 400),
        (
            "plant",
            {"name": "Junk", "genome": {"rules": {"X": ["F", "F", "F", "F"]}}},
            400,
        ),
        ("plant", {"name": "Junk", "genome": {"rules": {"X": ["F" * 61]}}}, 400),
        (
            "plant",
            {"name": "Junk", "genome": {"rules": {"X": ["F"]}, "flower": "tulip"}},
            400,
        ),
        (
            "plant",
            {"name": "Junk", "genome": {"rules": {"X": ["F"]}, "angle": "wide"}},
            400,
        ),
        (
            "plant",
            {"name": "Junk", "genome": {"rules": {"X": ["F"]}, "max_gen": True}},
            400,
        ),
        (
            "plant",
            {
                "name": "Junk",
                "genome": {"rules": {"X": ["F"]}, "hues": {"leaf": "green"}},
            },
            400,
        ),
        ("cross", {"a": "p1", "b": "p1", "name": "Self"}, 400),
        ("cross", {"a": "p1", "b": "ember fern", "name": "Self"}, 400),
        ("cross", {"a": "p1", "b": "p99", "name": "Orphan"}, 404),
        ("cross", {"a": "p1", "b": "p2", "name": ""}, 400),
        ("cross", {"a": "p1", "b": "p2", "name": "y" * 41}, 400),
        ("rename", {"id": "p99", "name": "Ghost"}, 404),
        ("rename", {"id": "p1", "name": " "}, 400),
        ("rename", {"id": "p1", "name": "z" * 500}, 400),
    ],
)
def test_bad_input_gets_a_clear_4xx(client, path, payload, status):
    r = client.post(f"{API}/{path}", json=payload, headers=HEAD)
    assert r.status_code == status, r.text
    assert r.json()["detail"]
    if status == 400:
        assert isinstance(r.json()["detail"], str) and len(r.json()["detail"]) > 8


@pytest.mark.parametrize(
    "field",
    [
        '"max_gen": Infinity',
        '"max_gen": NaN',
        '"seed": Infinity',
        '"angle": NaN',
        '"hues": {"leaf": Infinity}',
        '"seed": -Infinity',
    ],
)
def test_json_nan_and_infinity_are_refused_not_crashed_on(client, data_dir, field):
    assert client.get(f"{API}/plants").status_code == 200
    raw = '{"name": "Odd", "genome": {"rules": {"X": ["F[+X]FX"]}, ' + field + "}}"
    r = client.post(
        f"{API}/plant",
        content=raw,
        headers={**HEAD, "content-type": "application/json"},
    )
    assert r.status_code == 400, r.text
    text = (data_dir / "garden" / "garden.json").read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text


def test_a_genome_built_to_explode_is_capped_not_refused(m, client):
    genome = {"axiom": "F" * 20, "rules": {"F": ["F" * 60]}, "max_gen": 7}
    r = client.post(
        f"{API}/plant", json={"name": "Runaway", "genome": genome}, headers=HEAD
    )
    assert r.status_code == 200, r.text
    clean = r.json()["genome"]
    assert (
        m.effective_max_gen(clean) == 1
    )  # 1200 segments; the next step would be 72000
    text, _, reached = m.expand(clean, 7)
    assert reached == 1 and len(text) == 1200


def test_a_full_garden_says_so(m, client):
    for i in range(m.MAX_PLANTS - 4):
        m.plant_seed(f"Filler {i}", "pytest", seed=i)
    r = client.post(f"{API}/plant", json={"name": "One too many"}, headers=HEAD)
    assert r.status_code == 409 and "40" in r.json()["detail"]
    r = client.post(
        f"{API}/cross", json={"a": "p1", "b": "p2", "name": "Nor this"}, headers=HEAD
    )
    assert r.status_code == 409
    assert len(m.load_garden()["plants"]) == m.MAX_PLANTS


def test_planting_at_once_loses_nothing(m):
    m.load_garden()
    errors: list[BaseException] = []

    def plant(i: int):
        try:
            m.plant_seed(f"Race {i}", "pytest", seed=i)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=plant, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    plants = fresh_module().load_garden()["plants"]
    assert len(plants) == 20
    assert len({p["id"] for p in plants}) == 20
    assert {f"Race {i}" for i in range(16)} <= {p["name"] for p in plants}


def test_odd_names_are_kept_exactly_and_written_nowhere_else(client, data_dir):
    for name in ODD:
        r = client.post(
            f"{API}/plant", json={"name": name, "by": name, "seed": 1}, headers=HEAD
        )
        assert r.status_code == 200, (name, r.text)
        assert r.json()["name"] == name
    r = client.post(f"{API}/plant", json={"name": "🌱" * 40, "seed": 2}, headers=HEAD)
    assert r.status_code == 200, "forty emoji are forty characters"
    r = client.post(
        f"{API}/cross", json={"a": ODD[0], "b": ODD[1], "name": ODD[2]}, headers=HEAD
    )
    assert r.status_code == 200 and r.json()["parents"][0]["name"] == ODD[0]
    names = [p["name"] for p in client.get(f"{API}/plants").json()["plants"]]
    assert all(n in names for n in ODD)
    assert files_under(data_dir) == {"garden/garden.json"}


def test_an_id_wins_over_a_plant_named_like_one(m):
    m.rename_plant("p1", "p2")
    assert m.find_plant(m.load_garden(), "p2")["name"] == "Lantern bell"
    assert m.find_plant(m.load_garden(), "  P1 ")["id"] == "p1"


def test_a_broken_garden_file_is_a_400(client, data_dir):
    path = data_dir / "garden" / "garden.json"
    path.parent.mkdir(parents=True)
    for junk in ("{not json", '{"plants": 3}', "[]"):
        path.write_text(junk, encoding="utf-8")
        r = client.get(f"{API}/plants")
        assert r.status_code == 400, junk
        assert "garden" in r.json()["detail"]


def test_cli_look_plant_cross_and_render(capsys, data_dir):
    import play

    assert play.main(["garden", "look"]) == 0
    out = capsys.readouterr().out
    assert "4 plants" in out and "Ember fern" in out and "generation" in out
    assert (
        play.main(
            ["garden", "plant", "--name", 'A "quoted" / sprout 🌱', "--seed", "5"]
        )
        == 0
    )
    assert "Planted" in capsys.readouterr().out
    assert (
        play.main(
            [
                "garden",
                "cross",
                "p1",
                "Comet spire",
                "--name",
                "Comet fern",
                "--seed",
                "8",
            ]
        )
        == 0
    )
    assert "Ember fern x Comet spire" in capsys.readouterr().out
    genome = json.dumps({"rules": {"X": ["F[+X][-X]FX"]}, "max_gen": 4})
    assert play.main(["garden", "plant", "--name", "Mine", "--genome", genome]) == 0
    capsys.readouterr()
    assert play.main(["garden", "cross", "p1", "p1", "--name", "Self"]) == 1
    assert "Not done" in capsys.readouterr().out
    assert play.main(["garden", "plant", "--name", "Bad", "--genome", "{nope"]) == 1
    assert "not JSON" in capsys.readouterr().out
    for hour in ("3", "6", "12", "19.5", "-5", "30"):
        assert play.main(["garden", "render", "--hour", hour]) == 0
        printed = Path(capsys.readouterr().out.strip())
        assert printed == data_dir / "garden" / "render.png"
        w, h, raw = png_info(printed)
        assert (w, h) == (1200, 600) and raw == h * (1 + w * 3)
    assert files_under(data_dir) == {"garden/garden.json", "garden/render.png"}


def test_render_sky_follows_the_hour(m, data_dir):
    path = data_dir / "garden" / "render.png"
    tops = {}
    for hour in (2, 12, 19.5):
        m.render_png(path, width=80, height=40, hour=hour)
        data = path.read_bytes()
        idat = data.index(b"IDAT")
        (n,) = struct.unpack(">I", data[idat - 4 : idat])
        raw = zlib.decompress(data[idat + 4 : idat + 4 + n])
        tops[hour] = tuple(raw[1:4])  # first pixel after the filter byte
    assert tops[12][2] > tops[2][2] + 100, "day is far brighter blue than night"
    assert tops[2] != tops[19.5]
