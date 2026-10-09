import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import autostart  # noqa: E402

JAN = """[Desktop Entry]
Type=Application
Name=Jan
Exec=/usr/bin/flatpak run ai.jan.Jan
X-GNOME-Autostart-enabled=true
"""


def test_lists_entries(tmp_path):
    (tmp_path / "ai.jan.Jan.desktop").write_text(JAN)
    (tmp_path / "notes.txt").write_text("ignored")
    rows = autostart.list_entries(str(tmp_path))
    assert rows == [{"file": "ai.jan.Jan.desktop", "name": "Jan", "enabled": True}]


def test_toggle_round_trip(tmp_path):
    f = tmp_path / "ai.jan.Jan.desktop"
    f.write_text(JAN)
    autostart.set_enabled(str(tmp_path), "ai.jan.Jan.desktop", False)
    assert autostart.list_entries(str(tmp_path))[0]["enabled"] is False
    assert "Hidden=true" in f.read_text()
    autostart.set_enabled(str(tmp_path), "ai.jan.Jan.desktop", True)
    assert autostart.list_entries(str(tmp_path))[0]["enabled"] is True
    assert f.read_text() == JAN


def test_refuses_path_escape(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        autostart.set_enabled(str(tmp_path), "../evil.desktop", False)
