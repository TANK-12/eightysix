"""Genre presets are discovered from files and mapped onto chapters by code."""

from __future__ import annotations

import json

from novelforge import presets


def test_every_shipped_preset_loads_with_its_fields():
    found = presets.load_presets()
    assert len(found) >= 14
    for pid, p in found.items():
        assert p["id"] == pid
        assert p["label"] and p["voice"] and p["structure"]
        assert p["common_cliches"], "the shared worn-phrase list reaches every preset"
        assert all("role" in a and "at" in a for a in p["structure"])
    for pid in (
        "kr-hunter",
        "kr-rofan",
        "kr-murim",
        "jp-isekai",
        "cn-cultivation",
        "general",
    ):
        assert pid in found


def test_a_broken_file_is_skipped_and_common_is_not_a_preset(tmp_path):
    (tmp_path / "_common.json").write_text(json.dumps({"cliches": ["eyes widened"]}))
    (tmp_path / "good.json").write_text(
        json.dumps(
            {
                "id": "good",
                "label": "Good",
                "voice": ["x"],
                "structure": [{"at": 0, "role": "hook"}],
            }
        )
    )
    (tmp_path / "broken.json").write_text("{not json")
    (tmp_path / "partial.json").write_text(json.dumps({"id": "partial"}))
    found = presets.load_presets(str(tmp_path))
    assert list(found) == ["good"]
    assert found["good"]["common_cliches"] == ["eyes widened"]


def test_chapter_roles_cover_every_chapter_and_keep_key_beats():
    for p in presets.load_presets().values():
        keys = [a for a in p["structure"] if a.get("key")]
        for n in (1, 2, 3, 5, 8, 12, 20, 40, 100):
            roles = presets.chapter_roles(p["structure"], n)
            assert [r["chapter"] for r in roles] == list(range(1, n + 1))
            assert all(r["role"] and r["guide"] for r in roles)
            if n >= len(keys):
                got = {r["role"] for r in roles}
                assert {a["role"] for a in keys} <= got, (p["id"], n)
        roles = presets.chapter_roles(p["structure"], 30)
        first = min(p["structure"], key=lambda a: a["at"])
        last = max(p["structure"], key=lambda a: a["at"])
        assert roles[0]["role"] == first["role"]
        assert roles[-1]["role"] == last["role"]


def test_unclaimed_chapters_follow_the_previous_anchor():
    structure = [
        {"at": 0.0, "role": "hook", "guide": "open", "then": "grow", "key": True},
        {"at": 1.0, "role": "end", "guide": "close", "key": True},
    ]
    roles = presets.chapter_roles(structure, 4)
    assert [r["role"] for r in roles] == ["hook", "build", "build", "end"]
    assert roles[1]["guide"] == "grow"


def test_genre_text_picks_a_preset():
    all_ = presets.load_presets()
    assert (
        presets.guess_preset_id(
            "Korean Power Fantasy / LitRPG / Single-Heroine Romance", all_
        )
        == "kr-hunter"
    )
    assert presets.guess_preset_id("Murim regression", all_) == "kr-murim"
    assert presets.guess_preset_id("", all_) == "general"
    assert presets.preset_for_bible({"preset": "horror"})["id"] == "horror"
    assert (
        presets.preset_for_bible({"preset": "nope", "genre": "villainess rofan"})["id"]
        == "kr-rofan"
    )
