"""Shared pytest setup for the app's tests and every curio's tests.

Puts the app folder on sys.path (store, registry, kit, web_app) and points the
data folder at a temp folder for every test, so no test touches
~/ForgeGameData. A curio's test gets its server.py with load_curio("<id>").
"""

import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    folder = tmp_path / "afterglow-data"
    monkeypatch.setenv("AFTERGLOW_DATA", str(folder))
    return folder


@pytest.fixture
def load_curio():
    import registry

    return registry.load_server
