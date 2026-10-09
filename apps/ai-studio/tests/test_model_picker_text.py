"""The Models panel shows plain names and descriptions, no technical figures.

Asks the real GET /api/models route (found by path, so a renamed handler
still gets checked) and sweeps every card of every kind.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as studio  # noqa: E402  # pyright: ignore[reportMissingImports]

TECHNICAL = re.compile(
    r"\d+(\.\d+)?\s*(px|gb|mb|kb)\b"
    r"|\b(sd1\.5|sdxl|vae|lora|cfg|unet|gguf|safetensors|vram|fp16|fp8|q4|q8)\b",
    re.I,
)
SHOWN = ("label", "blurb", "description", "run_note")  # what a card can show
HIDDEN = ("size_gb", "style", "name", "full_description")  # never sent
BRANDS = {"NVIDIA", "AMD", "JPEG", "PNG"}  # names, not shouting


def _cards() -> list[dict]:
    route = next(
        r
        for r in studio.app.routes
        if getattr(r, "path", "") == "/api/models"
        and "GET" in getattr(r, "methods", ())
    )
    out = route.endpoint()  # pyright: ignore[reportAttributeAccessIssue]
    return out["models"] if isinstance(out, dict) else out


def test_cards_carry_no_technical_figures():
    cards = _cards()
    assert cards, "the catalog is empty"
    for card in cards:
        for key in HIDDEN:
            assert key not in card, (card.get("id"), key)
        for key in SHOWN:
            text = card.get(key) or ""
            assert not TECHNICAL.search(text), (card.get("id"), key, text)
            shouting = set(re.findall(r"\b[A-Z]{3,}\b", text)) - BRANDS
            assert not shouting, (card.get("id"), key, text)


def test_every_card_has_a_label_and_words():
    for card in _cards():
        assert card.get("label"), card.get("id")
        assert card.get("blurb") or card.get("description"), card.get("id")
