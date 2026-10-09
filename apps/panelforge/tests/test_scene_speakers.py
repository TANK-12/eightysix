"""scene speaker guesses: one rule per test, plus a sweep over tail angles."""

import math

from panelforge.scene import speakers

PANEL = {"id": "p1", "box": [0, 1000, 800, 600]}


def ch(cid, face, box=None):
    fx, fy, fw, fh = face
    return {
        "cast_id": cid,
        "extra_id": None,
        "face": face,
        "box": box or [fx - fw, fy - fh // 2, fw * 3, fh * 5],
    }


def bub(bid, order, box, kind="speech", tail=None, panel="p1"):
    return {
        "id": bid,
        "panel_id": panel,
        "order": order,
        "box": box,
        "kind": kind,
        "tail": tail,
    }


def test_caption_is_narrator_and_sfx_is_skipped():
    out = speakers.guess(
        [
            bub("b1", 1, [10, 1010, 200, 50], "caption"),
            bub("b2", 2, [10, 1100, 50, 50], "sfx"),
        ],
        {"p1": PANEL},
        {},
    )
    assert out["b1"]["speaker"] == "narrator"
    assert "b2" not in out


def test_tail_beats_nearest_face():
    chars = {"p1": [ch("c01", [100, 300, 80, 80]), ch("c02", [600, 300, 80, 80])]}
    # Bubble sits right above c01, but its tail points down-right at c02.
    b = bub("b1", 1, [80, 1050, 160, 80], tail=[400, 1200])
    out = speakers.guess([b], {"p1": PANEL}, chars)
    assert out["b1"]["speaker"] == "c02"
    assert out["b1"]["why"] == "tail points at face"


def test_tail_angle_sweep():
    """Tails aimed within 30 degrees of a face pick that face, from every side."""
    face = [380, 280, 40, 40]  # centre (400, 300)
    chars = {"p1": [ch("c01", face)]}
    for deg in range(0, 360, 15):
        r = 250
        cx = 400 + r * math.cos(math.radians(deg))
        cy = 300 + r * math.sin(math.radians(deg))
        box = [int(cx - 40), int(cy - 20) + 1000, 80, 40]
        for off in (-30, 0, 30):
            a = math.radians(deg + 180 + off)
            tail = [int(cx + 60 * math.cos(a)), int(cy + 60 * math.sin(a)) + 1000]
            out = speakers.guess([bub("b1", 1, box, tail=tail)], {"p1": PANEL}, chars)
            assert out["b1"]["why"] == "tail points at face", (deg, off)
        # Aimed away: the tail rule must not fire (single character rule does).
        a = math.radians(deg)
        tail = [int(cx + 60 * math.cos(a)), int(cy + 60 * math.sin(a)) + 1000]
        out = speakers.guess([bub("b1", 1, box, tail=tail)], {"p1": PANEL}, chars)
        assert out["b1"]["why"] == "only character in panel", deg


def test_single_character_panel():
    out = speakers.guess(
        [bub("b1", 1, [500, 1020, 100, 60])],
        {"p1": PANEL},
        {"p1": [ch("c03", [100, 300, 80, 80])]},
    )
    assert out["b1"] == {
        "speaker": "c03",
        "conf": 0.65,
        "why": "only character in panel",
    }


def test_joined_bubbles_share_speaker():
    chars = {"p1": [ch("c01", [100, 300, 80, 80]), ch("c02", [600, 300, 80, 80])]}
    b1 = bub("b1", 1, [60, 1050, 160, 80], tail=[140, 1260])
    b2 = bub("b2", 2, [230, 1060, 160, 80])  # 10 px gap, no tail
    out = speakers.guess([b1, b2], {"p1": PANEL}, chars)
    assert out["b1"]["speaker"] == out["b2"]["speaker"] == "c01"
    assert out["b2"]["why"] == "joined to the previous bubble"


def test_alternating_dialogue_in_two_shot_and_across_empty_panels():
    p2 = {"id": "p2", "box": [0, 1700, 800, 400]}
    chars = {"p1": [ch("c01", [100, 400, 80, 80]), ch("c02", [620, 400, 80, 80])]}
    b1 = bub("b1", 1, [80, 1050, 150, 80], tail=[140, 1390])  # c01 by tail
    b2 = bub("b2", 2, [330, 1300, 140, 60])  # centred between: alternate -> c02
    b3 = bub("b3", 3, [300, 1750, 150, 60], panel="p2")  # empty panel: alternate -> c01
    b4 = bub("b4", 4, [300, 1900, 150, 60], panel="p2")  # -> c02
    out = speakers.guess([b1, b2, b3, b4], {"p1": PANEL, "p2": p2}, chars)
    assert [out[k]["speaker"] for k in ("b1", "b2", "b3", "b4")] == [
        "c01",
        "c02",
        "c01",
        "c02",
    ]
    assert out["b2"]["why"] == "alternating dialogue"
    assert out["b3"]["why"] == "alternating dialogue"


def test_nearest_face_when_clear_and_no_evidence_when_empty():
    chars = {"p1": [ch("c01", [100, 300, 80, 80]), ch("c02", [650, 300, 80, 80])]}
    out = speakers.guess([bub("b1", 1, [60, 1100, 150, 80])], {"p1": PANEL}, chars)
    assert out["b1"]["speaker"] == "c01" and out["b1"]["why"] == "nearest face"
    out = speakers.guess([bub("b9", 1, [60, 1100, 150, 80])], {"p1": PANEL}, {})
    assert out["b9"] == {"speaker": None, "conf": 0.0, "why": "no evidence"}


def test_characters_without_identity_are_not_speakers():
    anon = ch(None, [100, 300, 80, 80])
    out = speakers.guess(
        [bub("b1", 1, [60, 1100, 150, 80])], {"p1": PANEL}, {"p1": [anon]}
    )
    assert out["b1"]["speaker"] is None
