import json
import os
import stat
import subprocess
from typing import Optional

import pytest

import web_app

TESTS_LAST_FIXTURE = {
    "when": "2026-09-29T21:30:00",
    "passed": 12,
    "failed": 0,
    "seconds": 3.1,
    "tests": [{"name": "test_registry.gd:test_all_load", "ok": True, "message": ""}],
}


def fps_fixture(preset, when, avg_fps, target_fps: Optional[int] = 45):
    return {
        "when": when,
        "map": "test_range",
        "preset": preset,
        "target_fps": target_fps,
        "avg_fps": avg_fps,
        "p1_low_fps": 38.0,
        "min_fps": 30.5,
        "frame_ms_avg": 19.5,
        "seconds": 20.0,
        "resolution": [1920, 1080],
        "render_scale": 0.8,
        "gpu": "Intel(R) Iris(R) Xe Graphics",
        "blender_running": False,
    }


# --- status -----------------------------------------------------------


def test_status_reports_missing_root(client, monkeypatch, tmp_path):
    monkeypatch.setenv("EIGHTYSIX_ROOT", str(tmp_path / "does-not-exist"))
    res = client.get("/api/status")
    assert res.status_code == 200
    assert res.json()["root_exists"] is False


def test_status_reports_existing_root(client, game_root):
    res = client.get("/api/status")
    assert res.json()["root_exists"] is True


# --- tests --------------------------------------------------------------


def test_tests_last_missing_says_unavailable(client, game_root):
    res = client.get("/api/tests")
    assert res.json() == {"available": False, "running": False}


def test_tests_last_reads_contract_shape(client, game_root):
    logs = game_root / "logs"
    logs.mkdir()
    (logs / "tests-last.json").write_text(json.dumps(TESTS_LAST_FIXTURE))
    res = client.get("/api/tests")
    body = res.json()
    assert body["available"] is True
    assert body["passed"] == 12
    assert body["failed"] == 0
    assert body["tests"][0]["name"] == "test_registry.gd:test_all_load"


def test_tests_run_missing_script_does_not_fail(client, game_root):
    res = client.post("/api/tests/run")
    assert res.status_code == 200
    body = res.json()
    assert body["started"] is False
    assert "run_tests.sh" in body["reason"]


def test_tests_run_launches_existing_script(client, game_root, monkeypatch):
    tools = game_root / "tools"
    tools.mkdir()
    script = tools / "run_tests.sh"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)

    calls = []

    class FakePopen:
        pid = 4242

        def __init__(self, args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(web_app.subprocess, "Popen", FakePopen)
    res = client.post("/api/tests/run")
    assert res.json() == {"started": True}
    assert calls[0][0] == [str(script)]


# --- fps ------------------------------------------------------------------


def test_fps_empty_when_no_logs(client, game_root):
    res = client.get("/api/fps")
    body = res.json()
    assert len(body["presets"]) == 4
    assert all(p["record"] is None for p in body["presets"])


def test_fps_picks_newest_per_preset(client, game_root):
    fps_dir = game_root / "logs" / "fps"
    fps_dir.mkdir(parents=True)
    (fps_dir / "1-medium.json").write_text(
        json.dumps(fps_fixture("medium", "2026-09-29T10:00:00", 40.0))
    )
    (fps_dir / "2-medium.json").write_text(
        json.dumps(fps_fixture("medium", "2026-09-29T12:00:00", 51.2))
    )
    res = client.get("/api/fps")
    body = res.json()
    medium = next(p for p in body["presets"] if p["preset"] == "medium")
    assert medium["record"]["when"] == "2026-09-29T12:00:00"
    assert medium["record"]["avg_fps"] == 51.2
    assert medium["met_target"] is True


def test_fps_null_target_has_no_met_flag(client, game_root):
    fps_dir = game_root / "logs" / "fps"
    fps_dir.mkdir(parents=True)
    (fps_dir / "1-ultra.json").write_text(
        json.dumps(fps_fixture("ultra", "2026-09-29T10:00:00", 20.0, target_fps=None))
    )
    res = client.get("/api/fps")
    ultra = next(p for p in res.json()["presets"] if p["preset"] == "ultra")
    assert ultra["record"]["target_fps"] is None
    assert ultra["met_target"] is None


def test_fps_capped_record_is_judged_by_its_estimate(client, game_root):
    fps_dir = game_root / "logs" / "fps"
    fps_dir.mkdir(parents=True)
    low = fps_fixture("low", "2026-09-30T07:00:00", 59.8, target_fps=60)
    low.update({"vsync_cap_hz": 60.0, "est_uncapped_fps": 88.4})
    medium = fps_fixture("medium", "2026-09-30T07:00:00", 59.7, target_fps=45)
    medium.update({"vsync_cap_hz": 60.0, "est_uncapped_fps": 40.0})
    high = fps_fixture("high", "2026-09-30T07:00:00", 28.0, target_fps=30)
    (fps_dir / "1-low.json").write_text(json.dumps(low))
    (fps_dir / "1-medium.json").write_text(json.dumps(medium))
    (fps_dir / "1-high.json").write_text(json.dumps(high))
    by = {p["preset"]: p for p in client.get("/api/fps").json()["presets"]}
    assert (by["low"]["met_target"], by["low"]["met_by"]) == (True, "estimate")
    # A target under the cap is measured directly, whatever the estimate says.
    assert (by["medium"]["met_target"], by["medium"]["met_by"]) == (True, "measured")
    assert (by["high"]["met_target"], by["high"]["met_by"]) == (False, "measured")


# --- images -----------------------------------------------------------


def test_images_index_orders_by_number_newest_first(client, game_root):
    images = game_root / "images"
    (images / "002-first").mkdir(parents=True)
    (images / "010-later").mkdir(parents=True)
    res = client.get("/api/images")
    body = res.json()
    assert body["newest"] == "010-later"
    assert body["folders"] == ["010-later", "002-first"]


def test_images_folder_lists_pngs_and_report(client, game_root):
    folder = game_root / "images" / "001-run"
    folder.mkdir(parents=True)
    (folder / "shot1.png").write_bytes(b"\x89PNG\r\n")
    (folder / "shot2.png").write_bytes(b"\x89PNG\r\n")
    (folder / "notes.txt").write_text("ignore me")
    (folder / "report.json").write_text(json.dumps({"note": "looks good"}))
    res = client.get("/api/images/001-run")
    body = res.json()
    assert body["files"] == ["shot1.png", "shot2.png"]
    assert body["report"] == {"note": "looks good"}


def test_images_folder_rejects_path_escape(client, game_root):
    (game_root / "images").mkdir()
    # A plain ".." is collapsed by URL normalisation before it reaches the
    # server, same as a browser would; percent-encoding it is what a real
    # escape attempt looks like on the wire.
    res = client.get("/api/images/%2e%2e")
    assert res.status_code == 400


def test_safe_image_folder_rejects_escape_directly(game_root):
    (game_root / "images").mkdir()
    try:
        web_app._safe_image_folder("..")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("expected an HTTPException")


def test_image_file_serves_png(client, game_root):
    folder = game_root / "images" / "001-run"
    folder.mkdir(parents=True)
    (folder / "shot1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    res = client.get("/api/images/001-run/shot1.png")
    assert res.status_code == 200
    assert res.content == b"\x89PNG\r\n\x1a\n"


def test_image_file_rejects_non_png(client, game_root):
    folder = game_root / "images" / "001-run"
    folder.mkdir(parents=True)
    (folder / "secret.txt").write_text("nope")
    res = client.get("/api/images/001-run/secret.txt")
    assert res.status_code == 400


# --- readme -----------------------------------------------------------

README_FIXTURE = """# Eighty Six (0.1 alpha)

## Current state

- Lane A1 (foundation) in progress.

## Log

### 2026-09-29 · lane A1 · Sora (ejb-83) · started
- Created the project.

### 2026-09-29 · lane A1 helper · hub entry added
- Added the Forge hub tile.
"""


def test_readme_missing_says_unavailable(client, game_root):
    res = client.get("/api/readme")
    assert res.json() == {"available": False}


def test_readme_parses_current_state_and_newest_entry(client, game_root):
    (game_root / "README.md").write_text(README_FIXTURE)
    res = client.get("/api/readme")
    body = res.json()
    assert body["available"] is True
    assert "Lane A1 (foundation) in progress." in body["current_state"]
    assert "hub entry added" in body["newest_log_entry"]
    assert "started" not in body["newest_log_entry"]


# --- play ---------------------------------------------------------------


def test_play_runs_build_when_present_and_executable(client, game_root, monkeypatch):
    build_dir = game_root / "build" / "linux"
    build_dir.mkdir(parents=True)
    build = build_dir / "eightysix.x86_64"
    build.write_bytes(b"\x7fELF")
    build.chmod(build.stat().st_mode | stat.S_IEXEC)

    calls = []
    monkeypatch.setattr(
        web_app.subprocess, "Popen", lambda args, **kw: calls.append(args)
    )
    res = client.post("/api/play")
    body = res.json()
    assert body["mode"] == "build"
    assert calls[0] == [str(build)]


def test_play_falls_back_to_godot_editor_run_without_build(
    client, game_root, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        web_app.subprocess, "Popen", lambda args, **kw: calls.append(args)
    )
    res = client.post("/api/play")
    body = res.json()
    assert body["mode"] == "editor-run"
    assert calls[0] == ["godot", "--path", str(game_root)]


def test_play_editor_opens_godot_editor(client, game_root, monkeypatch):
    calls = []
    monkeypatch.setattr(
        web_app.subprocess, "Popen", lambda args, **kw: calls.append(args)
    )
    res = client.post("/api/play/editor")
    body = res.json()
    assert body["mode"] == "editor"
    assert calls[0] == ["godot", "-e", "--path", str(game_root)]


def _launcher(game_root):
    tools = game_root / "tools"
    tools.mkdir(exist_ok=True)
    launcher = tools / "play.sh"
    launcher.write_text("#!/bin/sh\n")
    launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    return launcher


def test_play_goes_through_the_games_launcher(client, game_root, monkeypatch):
    launcher = _launcher(game_root)
    calls = []
    monkeypatch.setattr(
        web_app.subprocess, "Popen", lambda args, **kw: calls.append(args)
    )
    assert client.post("/api/play").json()["mode"] == "auto"
    assert client.post("/api/play", json={"version": "3"}).json()["mode"] == "version"
    assert calls == [[str(launcher)], [str(launcher), "--version", "3"]]
    assert client.post("/api/play", json={"version": "; rm"}).status_code == 400


def test_versions_lists_saved_builds_newest_first(client, game_root):
    base = game_root / "build" / "versions"
    for n in (1, 2):
        d = base / f"00{n}-2026-09-30_1{n}00"
        d.mkdir(parents=True)
        (d / "VERSION.json").write_text(json.dumps({"number": n, "made": "x"}))
    (base / "002-2026-09-30_1200" / "share").mkdir()
    (base / "002-2026-09-30_1200" / "share" / "g-linux.zip").write_bytes(b"z")
    (base / "junk").mkdir()
    body = client.get("/api/versions").json()
    assert [v["number"] for v in body["versions"]] == [2, 1]
    assert body["versions"][0]["share"][0].endswith("g-linux.zip")


def test_versions_empty_without_builds(client, game_root):
    assert client.get("/api/versions").json() == {"available": False, "versions": []}


def test_share_starts_the_games_share_tool(client, game_root, monkeypatch):
    monkeypatch.setattr(web_app, "_share_proc", None)
    calls = []
    monkeypatch.setattr(
        web_app.subprocess, "Popen", lambda args, **kw: calls.append(args)
    )
    assert client.post("/api/share").json()["started"] is False
    (game_root / "tools").mkdir(exist_ok=True)
    (game_root / "tools" / "builds.py").write_text("")
    assert client.post("/api/share").json()["started"] is True
    assert calls[0][1:] == [str(game_root / "tools" / "builds.py"), "share"]


class _Running:
    def poll(self):
        return None


def test_share_runs_once_at_a_time_and_reports_its_zips(client, game_root, monkeypatch):
    monkeypatch.setattr(web_app, "_share_proc", None)
    monkeypatch.setattr(web_app.subprocess, "Popen", lambda args, **kw: _Running())
    (game_root / "tools").mkdir()
    (game_root / "tools" / "builds.py").write_text("")
    assert client.post("/api/share").json()["started"] is True
    again = client.post("/api/share").json()
    assert again["started"] is False and "already" in again["reason"]
    assert client.get("/api/share").json()["running"] is True
    monkeypatch.setattr(web_app, "_share_proc", None)
    (game_root / "build" / "share").mkdir(parents=True)
    (game_root / "build" / "share" / "eightysix-v011-linux.zip").write_bytes(b"z" * 10)
    (game_root / "logs" / "share.log").write_text("made\n")
    state = client.get("/api/share").json()
    assert state["running"] is False
    assert [z["name"] for z in state["zips"]] == ["eightysix-v011-linux.zip"]
    assert state["last_log"] == "made"


def test_delete_all_share_zips_runs_clear_shares(client, game_root, monkeypatch):
    monkeypatch.setattr(web_app, "_share_proc", None)
    assert client.post("/api/share/clear").json()["cleared"] is False
    (game_root / "tools").mkdir()
    (game_root / "tools" / "builds.py").write_text(
        "import sys\nprint('deleted 3 share zips, 210 MB freed' if sys.argv[1:] == ['clear-shares'] else 'no')\n"
    )
    body = client.post("/api/share/clear").json()
    assert body == {"cleared": True, "message": "deleted 3 share zips, 210 MB freed"}


# --- U1 sweep: no double launches -------------------------------------------


def test_a_double_click_on_play_launches_once(client, game_root, monkeypatch):
    _launcher(game_root)
    calls = []
    monkeypatch.setattr(
        web_app.subprocess, "Popen", lambda args, **kw: calls.append(args)
    )
    assert client.post("/api/play").status_code == 200
    again = client.post("/api/play")
    assert again.status_code == 409 and "few seconds" in again.json()["detail"]
    assert len(calls) == 1
    # another version, or the editor, is a different wish and goes through
    assert client.post("/api/play", json={"version": "3"}).status_code == 200
    assert client.post("/api/play/editor").status_code == 200
    assert len(calls) == 3


def test_play_works_again_after_the_cooldown(client, game_root, monkeypatch):
    calls = []
    monkeypatch.setattr(
        web_app.subprocess, "Popen", lambda args, **kw: calls.append(args)
    )
    clock = [1000.0]
    monkeypatch.setattr(web_app.time, "monotonic", lambda: clock[0])
    assert client.post("/api/play/editor").status_code == 200
    clock[0] += web_app.LAUNCH_COOLDOWN + 0.1
    assert client.post("/api/play/editor").status_code == 200
    assert len(calls) == 2


def test_tests_run_once_at_a_time(client, game_root, monkeypatch):
    tools = game_root / "tools"
    tools.mkdir()
    script = tools / "run_tests.sh"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    calls = []

    class Running:
        pid = 4242

        def __init__(self, args, **kwargs):
            calls.append(args)

        def poll(self):
            return None

    monkeypatch.setattr(web_app.subprocess, "Popen", Running)
    assert client.post("/api/tests/run").json() == {"started": True}
    again = client.post("/api/tests/run").json()
    assert again["started"] is False and "already" in again["reason"]
    assert len(calls) == 1
    assert client.get("/api/tests").json() == {"available": False, "running": True}


def test_tests_last_that_is_not_an_object_is_a_clean_error(client, game_root):
    (game_root / "logs").mkdir()
    (game_root / "logs" / "tests-last.json").write_text("[1, 2]")
    res = client.get("/api/tests")
    assert res.status_code == 500 and "not readable" in res.json()["detail"]


def test_a_launch_that_failed_can_be_tried_again_at_once(
    client, game_root, monkeypatch
):
    _launcher(game_root)
    calls = []

    def popen(args, **kw):
        calls.append(args)
        if len(calls) == 1:
            raise OSError("Exec format error")

    monkeypatch.setattr(web_app.subprocess, "Popen", popen)
    with pytest.raises(OSError):
        client.post("/api/play")
    assert client.post("/api/play").status_code == 200
    assert len(calls) == 2


def test_version_7_and_007_are_one_launch(client, game_root, monkeypatch):
    _launcher(game_root)
    calls = []
    monkeypatch.setattr(
        web_app.subprocess, "Popen", lambda args, **kw: calls.append(args)
    )
    assert client.post("/api/play", json={"version": "7"}).status_code == 200
    assert client.post("/api/play", json={"version": "007"}).status_code == 409
    assert calls == [[str(game_root / "tools" / "play.sh"), "--version", "7"]]


def test_a_run_started_before_a_backend_restart_still_counts(
    client, game_root, tmp_path
):
    tools = game_root / "tools"
    tools.mkdir()
    script = tools / "run_tests.sh"
    script.write_text("#!/bin/sh\nsleep 10\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    # started by an earlier backend: not this one's child, only the pid file knows
    proc = subprocess.Popen(["/bin/sh", str(script)])
    try:
        web_app.TESTS_PID.write_text(str(proc.pid))
        assert client.get("/api/tests").json()["running"] is True
        again = client.post("/api/tests/run").json()
        assert again["started"] is False and "already" in again["reason"]
    finally:
        proc.kill()
        proc.wait()
    assert client.get("/api/tests").json()["running"] is False
    # a stale pid that now belongs to something else is not a run
    web_app.TESTS_PID.write_text(str(os.getpid()))
    assert client.get("/api/tests").json()["running"] is False


def test_fps_log_with_text_where_numbers_belong_still_answers(client, game_root):
    fps = game_root / "logs" / "fps"
    fps.mkdir(parents=True)
    (fps / "low.json").write_text(
        json.dumps(
            {
                "preset": "low",
                "when": "2026-10-08",
                "avg_fps": "fast",
                "target_fps": "<i>60</i>",
                "vsync_cap_hz": "<img>",
                "est_uncapped_fps": None,
            }
        )
    )
    res = client.get("/api/fps")
    assert res.status_code == 200
    low = res.json()["presets"][0]
    assert low["preset"] == "low" and low["met_target"] is None
