import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import web_app


@pytest.fixture
def game_root(tmp_path, monkeypatch):
    root = tmp_path / "eightysix"
    root.mkdir()
    monkeypatch.setenv("EIGHTYSIX_ROOT", str(root))
    return root


@pytest.fixture
def client():
    return TestClient(web_app.app)


@pytest.fixture(autouse=True)
def fresh_launch_state(monkeypatch, tmp_path):
    """No launch or test run carried over from another test (or a real run)."""
    monkeypatch.setattr(web_app, "_recent_launches", {})
    monkeypatch.setattr(web_app, "_tests_proc", None)
    monkeypatch.setattr(web_app, "TESTS_PID", tmp_path / "tests.pid")
