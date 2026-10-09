"""The outline pipeline: fixed line format, checks, one-by-one retries, and
never any filler. Driven by a fake Jan client."""

from __future__ import annotations

import re

from conftest import make_engine, outline_line

from novelforge import outline
from novelforge.project import Project

NAMES = outline.name_tokens(["Kang Jin-Woo", "Yoo Soo-Ah"])
GOOD = (
    "Ten Floors Down | Jin-Woo carries Soo-Ah's pack through the flooded third floor "
    "of the Mapo gate | He learns the gate resets when its boss sees him | A second "
    "window opens that nobody else can read"
)


def good_line(c):
    return outline_line(c)


def why(*args, **kwargs) -> str:
    reason = outline.check_line(*args, **kwargs)
    assert reason, "expected the line to be rejected"
    return reason


def test_check_line_accepts_a_concrete_line_and_says_why_it_rejects():
    assert outline.check_line(GOOD, [], NAMES) is None
    assert "four parts" in why("Title | Jin-Woo fights a boss", [], NAMES)
    assert "vague" in why(
        "Trouble | Jin-Woo faces new challenges in the gate today | He grows | Something is coming",
        [],
        NAMES,
    )
    assert "names none" in why(
        "Trouble | A hunter carries the pack through the flooded floor of the gate | "
        "The gate resets | A second window opens",
        [],
        NAMES,
    )
    assert "repeats" in why(GOOD, [GOOD], NAMES)
    assert "example" in why(
        GOOD.replace("Soo-Ah's", "Do-Yun's"), [], NAMES, banned={"do-yun", "yun"}
    )
    assert "template" in why(
        "Title | <what happens: who does what, where> Jin-Woo | x y z | hook", [], NAMES
    )
    # a possessive and a dropped hyphen still count as the name
    assert outline.check_line(GOOD.replace("Jin-Woo", "Jin Woo"), [], NAMES) is None


def test_protagonist_name_keeps_hyphens_and_drops_traits():
    assert outline.protagonist_name("Kang Jin-Woo — stoic — proud") == "Kang Jin-Woo"
    assert outline.protagonist_name("Mira, a thief (27)") == "Mira"
    assert outline.protagonist_name("") == ""


def test_parse_batch_reads_numbered_or_bare_lines():
    raw = "Sure! Here you go:\n3. A | b c d | e | f\n**4. G | h i j | k | l**\n9. out | of | range | x"
    got = outline.parse_batch(raw, 3, 4)
    assert got == {3: "A | b c d | e | f", 4: "G | h i j | k | l"}
    bare = "- A | b | c | d\n- E | f | g | h"
    assert outline.parse_batch(bare, 5, 6) == {5: "A | b | c | d", 6: "E | f | g | h"}
    assert outline.parse_batch("<think>x</think>\n1. A | b | c | d", 1, 1) == {
        1: "A | b | c | d"
    }


def test_parse_outline_text_round_trips_a_hand_edit():
    lines = ["First | a | b | c", "Second line with no pipes"]
    assert outline.parse_outline_text(outline.render_outline(lines) + "\n\n") == lines
    assert outline.parse_outline_text("Chapter 3 - Hello\n  \n4: World") == [
        "Hello",
        "World",
    ]


def _project(data_dirs, name="Book"):
    p = Project(name)
    p.bible.update(
        protagonist="Kang Jin-Woo — stoic",
        genre="Korean hunter system",
        plot="Left to die in a gate, he wakes a system.",
        preset="kr-hunter",
    )
    p.codex["characters"]["Yoo Soo-Ah"] = {"desc": "healer"}
    p.save()
    return p


def asked_chapters(user):
    m = re.search(r"WRITE CHAPTERS (\d+) TO (\d+)", user)
    if m:
        return list(range(int(m.group(1)), int(m.group(2)) + 1))
    m = re.search(r"WRITE CHAPTER (\d+) of", user)
    return [int(m.group(1))] if m else []


def test_a_clean_run_plans_every_chapter_in_small_batches(data_dirs):
    p = _project(data_dirs)

    def handler(system, user):
        return "\n".join(f"{c}. {good_line(c)}" for c in asked_chapters(user))

    eng, client, logs = make_engine(p, handler, "tiny")
    text, lines = eng.build_outline(7)
    assert len(lines) == 7 and lines[0] == good_line(1)
    assert len(client.calls) == 3  # batches of 3 for a tiny model: 1-3, 4-6, 7
    assert "FORMAT:" in client.calls[0]["user"]
    assert client.calls[0]["user"].rstrip().endswith("nothing else.")
    assert "[hook]" in client.calls[0]["user"]
    saved = Project("Book")
    assert saved.bible["chapter_list"] == lines
    assert (
        len(saved.bible["chapter_roles"]) == 7
        and saved.bible["chapter_roles"][0] == "hook"
    )
    assert saved.bible["outline"].startswith(f"1. {good_line(1)}")


def test_a_bad_line_is_asked_for_again_alone_with_the_reason(data_dirs):
    p = _project(data_dirs)
    seen = []

    def handler(system, user):
        cs = asked_chapters(user)
        seen.append(cs)
        if len(cs) > 1:
            return "\n".join(
                f"{c}. "
                + (
                    "Filler | The hero faces new challenges | He grows | Something is coming"
                    if c == 2
                    else good_line(c)
                )
                for c in cs
            )
        return f"{cs[0]}. {good_line(cs[0])}"

    eng, client, logs = make_engine(p, handler, "tiny")
    _, lines = eng.build_outline(3)
    assert len(lines) == 3 and lines[1] == good_line(2)
    assert [2] in seen
    retry = next(c["user"] for c in client.calls if "WRITE CHAPTER 2 of" in c["user"])
    assert "vague" in retry and "rejected" in retry
    assert any("chapter 2 rejected" in ln for ln in logs)


def test_a_chapter_that_never_comes_right_stops_the_outline_without_filler(data_dirs):
    p = _project(data_dirs)

    def handler(system, user):
        return "\n".join(
            f"{c}. " + ("nonsense" if c == 3 else good_line(c))
            for c in asked_chapters(user)
        )

    eng, client, logs = make_engine(p, handler, "tiny")
    _, lines = eng.build_outline(6)
    assert lines == [good_line(1), good_line(2)]
    saved = Project("Book").bible
    assert saved["chapter_list"] == lines
    assert "Advance the central conflict" not in saved["outline"]
    assert any("Outline stopped at 2/6" in ln for ln in logs)

    # Continue outline picks up at the gap once the model behaves.
    eng2, _, _ = make_engine(
        Project("Book"),
        lambda s, u: "\n".join(f"{c}. {good_line(c)}" for c in asked_chapters(u)),
        "tiny",
    )
    _, lines2 = eng2.build_outline(6, keep_existing=True)
    assert lines2 == [good_line(c) for c in range(1, 7)]


def test_careful_mode_rewrites_the_chapter_the_editor_names(data_dirs):
    p = _project(data_dirs)

    def handler(system, user):
        if "weakest chapters" in user:
            return "2: it is a copy of chapter 1's setup"
        cs = asked_chapters(user)
        if cs == [2] and "an editor said" in user:
            return "2. Better Two | " + good_line(9).split(" | ", 1)[1]
        return "\n".join(f"{c}. {good_line(c)}" for c in cs)

    eng, _, logs = make_engine(p, handler, "small")
    _, lines = eng.build_outline(3, careful=True)
    assert lines[1].startswith("Better Two |")
    assert any("chapter 2 rewritten" in ln for ln in logs)


def test_the_planner_model_writes_the_outline(data_dirs):
    p = _project(data_dirs)
    eng, client, _ = make_engine(
        p,
        lambda s, u: "\n".join(f"{c}. {good_line(c)}" for c in asked_chapters(u)),
        "tiny",
        planner="big-27B",
    )
    eng.build_outline(2)
    assert {c["model"] for c in client.calls} == {"big-27B"}
