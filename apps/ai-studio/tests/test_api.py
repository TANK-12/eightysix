"""HTTP API handlers, called directly (the venv has no httpx for TestClient).
Downloads hit a local file server; video jobs run a fake sd CLI script."""

import base64
import io
import sys
import textwrap
import time

import pytest
from fastapi import HTTPException
from PIL import Image

from studio_fakes import (
    entry,
    make_part,
    put,
    server,
    studio,
    wait_download,
)  # noqa: F401
import app as studio_app  # pyright: ignore[reportMissingImports]
import config  # pyright: ignore[reportMissingImports]
import model_manager  # pyright: ignore[reportMissingImports]
import video_models  # pyright: ignore[reportMissingImports]

FAKE_SD = textwrap.dedent("""\
    #!{python}
    import os, sys, time
    args = sys.argv[1:]
    open(os.path.join(os.getcwd(), "argv.txt"), "w").write("\\n".join(args))
    out = args[args.index("-o") + 1]
    for i in range(1, 5):
        sys.stdout.write(f"  |=====>     | {{i}}/4 - 0.01s/it\\r")
        sys.stdout.flush()
        time.sleep(float(os.environ.get("FAKE_SD_SLEEP", "0")))
    if os.environ.get("FAKE_SD_FAIL"):
        print("ggml_vulkan: out of memory")
        sys.exit(3)
    open(out, "wb").write(b"not really a webm")
    """)


@pytest.fixture
def api(studio, server, tmp_path, monkeypatch):
    """Scratch outputs, a fake engine build and three tiny models."""
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setattr(config, "OUTPUTS_DIR", outputs)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    cli = bindir / "sd"
    cli.write_text(FAKE_SD.format(python=sys.executable))
    cli.chmod(0o755)
    (bindir / "sd-server").write_text("")
    monkeypatch.setattr(
        config,
        "ENGINE_BUILDS",
        {"current": {"dir": bindir, "cli": "sd", "server": "sd-server"}},
    )
    recorded = []
    monkeypatch.setattr(
        studio_app.library, "record", lambda *a, **k: recorded.append(a)
    )
    monkeypatch.setattr(video_models, "_jobs", {})
    img = entry("img", [make_part(server, "diffusion", "img.gguf", 300)])
    vid = entry(
        "vid",
        [
            make_part(server, "diffusion", "vid.gguf", 200),
            make_part(server, "vae", "vid-vae.st", 100),
        ],
        kind="video",
        settings={"frames": 9, "frame_grid": [4, 1], "cfg_scale": 6.0, "fps": 24},
    )
    nope = entry("needs-next", [make_part(server, "diffusion", "n.gguf", 5)])
    nope["engine_build"] = "next"  # not in the fake ENGINE_BUILDS
    studio.use([img, vid, nope])
    studio.outputs = outputs
    studio.recorded = recorded
    return studio


def _status(fn, *a):
    with pytest.raises(HTTPException) as e:
        fn(*a)
    return e.value.status_code, e.value.detail


def _wait_job(job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = studio_app.model_video_state(job_id)
        if snap["state"] != "running":
            return snap
        time.sleep(0.05)
    raise AssertionError("video job did not finish")


def test_models_list_has_the_contract_card_shape(api):
    got = studio_app.list_models()
    assert set(got) == {"models", "disk", "busy"} and got["disk"]["free_bytes"] > 0
    assert got["busy"] is None
    card = {c["id"]: c for c in got["models"]}["img"]
    for key in ("id", "kind", "label", "blurb", "tier", "installed", "active"):
        assert key in card
    assert card["can_run"] is True and card["run_note"] == ""
    assert card["download"] is None and card["installed"] is False
    nope = {c["id"]: c for c in got["models"]}["needs-next"]
    assert nope["can_run"] is False and nope["run_note"] == "Needs an engine update"


def test_quote_download_and_card_progress(api):
    q = studio_app.quote_model("vid")
    assert (q["total_bytes"], q["needed_bytes"], q["fits"]) == (300, 300, True)
    assert studio_app.download_model("vid")["status"] == "started"
    wait_download("vid")
    card = {c["id"]: c for c in studio_app.list_models()["models"]}["vid"]
    assert card["installed"] and card["active"] and card["download"] is None
    assert studio_app.download_model("vid")["status"] == "already installed"


def test_download_errors_are_plain_http_codes(api):
    assert _status(studio_app.download_model, "zzz")[0] == 404
    assert _status(studio_app.quote_model, "zzz")[0] == 404
    api.free[0] = 1000  # far below the 5 GB spare
    code, detail = _status(studio_app.download_model, "img")
    assert code == 507 and "Delete something first" in detail


def test_cancel_answers_even_when_nothing_runs(api):
    assert studio_app.cancel_download("img") == {"cancelled": False, "download": None}


def test_delete_returns_the_bytes_freed(api):
    put(api.parts / "img.gguf", 300)
    assert studio_app.remove_model("img") == {"deleted": "img", "freed_bytes": 300}


def test_activate_checks_install_and_engine(api):
    assert _status(studio_app.activate_model, "img")[0] == 400
    put(api.parts / "n.gguf", 5)
    assert _status(studio_app.activate_model, "needs-next") == (
        409,
        "Needs an engine update",
    )
    put(api.parts / "img.gguf", 300)
    assert studio_app.activate_model("img") == {"active": "img", "kind": "image"}
    assert api.fake.calls == [("switch", "img")]


def _install_video(api):
    put(api.parts / "vid.gguf", 200)
    put(api.parts / "vid-vae.st", 100)


def test_model_video_runs_the_cli_and_records_the_result(api):
    _install_video(api)
    png = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(png, "PNG")
    req = studio_app.ModelVideoRequest(
        prompt="a cat",
        start_image="data:image/png;base64,"
        + base64.b64encode(png.getvalue()).decode(),
        frames=7,
    )
    snap = studio_app.generate_model_video(req)
    assert snap["state"] == "running" and snap["model_id"] == "vid"
    done = _wait_job(snap["id"])
    assert done["state"] == "done", done["message"]
    assert done["url"] == f"/outputs/{snap['id']}/raw.webm"  # fake file: ffmpeg fails
    assert (done["step"], done["steps"]) == (4, 4)
    argv = (api.outputs / snap["id"] / "argv.txt").read_text().split("\n")
    assert argv[:2] == ["-M", "vid_gen"]
    assert argv[argv.index("--video-frames") + 1] == "9"  # 7 rounded up to 4k+1
    assert argv[argv.index("-i") + 1].endswith("start.png")
    assert argv[argv.index("--diffusion-model") + 1] == str(api.parts / "vid.gguf")
    assert api.fake.calls == ["stop"]  # image servers stopped to free memory
    assert api.recorded and api.recorded[0][1] == "video"


def test_model_video_failure_shows_the_engine_log(api, monkeypatch):
    _install_video(api)
    monkeypatch.setenv("FAKE_SD_FAIL", "1")
    snap = studio_app.generate_model_video(studio_app.ModelVideoRequest(prompt="x"))
    done = _wait_job(snap["id"])
    assert done["state"] == "failed" and "out of memory" in done["message"]


def test_model_video_cancel_stops_the_process(api, monkeypatch):
    _install_video(api)
    monkeypatch.setenv("FAKE_SD_SLEEP", "5")
    snap = studio_app.generate_model_video(studio_app.ModelVideoRequest(prompt="x"))
    code, _ = _status(
        studio_app.generate_model_video, studio_app.ModelVideoRequest(prompt="y")
    )
    assert code == 409  # one video at a time
    t0 = time.time()
    got = studio_app.cancel_model_video(snap["id"])
    assert got["state"] == "cancelled" and time.time() - t0 < 5


def test_model_video_refusals(api):
    req = studio_app.ModelVideoRequest(prompt="x")
    assert _status(studio_app.generate_model_video, req)[0] == 409  # none installed
    req = studio_app.ModelVideoRequest(prompt="x", model_id="img")
    assert _status(studio_app.generate_model_video, req)[0] == 400
    req = studio_app.ModelVideoRequest(prompt="  ")
    assert _status(studio_app.generate_model_video, req)[0] == 400
    _install_video(api)
    req = studio_app.ModelVideoRequest(prompt="x", start_image="not base64!!")
    assert _status(studio_app.generate_model_video, req)[0] == 400
    req = studio_app.ModelVideoRequest(prompt="x", start_image_url="/outputs/../etc")
    assert _status(studio_app.generate_model_video, req)[0] == 400
    assert _status(studio_app.model_video_state, "nope")[0] == 404


def test_world_cards_say_why_they_cannot_run_when_worlds_is_missing(api, monkeypatch):
    w = entry("w", [], kind="world")
    api.use([w])
    monkeypatch.setitem(sys.modules, "worlds", None)  # import worlds -> ImportError
    card = studio_app.list_models()["models"][0]
    assert card["can_run"] is False
    assert card["run_note"] == "Needs the 3D world runtime, not set up yet"
    assert _status(studio_app.world_overview)[0] == 503


def test_world_cards_use_the_runner_status(api, monkeypatch):
    class FakeWorlds:
        WorldError = RuntimeError

        @staticmethod
        def runner_status(e):
            return False, "Needs an NVIDIA card"

    monkeypatch.setitem(sys.modules, "worlds", FakeWorlds)
    api.use([entry("w", [], kind="world")])
    card = studio_app.list_models()["models"][0]
    assert (card["can_run"], card["run_note"]) == (False, "Needs an NVIDIA card")
    assert _status(studio_app.world_start, "img", None)[0] == 404


def test_world_start_refuses_a_model_that_is_not_a_world(api):
    req = studio_app.WorldStartRequest(prompt="x")
    assert _status(studio_app.world_start, "img", req)[0] == 400
