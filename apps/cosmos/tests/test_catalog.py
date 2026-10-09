"""Packing the HYG catalog into the binary file the map reads."""

import csv
import gzip
import json
import math

import pytest

import build_star_catalog as bsc

COLUMNS = [
    "id", "hip", "proper", "dist", "mag", "absmag", "spect", "ci",
    "x", "y", "z", "bayer", "flam", "con", "lum",
]  # fmt: skip


def write_catalog(path, rows):
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: "" for c in COLUMNS} | row)


SAMPLE = [
    {"id": "0", "proper": "Sol", "dist": "0", "mag": "-26.7", "absmag": "4.85",
     "x": "0.000005", "y": "0", "z": "0"},
    # A star 10 pc away exactly at the north celestial pole.
    {"id": "1", "proper": "Pole Star", "dist": "10", "mag": "2", "absmag": "1",
     "ci": "0.6", "x": "0", "y": "0", "z": "10", "spect": "F7", "con": "UMi", "lum": "2500"},
    {"id": "2", "dist": "100000", "mag": "9", "absmag": "-16", "x": "1", "y": "1", "z": "1"},
    {"id": "3", "dist": "40", "mag": "", "absmag": "3", "x": "40", "y": "0", "z": "0"},
    {"id": "4", "bayer": "Alp", "con": "Cen", "dist": "1.3", "mag": "0", "absmag": "4.4",
     "x": "-0.5", "y": "-0.4", "z": "-1.1"},
    {"id": "5", "hip": "999", "dist": "20", "mag": "7", "absmag": "5.5",
     "ci": "1.2", "x": "20", "y": "0", "z": "0"},
]  # fmt: skip


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "hyg.csv.gz"
    write_catalog(path, SAMPLE)
    return path


def read_records(path):
    data = path.read_bytes()
    magic, version, count = bsc.HEADER.unpack_from(data)
    records = [
        bsc.RECORD.unpack_from(data, bsc.HEADER.size + i * bsc.RECORD.size)
        for i in range(count)
    ]
    assert len(data) == bsc.HEADER.size + count * bsc.RECORD.size
    return magic, version, records


def test_build_packs_real_stars_and_skips_the_sun_and_unusable_rows(source, tmp_path):
    result = bsc.build(source, tmp_path / "out")
    assert result == {"count": 3, "skipped": 2, "named": 2}

    magic, version, records = read_records(tmp_path / "out" / bsc.STARS_FILE)
    assert magic == b"CSTR" and version == 1
    x, y, z, absmag, mag, ci = records[0]
    eps = math.radians(23.4392911)
    # The celestial pole sits 23.44 degrees from the ecliptic pole, toward +y.
    assert x == pytest.approx(0, abs=1e-5)
    assert y == pytest.approx(10 * math.sin(eps), abs=1e-4)
    assert z == pytest.approx(10 * math.cos(eps), abs=1e-4)
    assert (absmag, mag) == (1.0, 2.0)
    assert ci == pytest.approx(0.6)
    assert records[1][5] == pytest.approx(bsc.DEFAULT_COLOR_INDEX)
    assert records[2][5] == pytest.approx(1.2)


def test_names_point_at_their_records(source, tmp_path):
    bsc.build(source, tmp_path / "out")
    names = json.loads((tmp_path / "out" / bsc.NAMES_FILE).read_text())
    assert names["count"] == 3
    assert "CC BY-SA 4.0" in names["credit"]
    by_name = {s["name"]: s for s in names["stars"]}
    assert set(by_name) == {"Pole Star", "Alp Cen"}
    assert by_name["Pole Star"]["i"] == 0 and by_name["Pole Star"]["proper"] is True
    assert by_name["Alp Cen"]["i"] == 1 and by_name["Alp Cen"]["proper"] is False
    assert by_name["Pole Star"]["lum"] == 2500


def test_main_refuses_to_write_to_an_unplugged_drive(
    source, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(bsc, "AN3_ROOT", tmp_path / "AN3")
    code = bsc.main(["--source", str(source), "--out", str(tmp_path / "AN3" / "stars")])
    assert code == 1
    assert "not mounted" in capsys.readouterr().out
    assert not (tmp_path / "AN3").exists()


def test_main_builds_and_keeps_a_copy_for_when_the_drive_is_out(
    source, tmp_path, monkeypatch
):
    monkeypatch.setattr(bsc, "CACHE_DIR", tmp_path / "cache")
    out = tmp_path / "out"
    assert bsc.main(["--source", str(source), "--out", str(out)]) == 0
    for name in (bsc.STARS_FILE, bsc.NAMES_FILE):
        assert (tmp_path / "cache" / name).read_bytes() == (out / name).read_bytes()
