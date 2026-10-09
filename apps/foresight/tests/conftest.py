import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dossier_link  # noqa: E402
import store  # noqa: E402


@pytest.fixture(autouse=True)
def _private_data_root(tmp_path_factory, monkeypatch):
    """Every test gets its own data folder. Without this, a test that reached
    store.data_root() followed Emerson's real Dossier choice and left a write
    probe in his ForesightData folder on every run."""
    base = tmp_path_factory.mktemp("data-root")
    monkeypatch.setattr(dossier_link, "DOSSIER_CHOICE", base / "no-location.json")
    monkeypatch.setattr(store, "USB_ROOT", base / "no-usb" / "ForesightData")
    monkeypatch.setattr(store, "LOCAL_ROOT", base / "local")
    monkeypatch.setattr(store, "_resolved", None)
