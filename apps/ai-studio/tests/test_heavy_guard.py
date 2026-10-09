"""Critic-review fixes: the heavy-job guard (a model video or a 3D world
blocks the image servers and other heavy jobs), downloads vs. deletes,
quotes, sd-server restarts, world shutdown and world settings."""

import io
import os
import subprocess
import sys
import textwrap
import threading
import time
import types
import urllib.request
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from studio_fakes import (
    entry,
    make_part,
    put,
    server,
    studio,
    wait_download,
)  # noqa: F401
import app as studio_app  # pyright: ignore[reportMissingImports]
import catalog  # pyright: ignore[reportMissingImports]
import config  # pyright: ignore[reportMissingImports]
import model_manager as mm  # pyright: ignore[reportMissingImports]
from worlds import runners  # pyright: ignore[reportMissingImports]

SRC = Path(__file__).resolve().parent.parent / "src"


class FakeProc:
    def __init__(self):
        self.rc = None

    def poll(self):
        return self.rc

    def terminate(self):
        self.rc = -15

    def wait(self, timeout=None):
        return self.rc

    def kill(self):
        self.rc = -9


@pytest.fixture
def heavy(studio, monkeypatch, tmp_path):
    """Real ServerManager with fake processes, a switchable heavy job, and
    two installed image models."""
    sm = mm.ServerManager()
    launched = []

    def launch(entry, port, backend):
        launched.append(entry["id"])
        return FakeProc()

    monkeypatch.setattr(sm, "_launch", launch)
    monkeypatch.setattr(sm, "_wait_ready", lambda: None)
    monkeypatch.setattr(mm, "servers", sm)
    monkeypatch.setattr(studio_app.model_manager, "servers", sm)
    job = {"now": None}
    monkeypatch.setattr(mm, "_busy_probes", [lambda: job["now"]])
    monkeypatch.setattr(config, "OUTPUTS_DIR", tmp_path / "out")
    (tmp_path / "out").mkdir()
    studio.use(
        [
            entry(
                "a",
                [
                    {
                        "role": "diffusion",
                        "url": "https://x/a",
                        "filename": "a.g",
                        "size_bytes": 1,
                    }
                ],
            ),
            entry(
                "b",
                [
                    {
                        "role": "diffusion",
                        "url": "https://x/b",
                        "filename": "b.g",
                        "size_bytes": 1,
                    }
                ],
            ),
        ],
        default="a",
    )
    put(studio.parts / "a.g", 1)
    put(studio.parts / "b.g", 1)
    monkeypatch.setattr(mm, "run_status", lambda e: (True, ""))
    studio.sm, studio.launched, studio.job = sm, launched, job
    return studio


VIDEO = {"kind": "video", "id": "v1", "detail": mm.VIDEO_BUSY}
WORLD = {"kind": "world", "id": "w1", "detail": mm.WORLD_BUSY}


def _code(fn, *a):
    with pytest.raises(HTTPException) as e:
        fn(*a)
    return e.value.status_code, e.value.detail


def test_nothing_loads_the_image_server_while_a_heavy_job_runs(heavy):
    heavy.job["now"] = VIDEO
    assert heavy.sm.active_id is None  # the video job stopped the servers
    assert _code(studio_app._require_active_model) == (409, mm.VIDEO_BUSY)
    with pytest.raises(mm.Busy):
        heavy.sm.switch_to("b")
    with pytest.raises(mm.Busy):
        heavy.sm.start("a")
    assert heavy.launched == []
    heavy.job["now"] = None
    studio_app._require_active_model()
    assert heavy.launched == ["a"]


def test_routes_answer_409_with_the_plain_text(heavy, monkeypatch):
    heavy.job["now"] = WORLD
    resp = studio_app._busy(None, mm.Busy(mm.WORLD_BUSY))  # type: ignore[arg-type]
    assert resp.status_code == 409
    assert studio_app.busy_state() == {"busy": WORLD}
    assert studio_app.list_models()["busy"] == WORLD
    req = studio_app.EditRequest(prompt="x", start_image_url="/outputs/a/b.png")
    assert _code(studio_app.generate_edit, req) == (409, mm.WORLD_BUSY)
    vreq = studio_app.VideoRequest(prompt="a road")
    assert _code(studio_app.generate_video, vreq) == (409, mm.WORLD_BUSY)
    with pytest.raises(mm.Busy):
        studio_app.activate_model("b")
    assert heavy.launched == []


def test_model_video_and_world_refuse_each_other(heavy, monkeypatch):
    vid = entry(
        "v",
        [
            {
                "role": "diffusion",
                "url": "https://x/v",
                "filename": "v.g",
                "size_bytes": 1,
            }
        ],
        kind="video",
    )
    world = entry("w", [], kind="world")
    heavy.use([vid, world])
    put(heavy.parts / "v.g", 1)
    heavy.job["now"] = WORLD
    req = studio_app.ModelVideoRequest(prompt="x")
    assert _code(studio_app.generate_model_video, req) == (409, mm.WORLD_BUSY)
    heavy.job["now"] = VIDEO
    started = []
    fake = types.SimpleNamespace(
        WorldError=RuntimeError,
        start_session=lambda *a, **k: started.append(k) or {"id": "s"},
    )
    monkeypatch.setitem(sys.modules, "worlds", fake)
    wreq = studio_app.WorldStartRequest(prompt="x")
    assert _code(studio_app.world_start, "w", wreq) == (409, mm.VIDEO_BUSY)
    assert started == []
    # a running world does not block starting through worlds' own check,
    # and the image servers are stopped first
    heavy.job["now"] = None
    heavy.sm.gpu_proc, heavy.sm.active_id = FakeProc(), "a"  # servers up
    assert studio_app.world_start("w", wreq) == {"id": "s"}
    assert heavy.sm.active_id is None and started[0]["settings"] == {}


def test_deleting_the_active_model_during_a_heavy_job_leaves_servers_down(heavy):
    mm.set_active_id("a")
    heavy.job["now"] = VIDEO
    mm.delete_model("a")
    assert mm.get_active_id() == "b" and heavy.launched == []
    mm.set_active_id("b")
    mm.delete_all(["model:b"])
    assert heavy.launched == [] and mm.get_active_id() is None


def test_ensure_running_restarts_a_crashed_server(heavy):
    studio_app._require_active_model()
    assert heavy.launched == ["a"]
    studio_app._require_active_model()
    assert heavy.launched == ["a"]  # still alive: nothing to do
    heavy.sm.gpu_proc.rc = 1  # sd-server crashed
    studio_app._require_active_model()
    assert heavy.launched == ["a", "a"]


def test_wait_ready_forgets_the_model_when_sd_server_exits(monkeypatch):
    sm = mm.ServerManager()
    sm.gpu_proc, sm.active_id = FakeProc(), "a"
    sm.gpu_proc.rc = 1
    monkeypatch.setattr(config, "GPU_SERVER_URL", "http://127.0.0.1:9")
    sm._wait_ready(timeout=5)
    assert sm.active_id is None


def test_server_manager_serialises_start_and_stop(heavy, monkeypatch):
    inside = []

    def slow_launch(entry, port, backend):
        inside.append(1)
        assert len(inside) == 1, "two starts at once"
        time.sleep(0.05)
        inside.pop()
        return FakeProc()

    monkeypatch.setattr(heavy.sm, "_launch", slow_launch)
    threads = [
        threading.Thread(target=heavy.sm.switch_to, args=("a",)) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert heavy.sm.active_id == "a"


# ---- downloads vs. deletes, quotes, the plan ---------------------------------


def _shared_pair(server, studio):
    shared = make_part(server, "vae", "shared.st", 3000)
    studio.use(
        [
            entry("a", [make_part(server, "diffusion", "a.gguf", 5000), shared]),
            entry("b", [make_part(server, "diffusion", "b.gguf", 7000), shared]),
        ]
    )


def test_delete_keeps_parts_of_a_model_still_downloading(server, studio):
    _shared_pair(server, studio)
    put(studio.parts / "a.gguf", 5000)
    put(studio.parts / "shared.st", 3000)
    server.gate = threading.Event()
    mm.start_download("b")  # needs only b.gguf; shared.st is already there
    assert mm.delete_model("a") == 5000
    assert (studio.parts / "shared.st").exists()
    server.gate.set()
    assert wait_download("b") is None and mm.is_installed("b")


def test_delete_all_keeps_parts_of_a_model_still_downloading(server, studio):
    _shared_pair(server, studio)
    put(studio.parts / "a.gguf", 5000)
    put(studio.parts / "shared.st", 3000)
    server.gate = threading.Event()
    mm.start_download("b")
    got = mm.delete_all(["model:a"])
    assert got["freed_bytes"] == 5000 and (studio.parts / "shared.st").exists()
    server.gate.set()
    wait_download("b")


def test_a_part_vanishing_mid_download_fails_the_job(server, studio, monkeypatch):
    _shared_pair(server, studio)
    put(studio.parts / "shared.st", 3000)
    real_fetch = mm._fetch

    def fetch_then_lose_shared(part, job):
        real_fetch(part, job)
        (studio.parts / "shared.st").unlink()

    monkeypatch.setattr(mm, "_fetch", fetch_then_lose_shared)
    mm.start_download("a")
    got = wait_download("a")
    assert got["state"] == "failed" and "went missing" in got["message"]


def test_quote_counts_space_running_downloads_will_take(server, studio):
    _shared_pair(server, studio)
    studio.free[0] = mm.SPARE_BYTES + 15_000
    assert mm.quote("b")["fits"]
    server.gate = threading.Event()
    mm.start_download("a")  # 8000 bytes still to come
    q = mm.quote("b")  # b needs 7000 + 3000 (shared not on disk yet)
    assert q["free_bytes"] < mm.SPARE_BYTES + 15_000
    assert q["fits"] is False
    server.gate.set()
    wait_download("a")


def test_plan_skips_part_files_of_running_downloads(server, studio):
    _shared_pair(server, studio)
    put(studio.parts / "stale.gguf.part", 5)
    server.gate = threading.Event()
    mm.start_download("a")
    deadline = time.time() + 5
    while not (studio.parts / "a.gguf.part").exists() and time.time() < deadline:
        time.sleep(0.01)
    other = {i["id"]: i for i in mm.delete_all_plan()}["other"]
    assert [Path(f).name for f in other["files"]] == ["stale.gguf.part"]
    server.gate.set()
    wait_download("a")


def test_plan_item_tolerates_a_file_that_vanished(tmp_path):
    keep = put(tmp_path / "k", 4)
    item = mm._item("x", "X", [keep, tmp_path / "gone"], True)
    assert item["files"] == [str(keep)] and item["bytes"] == 4


def test_skipped_shared_part_counts_as_done(server, studio):
    _shared_pair(server, studio)
    server.gate = threading.Event()
    mm.start_download("a")
    mm.start_download("b")  # waits on shared.st's lock, then skips it
    server.gate.set()
    for mid in ("a", "b"):
        wait_download(mid)
    assert mm.is_installed("a") and mm.is_installed("b")


def test_the_token_is_not_sent_to_another_host():
    h = mm._Redirect()
    req = urllib.request.Request(
        "https://huggingface.co/x", headers={"Authorization": "Bearer t"}
    )
    same = h.redirect_request(
        req, io.BytesIO(), 302, "", {}, "https://huggingface.co/y"
    )
    other = h.redirect_request(req, io.BytesIO(), 302, "", {}, "https://cdn.example/y")
    assert same is not None and same.get_header("Authorization") == "Bearer t"
    assert other is not None and other.get_header("Authorization") is None


@pytest.mark.parametrize("dest", ["../x", "/etc/x", "a/../../b", "~/x", 5])
def test_catalog_refuses_unsafe_dest(dest):
    p = {
        "role": "weights",
        "url": "https://x/y",
        "filename": "y",
        "size_bytes": 1,
        "dest": dest,
    }
    with pytest.raises(ValueError, match="unsafe dest"):
        catalog.validate(entry("w", [p], kind="world"))
    p["dest"] = "models/sub/y.bin"
    catalog.validate(entry("w", [p], kind="world"))


# ---- worlds: shutdown, orphaned workers, settings ----------------------------


def test_shutdown_stops_every_running_world(monkeypatch):
    stopped = []
    fake = types.SimpleNamespace(
        manager=lambda: types.SimpleNamespace(running=lambda: ["s1", "s2"]),
        stop_session=stopped.append,
    )
    monkeypatch.setitem(sys.modules, "worlds", fake)
    monkeypatch.setattr(studio_app.model_manager.servers, "stop", lambda: None)
    studio_app._shutdown()
    assert stopped == ["s1", "s2"]


def test_world_worker_exits_when_the_app_is_gone(tmp_path):
    grandchild = textwrap.dedent(f"""
        import os, sys, time
        sys.path.insert(0, {str(SRC / "worlds")!r})
        import walk_sd_worker
        walk_sd_worker.watch_parent({str(tmp_path)!r}, os.getppid(), interval=0.05)
        time.sleep(30)
        """)
    child = textwrap.dedent(f"""
        import subprocess, sys
        p = subprocess.Popen([sys.executable, "-c", {grandchild!r}], start_new_session=True)
        print(p.pid, flush=True)
        import time; time.sleep(0.5)
        """)
    out = subprocess.run(
        [sys.executable, "-c", child], capture_output=True, text=True, timeout=20
    )
    pid = int(out.stdout.split()[0])
    deadline = time.time() + 10
    while time.time() < deadline and _alive(pid):
        time.sleep(0.05)
    assert not _alive(pid)
    assert "Stopped" in (tmp_path / "status.json").read_text()


def _alive(pid):
    try:
        state = Path(f"/proc/{pid}/status").read_text()
    except OSError:  # gone (ENOENT, or ESRCH while it was going)
        return False
    return "\tZ" not in state.split("State:", 1)[1].split("\n", 1)[0]


def test_world_settings_are_an_allow_list_with_bounds():
    ok = studio_app.WorldSettings(
        seed=3, steps=8, cfg_scale=5, frames=17, width=512, height=288, fps=16
    )
    assert ok.model_dump(exclude_none=True)["steps"] == 8
    for bad in (
        {"sd_args": ["--x"]},
        {"steps": 0},
        {"width": 99999},
        {"cfg_scale": float("nan")},
    ):
        with pytest.raises(ValidationError):
            studio_app.WorldSettings(**bad)
    with pytest.raises(ValidationError):
        studio_app.WorldStartRequest(settings={"sd_args": ["--rm"]})


def test_runner_ignores_request_keys_outside_the_allow_list():
    e = entry("w", [], kind="world", settings={"steps": 12, "sd_args": ["--safe"]})
    job = runners.Runner().build_job(
        e, settings={"steps": 4, "sd_args": ["--evil"], "x": 1}
    )
    assert job["settings"] == {"steps": 4, "sd_args": ["--safe"]}
