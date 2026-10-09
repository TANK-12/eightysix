"""Keepsakes and logbook pages on disk: naming, limits, seeds, nothing deleted."""

import json

import pytest

import kit
import store


@pytest.fixture
def curios(tmp_path):
    root = tmp_path / "curios"
    seeds = root / "garden" / "seeds"
    seeds.mkdir(parents=True)
    (seeds / "first-light.json").write_text(
        json.dumps(
            {
                "name": "First light",
                "author": "Claude",
                "made": "2026-10-01T10:00:00",
                "data": {"genome": "F"},
            }
        )
    )
    return root


def test_save_names_and_lists_newest_first(curios):
    a = store.save_keepsake(
        "garden", name="Moss Fern!", data={"x": 1}, curios_dir=curios
    )
    b = store.save_keepsake("garden", name="Moss fern", note="again", curios_dir=curios)
    assert a["slug"] == "moss-fern" and b["slug"] == "moss-fern-2"
    rows = store.list_keepsakes("garden", curios_dir=curios)
    assert [r["slug"] for r in rows][-1] == "first-light"
    assert {r["slug"] for r in rows} == {"moss-fern", "moss-fern-2", "first-light"}
    assert rows[-1]["seed"] is True and rows[0]["seed"] is False


def test_a_new_keepsake_never_takes_a_seed_name(curios):
    row = store.save_keepsake("garden", name="First light", curios_dir=curios)
    assert row["slug"] == "first-light-2"


def test_load_returns_data_and_seed_flag(curios):
    full = store.load_keepsake("garden", "first-light", curios_dir=curios)
    assert full["data"] == {"genome": "F"} and full["seed"] is True


def test_limits_are_refused(curios):
    with pytest.raises(store.StoreError):
        store.save_keepsake("garden", name="   ", curios_dir=curios)
    with pytest.raises(store.StoreError):
        store.save_keepsake("garden", name="x" * 81, curios_dir=curios)
    with pytest.raises(store.StoreError):
        store.save_keepsake(
            "garden", name="big", data="x" * (store.MAX_DATA + 1), curios_dir=curios
        )
    with pytest.raises(store.StoreError):
        store.save_keepsake("garden", name="pic", thumb="javascript:alert(1)")
    with pytest.raises(store.StoreError):
        store.save_keepsake("../etc", name="escape")


def test_path_tricks_find_nothing(curios):
    for slug in ("../../etc/passwd", "a/b", "", "UPPER", ".hidden"):
        with pytest.raises(store.NotFound):
            store.load_keepsake("garden", slug, curios_dir=curios)
    with pytest.raises(store.StoreError):
        store.load_keepsake("../garden", "first-light", curios_dir=curios)


def test_thumb_round_trip(curios):
    url = kit.png_data_url(2, 1, bytes([255, 0, 0, 0, 0, 255]))
    row = store.save_keepsake("garden", name="pic", thumb=url, curios_dir=curios)
    assert row["thumb"] == "/api/keepsakes/garden/pic/thumb"
    mime, data = store.thumb_bytes("garden", "pic", curios_dir=curios)
    assert mime == "image/png" and data.startswith(b"\x89PNG")
    with pytest.raises(store.NotFound):
        store.thumb_bytes("garden", "first-light", curios_dir=curios)


def test_put_away_moves_and_never_deletes(curios, data_dir):
    store.save_keepsake("garden", name="Weed", curios_dir=curios)
    moved = store.put_away("garden", "weed", curios_dir=curios)
    assert moved.is_file() and moved.parent.name == "put-away"
    assert "weed" not in {r["slug"] for r in store.list_keepsakes("garden", curios)}
    # the name stays taken, so a later keepsake does not reuse the put-away slug
    again = store.save_keepsake("garden", name="Weed", curios_dir=curios)
    assert again["slug"] == "weed-2"
    with pytest.raises(store.Conflict):
        store.put_away("garden", "first-light", curios_dir=curios)
    with pytest.raises(store.NotFound):
        store.put_away("garden", "weed", curios_dir=curios)


def test_edit_changes_name_and_note_but_not_seeds(curios):
    store.save_keepsake("garden", name="Old", curios_dir=curios)
    row = store.edit_keepsake(
        "garden", "old", name="New name", note="n", curios_dir=curios
    )
    assert row["name"] == "New name" and row["note"] == "n" and row["slug"] == "old"
    with pytest.raises(store.Conflict):
        store.edit_keepsake("garden", "first-light", name="x", curios_dir=curios)


def test_a_broken_file_is_skipped(curios, data_dir):
    folder = data_dir / "keepsakes" / "garden"
    folder.mkdir(parents=True)
    (folder / "broken.json").write_text("{not json")
    rows = store.list_keepsakes("garden", curios_dir=curios)
    assert [r["slug"] for r in rows] == ["first-light"]


def test_list_all_curios_reads_seeds_and_data(curios):
    store.save_keepsake("glyphs", name="Ripple", curios_dir=curios)
    ids = {r["id"] for r in store.list_keepsakes(curios_dir=curios)}
    assert ids == {"glyphs/ripple", "garden/first-light"}


def test_logbook_shipped_and_new_pages(tmp_path):
    shipped = tmp_path / "logbook"
    shipped.mkdir()
    (shipped / "2026-10-09-hello.json").write_text(
        json.dumps(
            {"title": "Hello", "body": "First page.", "made": "2026-10-09T09:00:00"}
        )
    )
    (shipped / "2026-10-09-empty.json").write_text(json.dumps({"body": "no title"}))
    page = store.add_page(
        "Second", "More.\n\nTwo paragraphs.", author="Claude (t)", curio="garden"
    )
    assert page["curio"] == "garden" and not page["shipped"]
    pages = store.list_pages(shipped_dir=shipped)
    assert [p["title"] for p in pages] == ["Second", "Hello"]
    with pytest.raises(store.StoreError):
        store.add_page("", "body")
    with pytest.raises(store.StoreError):
        store.add_page("t", "x" * (store.MAX_BODY + 1))


def test_png_writer_shape():
    png = kit.png_bytes(3, 2, bytes(18))
    assert (
        png[:8] == b"\x89PNG\r\n\x1a\n"
        and b"IHDR" in png
        and png.endswith(b"IEND\xaeB`\x82")
    )
    with pytest.raises(ValueError):
        kit.png_bytes(3, 2, bytes(17))
    assert kit.ramp(kit.EMBER, 0) == kit.EMBER[0]
    assert kit.ramp(kit.EMBER, 1) == kit.EMBER[-1]
