"""World runners and sessions, with a fake sd binary and a fake world runner.

No real model, no GPU: the fake sd writes small coloured frames and logs its
arguments, so the whole subprocess session path is exercised.
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog  # noqa: E402  # pyright: ignore[reportMissingImports]
import worlds  # noqa: E402  # pyright: ignore[reportMissingImports]
from PIL import Image  # noqa: E402
from worlds import protocol  # noqa: E402  # pyright: ignore[reportMissingImports]
from worlds import runners  # noqa: E402  # pyright: ignore[reportMissingImports]
from worlds_fakes import HELP_OLD, make_fake_sd, make_parts  # noqa: E402

WALK = catalog.CATALOG["world-walk"]
SMALL = {"width": 64, "height": 32, "frames": 5}


def wait_for(manager, sid, states, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        info = manager.poll(sid)
        if info["state"] in states:
            return info
        time.sleep(0.05)
    raise AssertionError(f"session stuck in {manager.poll(sid)['state']}")


@pytest.fixture
def env(tmp_path, monkeypatch):
    sd = make_fake_sd(tmp_path)
    parts = make_parts(tmp_path / "parts", WALK)
    monkeypatch.setattr(runners, "sd_binary", lambda entry: sd)
    monkeypatch.setattr(runners, "PART_DIRS", [parts])
    monkeypatch.setattr(runners, "WORLDS_DIR", tmp_path / "worlds")
    monkeypatch.setenv("FAKE_SD_LOG", str(tmp_path / "sd_calls.jsonl"))
    manager = worlds.SessionManager(tmp_path / "sessions")
    picture = tmp_path / "start.jpg"
    Image.new("RGB", (300, 200), (200, 120, 40)).save(picture)
    yield {"tmp": tmp_path, "sd": sd, "manager": manager, "picture": picture}
    for sid in manager.running():
        manager.stop(sid, grace=1)


def sd_calls(env):
    path = env["tmp"] / "sd_calls.jsonl"
    return (
        [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    )


# -- runner_status -------------------------------------------------------------


def test_walk_status_follows_the_engine(env, monkeypatch, tmp_path):
    walk = runners.RUNNERS["walk-sd"]
    assert walk.status(WALK) == (True, runners.NOTE_READY)
    monkeypatch.setattr(runners, "sd_binary", lambda e: tmp_path / "missing" / "sd")
    assert walk.status(WALK) == (False, runners.NOTE_NO_ENGINE)
    (tmp_path / "old").mkdir()
    old = make_fake_sd(tmp_path / "old", HELP_OLD)
    monkeypatch.setattr(runners, "sd_binary", lambda e: old)
    assert walk.status(WALK) == (False, runners.NOTE_ENGINE_UPDATE)


@pytest.mark.parametrize("nvidia", [False, True])
def test_torch_runners_are_honest_without_a_runtime(env, monkeypatch, nvidia):
    monkeypatch.setattr(runners, "has_nvidia", lambda: nvidia)
    for rid, runner in runners.RUNNERS.items():
        if rid == "walk-sd":
            continue
        ok, note = runner.status({"engine": f"world:{rid}"})
        assert not ok
        if runner.needs_nvidia and not nvidia:
            assert note == runners.NOTE_NVIDIA
        else:
            assert note == runners.NOTE_NO_RUNTIME
        # with a runtime folder in place it reports ready (when the card allows)
        runner.python.parent.mkdir(parents=True, exist_ok=True)
        runner.python.write_text("")
        runner.adapter.write_text("")
        ok, note = runner.status({"engine": f"world:{rid}"})
        assert ok == (nvidia or not runner.needs_nvidia)


def test_every_world_entry_gets_a_status():
    for entry in catalog.CATALOG.values():
        if entry["kind"] == "world":
            ok, note = worlds.runner_status(entry)
            assert isinstance(ok, bool) and note
    assert worlds.runner_status({"engine": "sd"}) == (False, worlds.NOTE_NO_RUNNER)
    assert worlds.runner_status({"engine": "world:nope"}) == (
        False,
        worlds.NOTE_NO_RUNNER,
    )


def test_runtime_plan_is_documented_and_not_installable_here():
    plan = worlds.runtime_plan("inspatio")
    assert plan and plan["packages"] and plan["why_not"]
    assert plan["press_to_install"] is False
    assert any(p.startswith("torch==") and "+cpu" in p for p in plan["packages"])
    assert worlds.runtime_plan("walk-sd") is None


def test_missing_parts_refuse_to_start(env, monkeypatch, tmp_path):
    monkeypatch.setattr(runners, "PART_DIRS", [tmp_path / "empty"])
    with pytest.raises(worlds.WorldCannotRun, match="Download it first"):
        env["manager"].start(runners.RUNNERS["walk-sd"], WALK, settings=SMALL)


# -- walk-sd sessions -------------------------------------------------------------


def test_walk_with_picture_builds_frames_step_by_step(env):
    m = env["manager"]
    walk = runners.RUNNERS["walk-sd"]
    info = m.start(
        walk, WALK, prompt="a forest path", image=env["picture"],
        actions=["forward", "turn_left"], settings=SMALL,
    )  # fmt: skip
    sid = info["id"]
    info = wait_for(m, sid, {"waiting"})
    assert info["frame_count"] == 1 + (SMALL["frames"] - 1)
    assert info["chunk"] == 1
    calls = sd_calls(env)
    assert len(calls) == 1
    args = calls[0]
    assert args[:2] == ["-M", "vid_gen"]
    assert "--control-video" in args and "-i" in args
    assert args[args.index("-p") + 1] == "a forest path"
    for flag in ("--diffusion-model", "--t5xxl", "--vae", "--offload-to-cpu"):
        assert flag in args
    # the start frame is the picture, cropped to the walk's shape
    first = Image.open(m.frame_path(sid, "000001.png"))
    assert first.size == (64, 32)
    # the next step continues from the last frame
    m.step(sid, ["forward"])
    end = time.monotonic() + 30
    while m.poll(sid)["chunk"] < 2 or m.poll(sid)["state"] != "waiting":
        assert time.monotonic() < end
        time.sleep(0.05)
    info = m.poll(sid, since=5)
    assert info["frame_count"] == 9 and info["frames"] == [
        f"{i:06d}.png" for i in range(6, 10)
    ]
    assert len(sd_calls(env)) == 2
    clip = m.make_clip(sid)
    assert clip.is_file() and clip.stat().st_size > 0
    info = m.stop(sid)
    assert info["state"] == "stopped"
    assert m.running() == []


def test_walk_without_picture_starts_from_text(env):
    m = env["manager"]
    sid = m.start(runners.RUNNERS["walk-sd"], WALK, prompt="a beach", actions=["stay"],
                  settings=SMALL)["id"]  # fmt: skip
    info = wait_for(m, sid, {"waiting"})
    assert info["frame_count"] == SMALL["frames"]
    assert "--control-video" not in sd_calls(env)[0]
    m.stop(sid)


def test_waits_for_moves_when_started_without_any(env):
    m = env["manager"]
    sid = m.start(
        runners.RUNNERS["walk-sd"], WALK, image=env["picture"], settings=SMALL
    )["id"]
    info = wait_for(m, sid, {"waiting"})
    assert info["frame_count"] == 1 and sd_calls(env) == []
    m.stop(sid)


def test_only_one_world_runs_at_a_time(env):
    m = env["manager"]
    walk = runners.RUNNERS["walk-sd"]
    sid = m.start(walk, WALK, image=env["picture"], settings=SMALL)["id"]
    with pytest.raises(worlds.WorldBusy):
        m.start(walk, WALK, image=env["picture"], settings=SMALL)
    m.stop(sid)
    sid2 = m.start(walk, WALK, image=env["picture"], settings=SMALL)["id"]
    assert sid2 != sid
    m.stop(sid2)


def test_engine_failure_is_reported(env, monkeypatch):
    monkeypatch.setenv("FAKE_SD_FAIL", "1")
    m = env["manager"]
    sid = m.start(runners.RUNNERS["walk-sd"], WALK, image=env["picture"],
                  actions=["forward"], settings=SMALL)["id"]  # fmt: skip
    info = wait_for(m, sid, {"failed"})
    assert info["message"] == "The video engine stopped with an error"
    with pytest.raises(worlds.WorldError):
        m.step(sid, ["forward"])


def test_stop_ends_a_busy_engine_quickly(env, monkeypatch):
    monkeypatch.setenv("FAKE_SD_SLEEP", "60")
    m = env["manager"]
    sid = m.start(runners.RUNNERS["walk-sd"], WALK, image=env["picture"],
                  actions=["forward"], settings=SMALL)["id"]  # fmt: skip
    wait_for(m, sid, {"working"})
    end = time.monotonic() + 10
    while not sd_calls(env):  # the fake engine has started sleeping
        assert time.monotonic() < end
        time.sleep(0.05)
    pid = int((env["manager"].root / sid / "pid").read_text())
    t0 = time.monotonic()
    info = m.stop(sid, grace=0.5)
    assert info["state"] == "stopped"
    assert time.monotonic() - t0 < 8
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_bad_moves_ids_and_frame_names(env):
    m = env["manager"]
    walk = runners.RUNNERS["walk-sd"]
    with pytest.raises(worlds.WorldError, match="Unknown move"):
        m.start(walk, WALK, actions=["fly"], settings=SMALL)
    for sid in ("../x", "", "nope-nope", None):
        with pytest.raises(worlds.WorldNotFound):
            m.poll(sid)
    sid = m.start(walk, WALK, image=env["picture"], settings=SMALL)["id"]
    wait_for(m, sid, {"waiting"})
    for name in ("../job.json", "1.png", "000099.png"):
        with pytest.raises(worlds.WorldNotFound):
            m.frame_path(sid, name)
    with pytest.raises(worlds.WorldError, match="Unknown move"):
        m.step(sid, ["fly"])
    m.stop(sid)


def test_app_restart_marks_running_sessions_stopped(env):
    m = env["manager"]
    sid = m.start(
        runners.RUNNERS["walk-sd"], WALK, image=env["picture"], settings=SMALL
    )["id"]
    wait_for(m, sid, {"waiting"})
    fresh = worlds.SessionManager(m.root)
    info = fresh.poll(sid)
    assert info["state"] == "stopped" and "restarted" in info["message"]
    assert [s["id"] for s in fresh.list()] == [sid]
    m.stop(sid)


# -- a fake PyTorch runner speaking the protocol -----------------------------------

FAKE_ADAPTER = r"""
import sys
from pathlib import Path
sys.path.insert(0, {worlds_dir!r})
import protocol
from PIL import Image
d = Path(sys.argv[1])
job = protocol.read_json(d / protocol.JOB)
seq = 0
pending = job["actions"] or None
while True:
    if pending is None:
        protocol.write_status(d, "waiting", "Ready", seq_done=seq)
        rec = protocol.wait_for_actions(d, seq, 30)
        if rec in ("stop", "timeout"):
            protocol.write_status(d, "stopped", "Stopped")
            break
        seq, pending = rec["seq"], rec["actions"]
    for a in pending:
        img = d / "tmp.png"
        Image.new("RGB", (8, 8)).save(img)
        protocol.add_frame(d, img)
    pending = None
"""


def test_torch_runner_session_with_a_fake_runtime(env, monkeypatch):
    runner = runners.RUNNERS["inspatio"]
    runner.python.parent.mkdir(parents=True)
    runner.python.symlink_to(sys.executable)
    worlds_dir = str(Path(runners.__file__).parent)
    runner.adapter.write_text(FAKE_ADAPTER.replace("{worlds_dir!r}", repr(worlds_dir)))
    entry = {
        "id": "fake-world",
        "engine": "world:inspatio",
        "parts": [],
        "settings": {},
    }
    m = env["manager"]
    sid = m.start(runner, entry, actions=["forward", "left"])["id"]
    info = wait_for(m, sid, {"waiting"})
    assert info["frame_count"] == 2
    job = protocol.read_json(m.root / sid / protocol.JOB)
    assert job["runner"] == "inspatio" and job["actions"] == ["forward", "left"]
    m.step(sid, ["back"])
    end = time.monotonic() + 20
    while m.poll(sid)["frame_count"] < 3:
        assert time.monotonic() < end
        time.sleep(0.05)
    assert m.stop(sid)["state"] == "stopped"


def test_runner_that_dies_is_reported(env):
    runner = runners.RUNNERS["inspatio"]
    runner.python.parent.mkdir(parents=True)
    runner.python.symlink_to(sys.executable)
    runner.adapter.write_text("import sys; sys.exit(2)\n")
    m = env["manager"]
    sid = m.start(runner, {"id": "x", "engine": "world:inspatio", "parts": []})["id"]
    info = wait_for(m, sid, {"failed"})
    assert info["message"] == "The world runner stopped unexpectedly"
