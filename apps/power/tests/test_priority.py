import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import priority  # noqa: E402

GOOD = {"nice": 10, "background": ["claude"], "protected": ["important"]}


def test_default_when_no_file(tmp_path):
    cfg = priority.load_config(str(tmp_path / "priority.json"))
    assert cfg["nice"] == 10 and cfg["protected"] == []
    assert cfg["background"][0] == "claude"
    assert set(priority.preset_patterns(priority.load_presets())) <= set(
        cfg["background"]
    )
    assert priority._is_valid(cfg)


def test_shipped_presets_are_nonempty_and_valid():
    groups = priority.load_presets()
    assert len(groups) >= 5
    patterns = priority.preset_patterns(groups)
    assert len(patterns) >= 30
    assert all(len(p) <= 15 for p in patterns)  # ps truncates names to 15
    assert len(patterns) == len(set(patterns))


@pytest.mark.parametrize(
    "name",
    [
        "localsearch-3",
        "bazaar-dl-worke",
        "evolution-calen",
        "gvfs-udisks2-vo",
        "tracker-miner-f",
        "steamwebhelper",
    ],
)
def test_presets_catch_known_background_tasks(name):
    assert priority.matches(name, priority.preset_patterns(priority.load_presets()))


@pytest.mark.parametrize(
    "name",
    [
        "Hyprland",
        "firefox",
        "pipewire",
        "wireplumber",
        "gvfsd-fuse",
        "xdg-desktop-por",
        "gsd-media-keys",
        "python3",
        "steam",
        "evolution",
    ],
)
def test_presets_leave_foreground_and_core_alone(name):
    assert not priority.matches(name, priority.preset_patterns(priority.load_presets()))


def test_bad_presets_file_gives_no_groups(tmp_path):
    path = tmp_path / "p.json"
    path.write_text("{nope")
    assert priority.load_presets(str(path)) == []
    path.write_text(json.dumps({"groups": [{"name": "x", "patterns": [""]}]}))
    assert priority.load_presets(str(path)) == []


def test_save_then_load(tmp_path):
    path = str(tmp_path / "sub" / "priority.json")
    priority.save_config(path, dict(GOOD))
    assert priority.load_config(path) == GOOD


def test_corrupt_file_falls_back_to_default(tmp_path):
    path = tmp_path / "priority.json"
    path.write_text("{not json")
    assert priority.load_config(str(path)) == priority._default()


@pytest.mark.parametrize(
    "cfg",
    [
        {**GOOD, "nice": 0},
        {**GOOD, "nice": 20},
        {**GOOD, "nice": "10"},
        {**GOOD, "nice": True},
        {**GOOD, "background": "claude"},
        {**GOOD, "background": [""]},
        {**GOOD, "background": [1]},
        {**GOOD, "extra": 1},
        {"nice": 10, "background": ["claude"]},
        {"nice": 10, "background": ["x"], "protected": ["x"]},
    ],
)
def test_save_rejects_bad_config(tmp_path, cfg):
    with pytest.raises(ValueError):
        priority.save_config(str(tmp_path / "priority.json"), cfg)


def test_saved_file_is_plain_json(tmp_path):
    path = tmp_path / "priority.json"
    priority.save_config(str(path), dict(GOOD))
    assert json.loads(path.read_text()) == GOOD


@pytest.mark.parametrize(
    "name,patterns,expected",
    [
        ("claude", ["claude"], True),
        ("Claude Code", ["claude"], True),
        ("node", ["claude"], False),
        ("anything", [], False),
    ],
)
def test_matches(name, patterns, expected):
    assert priority.matches(name, patterns) is expected


def test_plan_matches_background_and_skips_protected():
    cfg = {"nice": 10, "background": ["claude"], "protected": ["important-claude"]}
    processes = [
        {"pid": 1, "name": "claude"},
        {"pid": 2, "name": "important-claude-tool"},
        {"pid": 3, "name": "firefox"},
    ]
    assert priority.plan(cfg, processes) == [{"pid": 1, "name": "claude", "nice": 10}]


def test_plan_returns_empty_for_no_matches():
    cfg = {"nice": 10, "background": [], "protected": []}
    assert priority.plan(cfg, [{"pid": 1, "name": "anything"}]) == []


def test_apply_calls_run_and_reports_results():
    calls = []

    def fake_run(pid, nice):
        calls.append((pid, nice))
        if pid == 2:
            raise ProcessLookupError("gone")

    entries = [{"pid": 1, "name": "a", "nice": 10}, {"pid": 2, "name": "b", "nice": 10}]
    results = priority.apply(entries, run=fake_run)
    assert calls == [(1, 10), (2, 10)]
    assert results[0] == {"pid": 1, "name": "a", "ok": True}
    assert results[1]["ok"] is False and results[1]["pid"] == 2


def test_all_processes_parses_ps_output(monkeypatch):
    class FakeResult:
        stdout = "  123 claude\n  456 firefox\nnotanumber comm\n"

    monkeypatch.setattr(priority.subprocess, "run", lambda *a, **k: FakeResult())
    assert priority.all_processes() == [
        {"pid": 123, "name": "claude"},
        {"pid": 456, "name": "firefox"},
    ]


def test_all_processes_lists_only_our_own():
    pids = {p["pid"] for p in priority.all_processes()}
    assert os.getpid() in pids
    assert 1 not in pids  # init is root's


def test_parse_cpu_list():
    assert priority.parse_cpus("4-11\n") == set(range(4, 12))
    assert priority.parse_cpus("0,2-3") == {0, 2, 3}
    assert priority.parse_cpus("") == set()


def test_mode_squeeze_lowers_further_and_pins():
    cfg = {"nice": 6, "background": ["bg"], "protected": []}
    procs = [{"pid": 5, "name": "bg"}, {"pid": 6, "name": "fg"}]
    squeeze = {"nice": 19, "cpus": {4, 5}}
    assert priority.plan(cfg, procs, squeeze) == [
        {"pid": 5, "name": "bg", "nice": 19, "cpus": {4, 5}}
    ]
    # A squeeze never makes a task *less* nice than the user's own setting.
    cfg["nice"] = 19
    assert priority.plan(cfg, procs, {"nice": 12})[0]["nice"] == 19


def test_apply_passes_cpus_when_pinning():
    calls = []
    priority.apply(
        [{"pid": 1, "name": "a", "nice": 19, "cpus": {4}}],
        run=lambda pid, nice, cpus=None: calls.append((pid, nice, cpus)),
    )
    assert calls == [(1, 19, {4})]


def test_default_run_never_tries_to_raise_priority(monkeypatch):
    calls = []
    monkeypatch.setattr(priority.os, "getpriority", lambda which, pid: 19)
    monkeypatch.setattr(priority.os, "setpriority", lambda *a: calls.append(a))
    monkeypatch.setattr(priority.subprocess, "run", lambda *a, **k: calls.append(a))
    priority._default_run(123, 10)  # already at 19: unprivileged can't go back
    assert calls == []


def test_squeeze_for_mode_reads_the_mode_block(tmp_path):
    ecores = tmp_path / "cpus"
    ecores.write_text("4-11\n")
    mode = {"background_tasks": {"nice": 19, "efficiency_cores_only": True}}
    assert priority.squeeze_for(mode, str(ecores)) == {
        "nice": 19,
        "cpus": set(range(4, 12)),
    }
    assert priority.squeeze_for({}, str(ecores)) is None
    assert priority.squeeze_for(mode, str(tmp_path / "missing")) == {"nice": 19}
