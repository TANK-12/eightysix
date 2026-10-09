"""The shared Jan helper: per-app model settings, and releasing idle models.

WHY THIS EXISTS
    Emerson asked on 2026-09-16 that every Jan-using app choose its own models,
    load them only when needed and release them when idle, "cause ram saving".
    The rules worth protecting are that a model doing work for ANY app or
    session is never released, that an app with a request in flight releases
    nothing, and that Jan itself is never started or stopped.

HOW TO RUN
    /usr/bin/python3 tests/test_forge_jan.py

    System python on purpose: shared/ has no virtualenv of its own, and the
    module is stdlib-only so every app's venv can import it.
"""

import os
import sys
import tempfile

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"),
)

import forge_jan  # noqa: E402

# Some tests swap release() for a stand-in without putting it back (the
# __main__ runner restores it; pytest does not), so keep the real one here.
REAL_RELEASE = forge_jan.release


def write_proc(proc_dir, pid, argv, utime=0, stime=0):
    """A fake /proc/<pid> for a llama-server: its command line and its CPU time."""
    folder = os.path.join(proc_dir, str(pid))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "cmdline"), "wb") as fh:
        fh.write(b"\0".join(a.encode() for a in argv) + b"\0")
    rest = ["S", "1", "1", "1", "0", "-1", "0", "0", "0", "0", "0"]
    rest += [str(utime), str(stime), "0", "0", "20", "0", "4", "0", "1000", "1", "2"]
    with open(os.path.join(folder, "stat"), "w") as fh:
        fh.write(f"{pid} (llama-server) " + " ".join(rest) + "\n")


def fake_jan(tmp):
    """A router and one loaded model, as Jan really runs them."""
    proc_dir = os.path.join(tmp, "proc")
    write_proc(
        proc_dir,
        300,
        [
            "/x/llama-server",
            "--models-preset",
            "/x/router.ini",
            "--host",
            "127.0.0.1",
            "--port",
            "53041",
        ],
    )
    write_proc(
        proc_dir,
        301,
        ["/x/llama-server", "--alias", "small-model", "--port", "45535"],
        utime=50,
    )
    return proc_dir


def test_each_app_keeps_its_own_models_and_idle_time():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["FORGE_JAN_SETTINGS_DIR"] = os.path.join(tmp, "jan")
        roles = ("chatter", "narrator")
        first = forge_jan.read_settings("janhollow", roles)
        assert first == {"models": {"chatter": "", "narrator": ""}, "idle_minutes": 5.0}

        forge_jan.write_settings(
            "janhollow", {"models": {"chatter": "small-model"}}, roles
        )
        forge_jan.write_settings("janhollow", {"idle_minutes": 12}, roles)
        forge_jan.write_settings(
            "dossier", {"models": {"triage": "other-model"}}, ("triage",)
        )

        mine = forge_jan.read_settings("janhollow", roles)
        assert mine["models"] == {"chatter": "small-model", "narrator": ""}
        assert mine["idle_minutes"] == 12.0  # one setting does not clear the other
        assert (
            forge_jan.read_settings("dossier", ("triage",))["models"]["triage"]
            == "other-model"
        )
        assert (
            forge_jan.read_settings("janhollow", roles)["models"].get("triage") is None
        )


def test_a_role_falls_back_to_the_apps_own_choice_then_to_jan():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["FORGE_JAN_SETTINGS_DIR"] = os.path.join(tmp, "jan")
        forge_jan._models_cache.update(ids=["a-model", "b-model"], checked=9e18)
        owner = forge_jan.AppJan("janhollow", ("chatter",), proc_dir=fake_jan(tmp))
        assert owner.model_for("chatter") == "a-model"  # nothing set: Jan's first
        assert owner.model_for("chatter", fallback="b-model") == "b-model"
        owner.update({"models": {"chatter": "picked"}})
        assert owner.model_for("chatter", fallback="b-model") == "picked"


def test_the_router_and_loaded_models_are_read_from_proc():
    with tempfile.TemporaryDirectory() as tmp:
        proc_dir = fake_jan(tmp)
        assert forge_jan.router_url(proc_dir) == "http://127.0.0.1:53041"
        assert forge_jan.loaded_models(proc_dir) == [
            "small-model"
        ]  # the router is not a model
        assert forge_jan.cpu_ticks(proc_dir) == {"small-model": 50}
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty, exist_ok=True)
        assert forge_jan.router_url(empty) is None  # Jan off: leave it alone


def test_a_model_is_released_only_after_a_whole_quiet_wait():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["FORGE_JAN_SETTINGS_DIR"] = os.path.join(tmp, "jan")
        proc_dir = fake_jan(tmp)
        released = []
        forge_jan.release = (
            lambda model, proc="/proc": bool(released.append(model)) or True
        )
        owner = forge_jan.AppJan(
            "janhollow", ("chatter",), proc_dir=proc_dir, log=lambda *a: None
        )
        owner.update({"idle_minutes": 1})
        with owner.using("small-model"):
            assert owner.check_idle(now=0) == []  # a request in flight holds it
        assert owner.check_idle(now=0) == []  # first sighting: nothing is idle yet
        write_proc(
            proc_dir, 301, ["/x/llama-server", "--alias", "small-model"], utime=99
        )
        assert owner.check_idle(now=30) == []  # it did work, so the wait restarts
        assert owner.check_idle(now=120) == ["small-model"]
        assert released == ["small-model"]


def test_only_this_apps_models_are_released():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["FORGE_JAN_SETTINGS_DIR"] = os.path.join(tmp, "jan")
        proc_dir = fake_jan(tmp)
        write_proc(
            proc_dir, 302, ["/x/llama-server", "--alias", "someone-elses"], utime=7
        )
        released = []
        forge_jan.release = (
            lambda model, proc="/proc": bool(released.append(model)) or True
        )
        owner = forge_jan.AppJan(
            "janhollow", ("chatter",), proc_dir=proc_dir, log=lambda *a: None
        )
        owner.update({"idle_minutes": 1})
        with owner.using("small-model"):
            pass
        owner.check_idle(now=0)
        assert owner.check_idle(now=120) == ["small-model"]
        assert "someone-elses" not in released  # another app's model is not ours
        released.clear()
        # Stopping the backend releases what this app loaded, and only that.
        assert owner.stop() == ["small-model"]
        assert released == ["small-model"]


def test_zero_minutes_keeps_models_loaded():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["FORGE_JAN_SETTINGS_DIR"] = os.path.join(tmp, "jan")
        proc_dir = fake_jan(tmp)
        forge_jan.release = lambda model, proc="/proc": True
        owner = forge_jan.AppJan(
            "janhollow", ("chatter",), proc_dir=proc_dir, log=lambda *a: None
        )
        owner.update({"idle_minutes": 0})
        with owner.using("small-model"):
            pass
        assert owner.check_idle(now=0) == [] and owner.check_idle(now=10_000) == []


if __name__ == "__main__":
    failures = 0
    real_release = forge_jan.release
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            forge_jan.release = real_release
            try:
                fn()
                print(f"PASS :: {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL :: {name} :: {e}")
    print()
    print("ALL PASS" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)


def test_router_key_is_read_from_the_router_environment(tmp_path):
    """Jan's router takes its unload key from LLAMA_API_KEY (2026-09-22)."""
    import forge_jan

    router = tmp_path / "4242"
    router.mkdir()
    (router / "cmdline").write_bytes(
        b"/x/llama-server\0--models-preset\0/p.ini\0--port\0555\0"
    )
    (router / "environ").write_bytes(b"HOME=/h\0LLAMA_API_KEY=secret123\0PATH=/b\0")
    child = tmp_path / "4243"
    child.mkdir()
    (child / "cmdline").write_bytes(b"/x/llama-server\0--alias\0m\0")
    assert forge_jan.router_key(str(tmp_path)) == "secret123"


def test_release_when_jan_has_gone_away_is_quiet(monkeypatch):
    # Acchan's shutdown failed twice (outputs/acchan.log) because Jan's router
    # was closing too: the unload hit "connection refused" and raised.
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(
        forge_jan, "router_url", lambda proc_dir="/proc": f"http://127.0.0.1:{port}"
    )
    monkeypatch.setattr(forge_jan, "router_key", lambda proc_dir="/proc": None)
    assert REAL_RELEASE("some-model") is False
