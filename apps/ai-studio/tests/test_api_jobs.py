"""Warp-video jobs run in the background with a cancel route; cancelled work
is a 409; batch_count's bound is the real cap; the image edit route."""

import base64
import io
import json
import threading
import time

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from studio_fakes import studio  # noqa: F401
import app as studio_app  # pyright: ignore[reportMissingImports]
import config  # pyright: ignore[reportMissingImports]
import hybrid  # pyright: ignore[reportMissingImports]
import longform  # pyright: ignore[reportMissingImports]


class FakeLongform:
    """Writes state.json like LongformJob; its run() waits for a cancel file
    (or `go`) so a test can cancel it mid-way."""

    go = threading.Event()

    def __init__(self, job_id, work_dir, **kw):
        self.job_id = job_id
        self.work_dir = work_dir
        work_dir.mkdir(parents=True, exist_ok=True)
        self.state = {"job_id": job_id, "status": "running", "phase": "keyframes"}
        self._set()

    def _set(self, **fields):
        self.state.update(fields)
        (self.work_dir / "state.json").write_text(json.dumps(self.state))

    def run(self):
        deadline = time.time() + 5
        while time.time() < deadline and not FakeLongform.go.is_set():
            if (self.work_dir / longform.CANCEL_FILE).exists():
                self._set(status="cancelled")
                raise hybrid.Cancelled()
            time.sleep(0.01)
        return ["k1"], {"gpu": 1}

    def upscale_all(self, paths):
        return self.work_dir, 0.5

    def interpolate_and_encode(self, src, hold, fps, out):
        out.write_bytes(b"mp4")
        self._set(status="done", phase="done")
        return 0.25


@pytest.fixture
def api(studio, tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(config, "OUTPUTS_DIR", out)
    monkeypatch.setattr(studio_app, "LongformJob", FakeLongform)
    monkeypatch.setattr(studio_app, "_require_active_model", lambda: None)
    monkeypatch.setattr(
        studio_app.model_manager, "get_active_entry", lambda: {"settings": {}}
    )
    records = []
    monkeypatch.setattr(studio_app.library, "record", lambda *a: records.append(a))
    FakeLongform.go = threading.Event()
    studio.out = out
    studio.records = records
    return studio


def _wait_state(job_id, want, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = studio_app.job_state(job_id)
        if st["status"] == want and (want != "done" or "total_seconds" in st):
            return st
        time.sleep(0.02)
    raise AssertionError(studio_app.job_state(job_id))


def test_video_answers_at_once_and_finishes_in_the_background(api):
    r = studio_app.generate_video(studio_app.VideoRequest(prompt="a road"))
    assert r["status"] == "running" and r["url"] is None
    st = studio_app.job_state(r["id"])
    assert st["status"] == "running" and st["url"] == f"/outputs/{r['id']}/final.mp4"
    FakeLongform.go.set()
    st = _wait_state(r["id"], "done")
    assert st["total_seconds"] >= 0.75 and st["frame_count"] == 1
    assert api.records and api.records[0][0] == r["id"]


def test_cancel_route_stops_a_running_video(api):
    r = studio_app.generate_video(studio_app.VideoRequest(prompt="a road"))
    got = studio_app.cancel_job(r["id"])
    assert got == {"id": r["id"], "cancel_requested": True}
    assert _wait_state(r["id"], "cancelled")["status"] == "cancelled"
    assert api.records == []


def test_cancel_route_refuses_bad_and_unknown_ids(api):
    for bad, code in (("../x", 400), ("nosuchjob", 404)):
        with pytest.raises(HTTPException) as e:
            studio_app.cancel_job(bad)
        assert e.value.status_code == code


def test_wait_true_keeps_the_old_blocking_reply(api):
    FakeLongform.go.set()
    r = studio_app.generate_video(studio_app.VideoRequest(prompt="a road", wait=True))
    assert r["url"].endswith("final.mp4") and r["total_seconds"] >= 0.75


def test_cancelled_is_a_409(api):
    resp = studio_app._cancelled(None, hybrid.Cancelled())  # type: ignore[arg-type]
    assert resp.status_code == 409 and json.loads(bytes(resp.body)) == {
        "detail": "cancelled"
    }


def test_batch_count_bound_is_the_real_cap():
    assert studio_app.ImageRequest(prompt="x", batch_count=8).batch_count == 8
    with pytest.raises(ValidationError):
        studio_app.ImageRequest(prompt="x", batch_count=9)


def _png(size=(300, 200)):
    buf = io.BytesIO()
    Image.new("RGB", size, "blue").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def test_edit_runs_img2img_on_the_given_picture(api, monkeypatch):
    calls = {}

    def fake_img2img(**kw):
        calls.update(kw)
        Image.new("RGB", (kw["width"], kw["height"])).save(kw["out_path"])

    monkeypatch.setattr(studio_app.engine, "img2img", fake_img2img)
    monkeypatch.setattr(
        studio_app.model_manager,
        "get_active_entry",
        lambda: {"settings": {"width": 512, "height": 512, "steps": 7}},
    )
    req = studio_app.EditRequest(
        prompt="make it red", start_image=_png(), upscale=False
    )
    r = studio_app.generate_edit(req)
    assert r["url"] == f"/outputs/{r['id']}/final.jpg"
    assert (calls["width"], calls["height"]) == (512, 320)  # 300x200 at long side 512
    assert calls["strength"] == 0.6 and calls["steps"] == 7
    assert (api.out / r["id"] / "final.jpg").is_file()


def test_edit_needs_a_picture_and_a_valid_one(api):
    for req, code in (
        (studio_app.EditRequest(prompt="x"), 400),
        (studio_app.EditRequest(prompt="x", start_image="nope!!"), 400),
        (studio_app.EditRequest(prompt="x", start_image_url="/outputs/a/../b"), 400),
    ):
        with pytest.raises(HTTPException) as e:
            studio_app.generate_edit(req)
        assert e.value.status_code == code
    with pytest.raises(ValidationError):
        studio_app.EditRequest(prompt="x", strength=0.99)
