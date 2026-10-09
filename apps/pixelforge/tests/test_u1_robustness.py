"""Wrong-shaped saves are refused with a reason, never a 500 or a half write.

U1 sweep (2026-10-08). Runs against temp art and content dirs and a dead Jan
URL; no route here asks Jan for anything.
"""

import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="pixelforge-test-")
ENV = {
    "FORGE_ART_DIR": os.path.join(TMP, "art"),
    "FORGE_CONTENT_DIR": os.path.join(TMP, "game"),
    "FORGE_JAN_SETTINGS_DIR": os.path.join(TMP, "jan"),
    "JAN_BASE_URL": "http://127.0.0.1:9/v1",
}
sys.path.insert(0, ROOT)

# Set only while importing (web_app makes its folders then) and inside each
# test, so test_janart still reads the real library it checks against.
_saved = {k: os.environ.get(k) for k in ENV}
os.environ.update(ENV)
from fastapi.testclient import TestClient  # noqa: E402

import web_app  # noqa: E402

for _k, _v in _saved.items():
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v

client = TestClient(web_app.app)


@pytest.fixture(autouse=True)
def temp_stores(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


def palettes():
    return sorted(os.listdir(os.path.join(TMP, "art", "palettes")))


@pytest.mark.parametrize(
    "pack",
    [
        {"id": "t1", "sprites": {"a": None}},
        {"id": "t1", "sprites": {"a": 5}},
        {"id": "t1", "sprites": {"a": {"w": 2, "h": 1, "frames": [None]}}},
    ],
)
def test_a_malformed_pack_is_refused_not_a_500(pack):
    res = client.post("/api/art/packs", json={"pack": pack})
    assert res.status_code == 422
    assert isinstance(res.json()["detail"], str)


def test_keep_sprite_with_a_bad_colour_writes_nothing():
    before = palettes()
    res = client.post(
        "/api/jan/art/keep-sprite",
        json={
            "pack": "zz",
            "name": "a",
            "rows": ["aa", "aa"],
            "palette": {"a": 5},
            "w": 2,
            "h": 2,
        },
    )
    assert res.status_code == 422
    assert palettes() == before


def test_keep_sprite_with_bad_rows_does_not_merge_its_colours():
    before = palettes()
    res = client.post(
        "/api/jan/art/keep-sprite",
        json={
            "pack": "zz",
            "name": "a",
            "rows": [1, 2],
            "palette": {"a": "#ffffff"},
            "w": 2,
            "h": 2,
        },
    )
    assert res.status_code == 422
    assert palettes() == before


def test_keep_sprite_good_drawing_still_saves():
    res = client.post(
        "/api/jan/art/keep-sprite",
        json={
            "pack": "good",
            "name": "box",
            "rows": ["ab", "ba"],
            "palette": {"a": "#ffffff", "b": "#000000"},
            "w": 2,
            "h": 2,
        },
    )
    assert res.status_code == 200, res.text
    with open(os.path.join(TMP, "art", "packs", "good.json"), encoding="utf-8") as f:
        assert json.load(f)["sprites"]["box"]["frames"][0]["rows"] == ["ab", "ba"]


@pytest.mark.parametrize(
    "body, why",
    [
        ({"rows": [3], "legend": {"a": 5}, "w": -1, "h": 10**9}, "1-64"),
        ({"rows": ["ab"], "legend": {"a": "floor_wood"}, "w": 2, "h": 1}, "no tile"),
        ({"rows": ["a"], "legend": {"a": "floor_wood"}, "w": 2, "h": 1}, "characters"),
        ({"rows": ["aa"], "legend": {"a": "floor_wood"}, "w": 2, "h": 2}, "rows"),
    ],
)
def test_keep_structure_refuses_bad_geometry(body, why):
    res = client.post(
        "/api/jan/art/keep-structure", json={"id": "s", "label": "L", **body}
    )
    assert res.status_code == 422
    assert why in res.json()["detail"]


def test_keep_structure_good_plan_saves():
    res = client.post(
        "/api/jan/art/keep-structure",
        json={
            "id": "hut",
            "label": "Hut",
            "rows": ["a.a"],
            "legend": {"a": "floor_wood"},
            "w": 3,
            "h": 1,
        },
    )
    assert res.status_code == 200, res.text


@pytest.mark.parametrize(
    "extra",
    [
        {"freq": "high"},
        {"duration": float("inf")},
        {"loop": "yes"},
        {"repeat": True},
        {"label": "x" * 201},
    ],
)
def test_a_sound_with_a_wrong_type_is_refused(extra):
    sound = {"id": "s1", "label": "a", "event": "x", **extra}
    res = client.post(
        "/api/sounds",
        content=json.dumps({"sound": sound}).replace("Infinity", "1e400"),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 422


def test_a_good_sound_saves_with_unicode_name():
    sound = {"id": "s2", "label": "猫 purr", "event": "x", "freq": 300, "loop": True}
    res = client.post("/api/sounds", json={"sound": sound})
    assert res.status_code == 200, res.text


# --- critic findings (G11 critic, 2026-10-08) ---------------------------------

SPRITE = {"w": 2, "h": 1, "frames": [{"ms": 0, "rows": [".."]}]}


@pytest.mark.parametrize(
    "pack",
    [
        {"id": "c1", "sprites": {"s": {**SPRITE, "tags": 5}}},
        {"id": "c1", "sprites": {"s": {**SPRITE, "tags": [None, 5]}}},
        {"id": "c1", "sprites": {"s": {**SPRITE, "frames": "x"}}},
        {"id": "c1", "sprites": {"s" * 300: SPRITE}},
        {"id": "c1", "label": "x" * 201, "sprites": {"s": SPRITE}},
        {"id": "c" * 300, "sprites": {"s": SPRITE}},
    ],
)
def test_pack_with_bad_tags_names_or_ids_is_refused(pack):
    res = client.post("/api/art/packs", json={"pack": pack})
    assert res.status_code == 422, res.text
    assert len(res.json()["detail"]) < 400  # no 200 kB echo


def test_a_bad_tags_file_on_disk_does_not_break_ask_jan():
    path = os.path.join(TMP, "art", "packs", "handmade.json")
    pack = {"id": "handmade", "sprites": {"floor_x": {**SPRITE, "tags": 5}}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pack, f)
    try:
        import janart

        assert "floor_x" in janart.tile_choices()
    finally:
        os.remove(path)


@pytest.mark.parametrize(
    "body",
    [
        {"pack": "a" * 300},
        {"name": "n" * 300},
        {"tags": [None, 5]},
        {"tags": "tile"},
    ],
)
def test_keep_sprite_refuses_long_ids_and_bad_tags(body):
    good = {
        "pack": "good",
        "name": "box",
        "rows": ["ab", "ba"],
        "palette": {"a": "#ffffff", "b": "#000000"},
        "w": 2,
        "h": 2,
    }
    before = palettes()
    res = client.post("/api/jan/art/keep-sprite", json={**good, **body})
    assert res.status_code == 422, res.text
    assert palettes() == before


@pytest.mark.parametrize(
    "extra", [{"id": "s" * 300}, {"source": "x" * 5000}, {"tags": [3]}]
)
def test_keep_structure_refuses_long_ids_source_and_bad_tags(extra):
    body = {
        "id": "hut",
        "label": "Hut",
        "rows": ["a"],
        "legend": {"a": "floor_wood"},
        "w": 1,
        "h": 1,
        **extra,
    }
    assert client.post("/api/jan/art/keep-structure", json=body).status_code == 422


@pytest.mark.parametrize(
    "extra", [{"label": "L" * 201}, {"description": "d" * 5000}, {"id": "w" * 300}]
)
def test_keep_world_refuses_huge_text(extra):
    # (a good body would save into the real worlds folder, so only the
    # refusal is driven here, and its reason must be the oversized field)
    body = {
        "id": "moon",
        "label": "Moon",
        "kind": "moon",
        "distance": "near",
        "colour": "#aabbcc",
        "description": "Grey and quiet.",
        **extra,
    }
    res = client.post("/api/jan/art/keep-world", json=body)
    assert res.status_code == 422
    assert next(iter(extra)) in res.json()["detail"]


def test_palette_roles_must_be_text_and_ids_short():
    for palette in (
        {"id": "p", "colors": {"a": "#ffffff"}, "roles": {"a": 5}},
        {"id": "p" * 300, "colors": {"a": "#ffffff"}},
    ):
        res = client.post("/api/art/palettes", json={"palette": palette})
        assert res.status_code == 422, res.text


def test_a_long_sound_id_is_refused_without_echoing_it():
    res = client.post("/api/sounds", json={"sound": {"id": "z" * 200000, "event": "x"}})
    assert res.status_code == 422
    assert len(res.json()["detail"]) < 200
