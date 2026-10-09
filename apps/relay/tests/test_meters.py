from pathlib import Path

import meters


def test_env_for_sets_config_dir_only_for_profiles(monkeypatch):
    monkeypatch.setattr(
        meters,
        "accounts",
        lambda: {"default": Path("/home/x/.claude"), "hey": Path("/p/hey")},
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/leaked/from/parent")
    monkeypatch.setenv("CLAUDECODE", "1")
    assert "CLAUDE_CONFIG_DIR" not in meters.env_for("default")
    assert "CLAUDECODE" not in meters.env_for("default")
    assert meters.env_for("hey")["CLAUDE_CONFIG_DIR"] == "/p/hey"
    assert ".local/bin" in meters.env_for("hey")["PATH"]


def test_simplify_usage_answer():
    raw = {
        "five_hour": {"utilization": 42.0, "resets_at": "2026-09-29T12:00:00Z"},
        "seven_day": {"utilization": 17.0, "resets_at": "x"},
        "_age": 30,
    }
    assert meters.simplify(raw) == {
        "five": 42.0,
        "week": 17.0,
        "resets": "2026-09-29T12:00:00Z",
        "week_resets": "x",
        "age": 30,
    }
    assert meters.simplify({})["five"] is None


def test_token_expired_reads_the_credentials(tmp_path):
    (tmp_path / ".credentials.json").write_text(
        '{"claudeAiOauth": {"expiresAt": 1000000}}'
    )
    assert meters.token_expired(tmp_path, now=2000)
    assert not meters.token_expired(tmp_path, now=500)
    assert not meters.token_expired(tmp_path / "missing", now=2000)


def test_refresh_login_runs_a_tiny_call_at_most_every_gap(monkeypatch):
    monkeypatch.setattr(meters, "_refreshed", {})
    monkeypatch.setattr(meters, "accounts", lambda: {"hey": Path("/p/hey")})
    calls = []
    spawn = lambda argv, env: calls.append((argv, env["CLAUDE_CONFIG_DIR"]))
    assert meters.refresh_login("hey", now=10_000, spawn=spawn)
    assert not meters.refresh_login("hey", now=10_000 + 60, spawn=spawn)
    assert meters.refresh_login("hey", now=10_000 + meters.REFRESH_GAP, spawn=spawn)
    assert len(calls) == 2 and calls[0][1] == "/p/hey"
    assert "haiku" in calls[0][0] and "-p" in calls[0][0]


def test_read_refreshes_on_401_and_drops_stale_readings(monkeypatch, tmp_path):
    import urllib.error
    from email.message import Message

    class Usage:
        def all_configs(self):
            return {"default": tmp_path / "d", "hey": tmp_path / "h"}

        def fetch(self, config):
            if config.name == "d":
                raise urllib.error.HTTPError("u", 401, "Unauthorized", Message(), None)
            return {  # an old cache from before both windows reset
                "five_hour": {
                    "utilization": 10,
                    "resets_at": "2026-10-01T00:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 99,
                    "resets_at": "2026-10-05T00:00:00+00:00",
                },
                "_age": 4 * 86400,
            }

    monkeypatch.setattr(meters, "_usage", lambda: Usage())
    monkeypatch.setattr(meters, "_refreshed", {})
    refreshed = []
    monkeypatch.setattr(
        meters, "refresh_login", lambda name, now=None: refreshed.append(name) or True
    )
    got = meters.read(force=True)
    assert got["default"]["five"] is None and "refreshing" in got["default"]["error"]
    assert got["hey"]["week"] is None and "stale" in got["hey"]["error"]
    assert refreshed == ["default"]


def test_a_stale_reading_note_is_not_a_401():
    assert not meters.UNAUTHORISED.search("stale reading (401 min old)")
    assert meters.UNAUTHORISED.search("HTTP Error 401: Unauthorized")
