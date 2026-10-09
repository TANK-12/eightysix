"""Foundation: paths, atomic store, jobs, model budget, app wiring."""

import importlib

import pytest


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    from panelforge import jobs, models, paths

    importlib.reload(paths)
    importlib.reload(jobs)
    importlib.reload(models)
    paths.ensure_roots()
    return tmp_path


def test_slugs():
    from panelforge import paths

    assert paths.slug("Bad Born Blood!") == "bad-born-blood"
    assert paths.slug("???") == "untitled"
    assert paths.chapter_slug(1) == "0001"
    assert paths.chapter_slug(12.5) == "0012.5"
    assert sorted([paths.chapter_slug(x) for x in (10, 2, 2.5)]) == [
        "0002",
        "0002.5",
        "0010",
    ]


def test_store_roundtrip_and_update(data):
    from panelforge import store

    p = data / "a" / "doc.json"
    assert store.read(p, {"x": 0}) == {"x": 0}
    store.write(p, {"schema": 1, "x": 1})
    store.update(p, lambda d: {**d, "x": d["x"] + 1})
    assert store.read(p) == {"schema": 1, "x": 2}
    assert not [f for f in p.parent.iterdir() if f.name.startswith(".tmp-")]


def test_job_runs_logs_and_cancels(data):
    from panelforge import jobs

    def work(job):
        job.log("step")
        job.progress(0.5)
        return 42

    j = jobs.wait(jobs.start("t", "test", work))
    assert j.state == "done" and j.result == 42 and j.frac == 1.0
    assert (data / "jobs" / f"{j.id}.json").exists()

    def slow(job):
        for _ in range(200):
            job.check()
            import time

            time.sleep(0.01)

    j2 = jobs.start("t", "slow", slow, lane="other")
    j2.cancel()
    assert jobs.wait(j2).state == "cancelled"

    j3 = jobs.wait(jobs.start("t", "boom", lambda job: 1 / 0))
    assert j3.state == "failed" and "ZeroDivisionError" in j3.error


def test_model_budget_refuses(data, monkeypatch):
    from panelforge import models

    monkeypatch.setattr(models, "BUDGET_BYTES", 10)
    with pytest.raises(models.BudgetExceeded):
        models.ensure("x", "http://127.0.0.1:9/none", "m.onnx", 1, "test", "test")


def test_app_health(data):
    from fastapi.testclient import TestClient

    import web_app

    importlib.reload(web_app)
    r = TestClient(web_app.app).get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True
