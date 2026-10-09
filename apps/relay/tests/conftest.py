import os
import sys

import pytest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(APP, "..", "..", "shared")
for path in (APP, SHARED):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Every test gets its own empty Relay data folder."""
    monkeypatch.setenv("RELAY_DATA_DIR", str(tmp_path / "relay"))
    # the local model pick lives in Jan's per-app settings: never the real ones
    monkeypatch.setenv("FORGE_JAN_SETTINGS_DIR", str(tmp_path / "jan"))
    # session names: no real crew boards, no real Claude app
    monkeypatch.setenv("CREW_HOME", str(tmp_path / "crew"))
    monkeypatch.setenv("FORGE_APPS_DIR", str(tmp_path / "apps"))
    import web_app

    monkeypatch.setattr(web_app, "_run_names", {})
    import store

    store.ensure()
    # the Jan front desk is on by default; tests that want it turn it on
    # the local stand-in too: tests that want it turn it on with a fake Jan
    store.save_settings({"whatsapp_frontdesk": "off", "whatsapp_fallback": "off"})
    return tmp_path / "relay"
