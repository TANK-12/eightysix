"""Forge's window lets a page use the microphone, never the camera
(Acchan's voice button, 2026-09-27)."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import forge  # noqa: E402
import forge_popout  # noqa: E402


def test_only_the_microphone_is_allowed():
    assert forge.media_request_ok(audio=True, video=False, uri="file:///hub/index.html")
    assert not forge.media_request_ok(True, False)  # no page known: refused
    assert not forge.media_request_ok(audio=False, video=True)
    assert not forge.media_request_ok(audio=True, video=True)
    assert not forge.media_request_ok(audio=False, video=False)
    assert not forge.media_request_ok(audio=True, video=False, display=True)


def test_only_forge_pages_get_the_microphone():
    for uri in (
        "file:///home/ejb/Forge/hub/index.html",
        "http://127.0.0.1:8467/",
        "http://localhost:8450/app",
        "http://[::1]:8000/",
    ):
        assert forge_popout.media_request_ok(True, False, uri=uri), uri
    for uri in (
        "https://example.com/",
        "http://127.0.0.1.example.com/",
        "http://localhost.evil.net/",
        "about:blank",
        "",
        None,
    ):
        assert not forge_popout.media_request_ok(True, False, uri=uri), uri


def test_the_request_handler_passes_the_page_and_screen_flags():
    src = Path(forge_popout.__file__).read_text()
    body = src[src.index("    def on_permission") :]
    assert "user_media_permission_is_for_display_device" in body
    assert "_view.get_uri()" in body


def test_this_webkit_can_tell_a_screen_request():
    import gi

    gi.require_version("WebKit2", "4.1")
    from gi.repository import WebKit2

    assert callable(WebKit2.user_media_permission_is_for_display_device)


def test_the_window_asks_for_it_and_app_frames_may_use_it():
    src = Path(forge.__file__).read_text()
    assert "allow_microphone(webview)" in src
    hub = (Path(forge.__file__).parent / "hub" / "index.html").read_text()
    found = re.search(r'frame\.allow = "([^"]*)"', hub)
    assert found, "the hub's app frame has no allow list"
    allow = found.group(1).split("; ")
    assert "microphone" in allow and "camera" not in allow


def test_a_popped_out_app_may_use_the_microphone_too():
    """Relay task 120: a pop-out's own view had no media stream and no
    permission answer, so an app's mic button there was refused."""
    src = Path(forge_popout.__file__).read_text()
    assert "allow_microphone(view)" in src[src.index("    def open(self") :]


def test_allow_microphone_turns_media_on_and_answers_requests():
    seen = {}

    class Settings:
        def set_property(self, name, value):
            seen[name] = value

    class View:
        def get_settings(self):
            return Settings()

        def connect(self, signal, handler):
            seen[signal] = handler

    handler = forge_popout.allow_microphone(View())
    assert seen["enable-media-stream"] is True
    assert seen["permission-request"] is handler
    assert handler(None, object()) is False  # not a media request: WebKit decides
    assert forge.media_request_ok is forge_popout.media_request_ok  # one rule
