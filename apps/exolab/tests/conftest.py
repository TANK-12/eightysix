"""Test setup: profiles and reports go to a scratch folder, never to
~/ForgeGameData or the docs library, and the app root is importable.

The environment is set before anything imports ``exolab``, because the
profile and report folders are read once at import time.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

SCRATCH = Path(tempfile.mkdtemp(prefix="exolab-tests-"))
os.environ["EXOLAB_DATA"] = str(SCRATCH / "data")
os.environ["EXOLAB_REPORT_DIR"] = str(SCRATCH / "reports")
APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from exolab import registry  # noqa: E402


@pytest.fixture(scope="session")
def reg() -> registry.Registry:
    return registry.Registry()


def prof(knobs: dict | None = None, overrides: dict | None = None) -> dict:
    """An inline profile, as the editor sends one."""
    return {"name": "test", "knobs": knobs or {}, "overrides": overrides or {}}


def every(reg: registry.Registry, kind: str, knob: str, mult: float) -> dict:
    """A profile turning one knob on every item of a kind."""
    return prof({kind: {i: {knob: mult} for i in reg.ids(kind)}})


def pytest_sessionfinish(session, exitstatus) -> None:
    shutil.rmtree(SCRATCH, ignore_errors=True)
