"""Which tools may run from a spoken command: each tool's own `voice` field.

Deny by default: a tool without the field never runs from voice. The two lists
below are pinned on purpose, so adding a voice tool or changing a field is a
deliberate edit here too. No tool with side effects really runs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acchan import registry, router, voice_command  # noqa: E402

registry.load_all()

# blender_render, blender_export_stl and godot_new_project passed the old name
# pattern; they are 'no' since 2026-10-08 (a misheard word must not start a long
# GPU job or write files).
VOICE_OK = [
    "app_controls",
    "ask_course",
    "ask_document",
    "assets_get",
    "assets_local",
    "assets_search",
    "blender_launch",
    "blender_print_check",
    "blender_scene",
    "blender_viewport_shot",
    "bluetooth",
    "browser_tabs",
    "calculate",
    "course_topics",
    "document_info",
    "find_files",
    "find_on_page",
    "focus_window",
    "forge_browser",
    "fullscreen_window",
    "godot_check",
    "godot_open",
    "godot_play",
    "list_accounts",
    "list_apps",
    "list_dir",
    "list_windows",
    "lock_screen",
    "look_at_screen",
    "make_folder",
    "media_control",
    "media_seek",
    "move_window",
    "navigate",
    "notify",
    "now_playing",
    "open_account",
    "open_web",
    "page_open",
    "page_read",
    "page_screenshot",
    "page_tabs",
    "play_media",
    "read_document",
    "read_file",
    "read_screen",
    "read_web_page",
    "read_window_text",
    "recall",
    "remember",
    "remind_me",
    "scroll",
    "search_text",
    "set_brightness",
    "set_volume",
    "shell_list",
    "shell_read",
    "shell_show",
    "switch_tab",
    "switch_workspace",
    "system_status",
    "take_screenshot",
    "terminal_switch_tab",
    "video_frame",
    "video_info",
    "video_transcript",
    "weather",
    "web_search",
    "what_time",
    "whats_on_screen",
    "wifi",
]
VOICE_FAST = ["launch_app", "open_item", "open_terminal", "terminal_new_tab"]

# The name pattern the guard used before the field existed (Relay task 113).
OLD_BLOCKED_PARTS = re.compile(
    r"(close|trash|delete|remove|move_path|write|edit|append|run|type|press|"
    r"keys|fill|click|send|clipboard|forget|convert)"
)


def by_level(level: str) -> list[str]:
    return sorted(n for n, t in registry.TOOLS.items() if t.voice == level)


def test_pinned_ok_and_fast_lists():
    assert by_level("ok") == VOICE_OK
    assert by_level("fast") == VOICE_FAST
    assert all(t.voice in registry.VOICE_LEVELS for t in registry.TOOLS.values())


def test_old_name_pattern_tools_are_no():
    matched = [n for n in registry.TOOLS if OLD_BLOCKED_PARTS.search(n)]
    assert matched
    for name in matched:
        assert registry.TOOLS[name].voice == "no", name
        assert voice_command.voice_blocked(name), name
        assert not voice_command.voice_agent_allowed(name), name


def test_risky_tools_are_no():
    risky = [n for n, t in registry.TOOLS.items() if t.risky]
    assert risky
    for name in risky:
        assert registry.TOOLS[name].voice == "no", name


def test_fast_tools_never_reach_the_model():
    for name in VOICE_FAST:
        assert not voice_command.voice_blocked(name), name
        assert not voice_command.voice_agent_allowed(name), name
    for name in VOICE_OK:
        assert voice_command.voice_agent_allowed(name), name
    assert voice_command.voice_blocked("no_such_tool")
    assert not voice_command.voice_agent_allowed("no_such_tool")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"risky": True, "voice": "ok"},
        {"risky": True, "voice": "fast"},
        {"voice": "yes"},
        {"voice": "OK"},
    ],
)
def test_tool_rejects_bad_voice(kwargs):
    before = set(registry.TOOLS)
    with pytest.raises(ValueError):
        registry.tool("test", **kwargs)
    assert set(registry.TOOLS) == before


@pytest.fixture
def unmarked_tool():
    ran = []

    @registry.tool("test", phrases=["zorblat the {thing}"])
    def zorblat_thing(thing: str) -> str:
        """Test only."""
        ran.append(thing)
        return "zorblatted"

    try:
        yield ran
    finally:
        registry.TOOLS.pop("zorblat_thing", None)


def test_unmarked_tool_refused_from_voice(monkeypatch, unmarked_tool):
    assert registry.TOOLS["zorblat_thing"].voice == "no"
    monkeypatch.setattr(router, "fast_path", lambda text: None)
    body = voice_command.handle("zorblat the widget", use_model=False)
    assert body["handled_by"] == "phrase"
    assert body["reply"] == voice_command.CONFIRM
    assert body["calls"][0]["tool"] == "zorblat_thing"
    assert unmarked_tool == []
    assert not voice_command.voice_agent_allowed("zorblat_thing")
    chat = voice_command.handle("zorblat the widget", use_model=False, source="chat")
    assert chat["calls"][0]["ok"] and unmarked_tool == ["widget"]


def test_close_tab_refused_and_time_answered(monkeypatch):
    real_run = voice_command._run
    ran = []

    def guarded_run(name, args):
        ran.append(name)
        if name != "what_time":
            raise AssertionError(f"{name} must not run in this test")
        return real_run(name, args)

    monkeypatch.setattr(voice_command, "_run", guarded_run)
    closed = voice_command.handle("close this tab", use_model=False)
    assert closed["reply"] == voice_command.CONFIRM and ran == []
    timed = voice_command.handle("what time is it", use_model=False)
    assert timed["handled_by"] in ("fast", "phrase")
    assert ran == ["what_time"] and re.search(r"\d", timed["reply"])


def test_a_spoken_picture_never_replaces_a_file(tmp_path, monkeypatch):
    """take_screenshot / blender_viewport_shot from voice: a new file or the
    tool's own default file, never a file that is already there."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "notes.md").write_text("mine")
    shots = tmp_path / "Pictures" / "Screenshots"
    shots.mkdir(parents=True)
    (shots / "acchan.png").write_bytes(b"the last shot")
    assert set(voice_command.WRITE_TOOLS) == {
        "take_screenshot",
        "blender_viewport_shot",
    }
    for name in sorted(voice_command.WRITE_TOOLS):
        refused = voice_command.voice_refusal(name, {"path": "~/notes.md"})
        assert refused == voice_command.NO_OVERWRITE.format(
            kind="file", name="notes.md"
        ), name
        assert voice_command.voice_refusal(name, {"path": "~/new.png"}) is None
        assert voice_command.voice_refusal(name, {}) is None
        assert voice_command.voice_refusal(name, {"path": "~"}) is not None
    again = {"path": "~/Pictures/Screenshots/acchan.png"}
    assert voice_command.voice_refusal("take_screenshot", again) is None
    assert voice_command.voice_refusal("blender_viewport_shot", again) is not None


def test_a_spoken_picture_counts_the_file_the_tool_really_saves(tmp_path, monkeypatch):
    """Blender's screenshot may save "notes" as notes.png, so that file counts
    as taken too; a folder is called a folder in the refusal."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "notes.png").write_bytes(b"mine")
    (tmp_path / "Docs").mkdir()
    bare = {"path": "~/notes"}
    assert voice_command.voice_refusal("blender_viewport_shot", bare) == (
        voice_command.NO_OVERWRITE.format(kind="file", name="notes.png")
    )
    assert voice_command.voice_refusal("take_screenshot", bare) is None
    other = {"path": "~/notes.jpg"}
    assert voice_command.voice_refusal("blender_viewport_shot", other) is not None
    for name in voice_command.WRITE_TOOLS:
        assert voice_command.voice_refusal(name, {"path": "~/Docs"}) == (
            voice_command.NO_OVERWRITE.format(kind="folder", name="Docs")
        ), name
