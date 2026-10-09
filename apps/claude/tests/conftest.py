import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parent.parent / "shared"))

import pytest


@pytest.fixture(autouse=True)
def private_main_config(tmp_path, monkeypatch):
    """Profiles link into the default profile's config; never the real one."""
    import runner

    monkeypatch.setattr(runner, "MAIN_CONFIG", tmp_path / "main-config")
