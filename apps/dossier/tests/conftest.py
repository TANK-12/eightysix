import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_saved_library_choice(tmp_path_factory, monkeypatch):
    """Tests never read Emerson's saved library folder (location.py)."""
    import location

    choice = tmp_path_factory.mktemp("choice") / "location.json"
    monkeypatch.setattr(location, "CHOICE_FILE", choice)
