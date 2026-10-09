"""Bulk runs: the step sequence per chapter, with a fake API."""

from panelforge import batch


class _Job:
    def __init__(self):
        self.lines = []
        self.frac = 0.0

    def log(self, m):
        self.lines.append(m)

    def progress(self, f):
        self.frac = f

    def check(self):
        pass


def _fake_api(fail_on=None):
    calls = []

    def call(base, method, path, body=None, timeout=600.0):
        calls.append((method, path, body))
        return {"job_id": f"j{len(calls)}"}

    def wait(base, job_id, check=None):
        n = int(job_id[1:])
        path = calls[n - 1][1]
        state = "failed" if fail_on and fail_on in path else "done"
        return {"state": state, "log": [f"{path} {state}"]}

    return calls, call, wait


def test_batch_runs_every_step_per_chapter_in_order():
    calls, call, wait = _fake_api()
    job = _Job()
    res = batch.run_batch(
        "http://x",
        "s",
        ["0001", "0002"],
        ["detect", "analyze", "render"],
        {"render": {"style": "puppet25d"}},
        job,
        call,
        wait,
    )
    assert res == {"done": ["0001", "0002"], "failed": []}
    # gathering steps run for every chapter before any building step, so
    # the cast is complete before a line is voiced or drawn
    assert [p for _, p, _ in calls] == [
        "/api/chapters/s/0001/detect",
        "/api/chapters/s/0001/analyze",
        "/api/chapters/s/0002/detect",
        "/api/chapters/s/0002/analyze",
        "/api/chapters/s/0001/render",
        "/api/chapters/s/0002/render",
    ]
    assert calls[4][2] == {"style": "puppet25d"}
    assert job.lines[-1].startswith("batch finished: 2 chapters done, 0 failed")


def test_a_failed_step_stops_that_chapter_only():
    calls, call, wait = _fake_api(fail_on="0001/analyze")
    job = _Job()
    res = batch.run_batch(
        "http://x",
        "s",
        ["0001", "0002"],
        ["detect", "analyze", "script"],
        {},
        job,
        call,
        wait,
    )
    assert res == {"done": ["0002"], "failed": ["0001"]}
    paths = [p for _, p, _ in calls]
    assert "/api/chapters/s/0001/script/build" not in paths
    assert "/api/chapters/s/0002/script/build" in paths
    assert any("[0001] stopped at analyze" in l for l in job.lines)


def test_fetch_step_uses_the_chapter_number_and_group():
    calls, call, wait = _fake_api()
    batch.run_batch(
        "http://x", "s", ["0007"], ["fetch"], {"group": "WebToon"}, _Job(), call, wait
    )
    assert calls[0] == (
        "POST",
        "/api/fetch/chapters",
        {"series": "s", "chapters": [7.0], "group": "WebToon"},
    )


def test_run_endpoint_expands_a_range(tmp_path, monkeypatch):
    import importlib

    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    from panelforge import jobs, paths

    importlib.reload(paths)
    importlib.reload(jobs)
    from fastapi.testclient import TestClient

    import web_app

    started = {}
    monkeypatch.setattr(
        batch,
        "run_batch",
        lambda *a, **k: (started.setdefault("args", a), {"done": [], "failed": []})[1],
    )
    c = TestClient(web_app.app)
    r = c.post(
        "/api/series/s/run", json={"first": 1, "last": 3, "steps": ["detect", "render"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["chapters"] == ["0001", "0002", "0003"]
    r = c.post("/api/series/s/run", json={"first": 1, "steps": ["nope"]})
    assert r.status_code == 400


def test_voices_are_cast_between_gathering_and_building():
    calls, call, wait = _fake_api()
    batch.run_batch(
        "http://x",
        "s",
        ["0001", "0002"],
        ["analyze", "voice"],
        {},
        _Job(),
        call,
        wait,
    )
    assert [p for _, p, _ in calls] == [
        "/api/chapters/s/0001/analyze",
        "/api/chapters/s/0002/analyze",
        "/api/series/s/cast/voices/auto",
        "/api/chapters/s/0001/voice",
        "/api/chapters/s/0002/voice",
    ]
    calls.clear()
    batch.run_batch(
        "http://x", "s", ["0001"], ["voice"], {"cast": False}, _Job(), call, wait
    )
    assert [p for _, p, _ in calls] == ["/api/chapters/s/0001/voice"]
