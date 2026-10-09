import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import browse  # noqa: E402


@pytest.fixture(autouse=True)
def forget_eject(monkeypatch):
    """browse.EJECTED lives as long as the process: one test's eject must
    not make the next test's drive look ejected."""
    monkeypatch.setattr(browse, "EJECTED", set())
