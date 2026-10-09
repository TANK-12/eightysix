"""World catalog entries: valid per the plan's schema, plain card text."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import catalog  # noqa: E402  # pyright: ignore[reportMissingImports]
import worlds  # noqa: E402  # pyright: ignore[reportMissingImports]
from catalog import world  # noqa: E402  # pyright: ignore[reportMissingImports]
from worlds import runners  # noqa: E402  # pyright: ignore[reportMissingImports]

TECHNICAL = re.compile(
    r"\d+\s*(px|gb|mb|b)\b|\b(gb|mb|px|cuda|gpu|vram|gguf|vace|wan|safetensors"
    r"|pytorch|torch|sd1\.5|sdxl|vae|lora|cfg|unet|fp16|bf16|q8|nvidia)\b",
    re.I,
)


def test_world_entries_are_in_the_catalog_and_valid():
    ids = [e["id"] for e in world.ENTRIES]
    assert len(ids) == len(set(ids)) >= 2
    for eid in ids:
        entry = catalog.CATALOG[eid]
        catalog.validate(entry)
        assert entry["kind"] == "world"
        assert entry["tier"] in ("compact", "big")
        assert entry["engine"].startswith("world:")
        assert worlds.runner_for(entry) is not None, eid


def test_parts_have_real_urls_sizes_and_unique_names():
    for entry in world.ENTRIES:
        names = [p["filename"] for p in entry["parts"]]
        assert len(names) == len(set(names))
        for p in entry["parts"]:
            assert p["url"].startswith(
                ("https://huggingface.co/", "https://codeload.github.com/")
            ), p["url"]
            assert isinstance(p["size_bytes"], int) and p["size_bytes"] > 0
            if p["role"] == "code":
                assert re.search(r"/tar\.gz/[0-9a-f]{40}$", p["url"]), p["url"]
            if entry["engine"] != "world:walk-sd":
                assert p.get("dest"), (entry["id"], p["filename"])


def test_compact_world_fits_the_laptop():
    for entry in world.ENTRIES:
        total = sum(p["size_bytes"] for p in entry["parts"])
        if entry["tier"] == "compact":
            assert total < 20 * 1024**3, entry["id"]


def test_card_text_is_plain():
    for entry in world.ENTRIES:
        for text in (entry["label"], entry["blurb"]):
            assert not TECHNICAL.search(text), text


def test_runner_notes_are_plain():
    notes = [v for k, v in vars(runners).items() if k.startswith("NOTE_")]
    notes.append(worlds.NOTE_NO_RUNNER)
    assert len(notes) >= 6
    allowed = re.compile(r"\bNVIDIA\b")  # naming the card maker is the point
    for note in notes:
        assert not TECHNICAL.search(allowed.sub("", note)), note
    for label in worlds.ACTION_LABELS.values():
        assert not TECHNICAL.search(label), label
    assert set(worlds.ACTION_LABELS) == set(worlds.ACTIONS)
