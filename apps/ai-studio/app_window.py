#!/usr/bin/env python3
"""Desktop launcher for AI Studio.

Starts the FastAPI backend (which owns sd-server's lifecycle itself -- see
model_manager.py) and opens a native app window (GTK + WebKit2, no browser
chrome) pointed at the UI. Closing the window stops the backend, which in
turn tears down sd-server via its shutdown hook. This is what the .desktop
launcher runs.
"""
import os
import signal
import subprocess
import sys
import time
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2, GLib  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_URL = "http://127.0.0.1:8420"


def url_up(url, timeout=2):
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False


class ServerManager:
    def __init__(self):
        self.app_proc = None

    def start(self):
        log_dir = os.path.join(ROOT, "outputs")
        os.makedirs(log_dir, exist_ok=True)
        app_log = open(os.path.join(log_dir, "app.log"), "ab")

        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = os.path.join(ROOT, "bin") + os.pathsep + env.get("LD_LIBRARY_PATH", "")

        self.app_proc = subprocess.Popen(
            [os.path.join(ROOT, ".venv", "bin", "uvicorn"), "app:app",
             "--host", "127.0.0.1", "--port", "8420"],
            cwd=os.path.join(ROOT, "src"), env=env,
            stdout=app_log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        # sd-server startup (model load onto the GPU) can take a while, so
        # give this a generous window before giving up.
        for _ in range(180):
            if url_up(APP_URL):
                break
            time.sleep(0.5)

    def stop(self):
        proc = self.app_proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=15)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass


def main():
    GLib.set_prgname("AI Studio")

    servers = ServerManager()
    servers.start()

    win = Gtk.Window(title="AI Studio")
    win.set_default_size(1280, 860)

    webview = WebKit2.WebView()
    webview.load_uri(APP_URL)
    win.add(webview)

    def on_destroy(*_args):
        servers.stop()
        Gtk.main_quit()

    win.connect("destroy", on_destroy)

    def handle_sigterm(*_args):
        GLib.idle_add(win.close)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    sys.exit(main())
