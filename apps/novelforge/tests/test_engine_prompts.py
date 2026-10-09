"""What the prose prompts look like, and that a run never invents a chapter
plan. All with a fake client."""

from __future__ import annotations

import pytest
from conftest import make_engine, prose

from novelforge.memory import MemoryManager
from novelforge.project import Project


def _book(data_dirs, lines=None):
    p = Project("Hunter")
    p.bible.update(
        protagonist="Kang Jin-Woo",
        genre="Korean hunter",
        preset="kr-hunter",
        story_scope="oneshot",
        planned_books=1,
    )
    p.codex["characters"]["Yoo Soo-Ah"] = {"desc": "healer"}
    if lines:
        p.set_outline_lines(lines)
    p.save()
    return p


def _handler(system, user):
    if "scene beats" in user:
        return "1: Jin-Woo enters the Mapo gate\n2: Soo-Ah follows him down\n3: The boss wakes"
    if "Write the scene now" in user or "Write chapter" in user:
        return prose(seed=len(user) % 97)
    return "NONE"


def test_scene_prompt_has_the_voice_names_and_a_final_check(data_dirs):
    p = _book(
        data_dirs,
        ["Start | Jin-Woo enters the gate alone | he gains a skill | a window opens"],
    )
    eng, client, logs = make_engine(
        p,
        _handler,
        "small",
        settings={
            "auto_codex": False,
            "auto_summary": False,
            "auto_running_synopsis": False,
            "auto_open_threads": False,
        },
    )
    eng.run(1, 900)
    scene_calls = [c for c in client.calls if "Write the scene now" in c["user"]]
    assert scene_calls
    system = scene_calls[0]["system"]
    assert "Korean hunter" in system and "square brackets" in system
    assert "Kang Jin-Woo" in system and "Yoo Soo-Ah" in system
    assert "NEVER use these worn phrases" in system and "eyes widened" in system
    user = scene_calls[0]["user"]
    assert user.rstrip().endswith("Prose only, no headings or notes.")
    assert "FINAL CHECK:" in user and "CHAPTER 1 PLAN: Start |" in user
    assert scene_calls[0]["extra"]["cache_prompt"] is True
    # every scene of the chapter shares the same system prompt (prompt cache)
    assert len({c["system"] for c in scene_calls}) == 1
    assert Project("Hunter").chapter_count() == 1


def test_a_run_past_the_outline_stops_instead_of_inventing_a_plan(data_dirs):
    p = _book(
        data_dirs,
        ["Start | Jin-Woo enters the gate alone | he gains a skill | a window opens"],
    )

    def handler(system, user):
        if "WRITE CHAPTER" in user:
            return "garbage"
        return _handler(system, user)

    eng, client, logs = make_engine(
        p,
        handler,
        "tiny",
        settings={
            "auto_codex": False,
            "auto_summary": False,
            "auto_running_synopsis": False,
            "auto_open_threads": False,
        },
    )
    with pytest.raises(RuntimeError, match="outline stops at chapter 1"):
        eng.run(3, 900)
    q = Project("Hunter")
    assert q.chapter_count() == 1
    assert "Advance the story" not in " ".join(c["user"] for c in client.calls)


def test_world_document_opening_scales_with_the_budget(data_dirs):
    p = _book(data_dirs)
    p.bible["world_doc"] = " ".join(f"w{i}" for i in range(20000))
    small = MemoryManager(
        p,
        None,
        "m",
        {"ctx_size": 8192},
        lambda m: None,
        context_budget=24000,
        reply_tokens=2000,
    )
    big = MemoryManager(
        p,
        None,
        "m",
        {"ctx_size": 50000},
        lambda m: None,
        context_budget=35000,
        reply_tokens=3000,
    )
    small.build_context(1)
    big.build_context(1)
    assert 0 < small.world_words_included < big.world_words_included < 20000
    assert small.verbatim_from == 1
