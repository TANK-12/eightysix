"""Relay task 120: does a real microphone reach speech to text from a Forge page?

    /usr/bin/python3 tests/browser/check_mic_webkit.py

Needs the voice service (apps/voice, port 8467) running; it says the test
line and transcribes the recordings. Nothing is heard and nothing shows:

- a temporary PipeWire test mic (pw-loopback: a sink the line is played into,
  a source WebKit records from), removed again at the end, and the default
  sink and source put back if anything moved them;
- the WebKit side runs in a private D-Bus session with a headless mutter and
  its own XDG_DATA_HOME, so no portal dialog can reach Emerson's desktop and
  his portal permission store is never touched.

Two views, made with Forge's own code: the hub's (forge.hub_webview() plus
forge_popout.allow_microphone, a file:// hub page holding an
http://127.0.0.1 app frame with allow="microphone") and a pop-out's (a plain
view plus allow_microphone, the app page at the top). The page loads only
/shared/forge_voice.js, as Forge apps do. In each view the line is played
into the test mic three times: recorded through MediaRecorder (the old way,
for the record), through ForgeVoice.mic() (shared/forge_mic.js, loaded on
first use), and by pressing ForgeVoice.micButton twice, which dictates into a
text box through the voice service like the real button.

PASS needs, in both views, ForgeMic's recording to be a 16 kHz WAV with sound
in it that the voice service hears as the line, and the dictation button to
put the line in its text box. Measured 2026-10-08 on WebKitGTK 2.54: the
MediaRecorder recording of a real mic is 0 bytes (the track reports sample
rate 0), which is why every browser mic in Forge failed. About 40 s.
Exit status 1 on any FAIL.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# before WebKit starts: no GPU (the other WebKit checks run the same way)
os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")

ROOT = Path(__file__).resolve().parents[2]
VOICE = os.environ.get("FORGE_VOICE_URL", "http://127.0.0.1:8467")
LINE = "What time is it?"
SINK = "forge_mic_check_in"
SOURCE = "forge_mic_check_mic"
LABEL = "Forge-Mic-Check"
SECONDS = 4


def voice_call(path: str, body: bytes, kind: str) -> tuple[int, bytes]:
    req = urllib.request.Request(
        VOICE + path,
        data=body,
        headers={"X-Forge": "1", "Content-Type": kind},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def words(text: str) -> str:
    return " ".join(re.findall(r"[a-z']+", text.lower()))


# --- outer: test mic, private session, clean-up ------------------------------


def pactl(*args: str) -> str:
    out = subprocess.run(["pactl", *args], capture_output=True, text=True)
    return out.stdout.strip()


def outer() -> int:
    for tool in ("pw-loopback", "pw-play", "pactl", "mutter", "dbus-run-session"):
        if not shutil.which(tool):
            print(f"FAIL {tool} is not installed")
            return 1
    status, wav = voice_call(
        "/api/tts", json.dumps({"text": LINE}).encode(), "application/json"
    )
    if status != 200:
        print(f"FAIL the voice service did not say the line: {status} {wav[:200]!r}")
        return 1
    before = (pactl("get-default-sink"), pactl("get-default-source"))
    loop = subprocess.Popen(
        [
            "pw-loopback",
            f"--capture-props=media.class=Audio/Sink node.name={SINK} "
            f"node.description={LABEL}-In audio.channels=1 audio.position=[MONO]",
            f"--playback-props=media.class=Audio/Source node.name={SOURCE} "
            f"node.description={LABEL} audio.channels=1 audio.position=[MONO]",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            if SOURCE in pactl("list", "short", "sources"):
                break
            time.sleep(0.1)
        else:
            print("FAIL the test mic did not appear")
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "line.wav").write_bytes(wav)
            Path(tmp, "data").mkdir()
            script = (
                "sock=forge-mic-check-$$; mutter --headless --wayland --no-x11 "
                '--virtual-monitor 800x600 --wayland-display "$sock" '
                '>"$1/mutter.log" 2>&1 & mp=$!; '
                'for _ in $(seq 100); do [ -S "$XDG_RUNTIME_DIR/$sock" ] && break; '
                "sleep 0.1; done; "
                # WebKit asks the camera portal even for a microphone; with no
                # stored answer the portal would wait on a dialog nobody sees.
                # 'no' is what Forge has on this laptop, and audio still works.
                "gdbus call --session --dest org.freedesktop.impl.portal.PermissionStore "
                "--object-path /org/freedesktop/impl/portal/PermissionStore "
                "--method org.freedesktop.impl.portal.PermissionStore.SetPermission "
                "devices true camera '' \"['no']\" >/dev/null; "
                'WAYLAND_DISPLAY=$sock GDK_BACKEND=wayland "$2" "$3"; rc=$?; '
                "kill $mp 2>/dev/null; wait $mp 2>/dev/null; exit $rc"
            )
            # the private bus's portal and permission store keep their data in tmp
            env = dict(os.environ, FORGE_MIC_CHECK_DIR=tmp, XDG_DATA_HOME=f"{tmp}/data")
            env.pop("DISPLAY", None)
            done = subprocess.run(
                [
                    "dbus-run-session",
                    "--",
                    "bash",
                    "-c",
                    script,
                    "_",
                    tmp,
                    sys.executable,
                    str(Path(__file__).resolve()),
                ],
                env=env,
                timeout=120,
            )
            return done.returncode
    finally:
        loop.terminate()
        loop.wait(timeout=10)
        for which, name in zip(("sink", "source"), before):
            if name and pactl(f"get-default-{which}") != name:
                pactl(f"set-default-{which}", name)
                print(f"info put the default {which} back to {name}")


# --- inner: the Forge-like WebKit view ---------------------------------------

HUB = """<!doctype html><html><body style="margin:0">
<iframe id="f" style="width:100%%;height:500px;border:0"></iframe>
<script>
const f = document.getElementById("f");
f.allow = "fullscreen; microphone; gamepad";
f.src = "http://127.0.0.1:%d/probe.html";
addEventListener("message", (e) => { if (e.data && e.data.title) document.title = e.data.title; });
</script></body></html>"""

PROBE = """<!doctype html><textarea id="box"></textarea>
<script src="/shared/forge_voice.js"></script><script>
const say = (title) => (window.top === window ? (document.title = title) : parent.postMessage({ title }, "*"));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const upload = (name, blob) => fetch("/upload/" + name, { method: "POST", body: blob });
let turn = 0;
const play = async (name) => { say("PLAY " + name + " " + ++turn); await wait(%d); };
(async () => {
  const out = {};
  try {
    // record from the test mic, not whatever the default is
    const first = await navigator.mediaDevices.getUserMedia({ audio: true });
    first.getTracks().forEach((t) => t.stop());
    const mic = (await navigator.mediaDevices.enumerateDevices())
      .find((d) => d.kind === "audioinput" && d.label.includes("%s"));
    if (!mic) throw new Error("the test mic is not in the device list");
    const gum = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = () => gum({ audio: { deviceId: { exact: mic.deviceId } } });

    // the old way: MediaRecorder
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream), parts = [];
      rec.ondataavailable = (e) => parts.push(e.data);
      const stopped = new Promise((r) => (rec.onstop = r));
      rec.start();
      await play("old");
      rec.stop(); await stopped;
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(parts, { type: rec.mimeType || "audio/webm" });
      out.old = { bytes: blob.size, type: blob.type, rate: stream.getAudioTracks()[0].getSettings().sampleRate };
      await upload("old", blob);
    } catch (e) { out.old = { error: e.message }; }

    // the new way: ForgeMic, loaded by forge_voice.js
    const rec = await (await ForgeVoice.mic()).start();
    await play("new");
    const wav = await rec.stop();
    out.new = { bytes: wav.size, type: wav.type, rate: rec.rate, peak: rec.peak, silent: rec.silent(), seconds: rec.seconds() };
    await upload("new", wav);

    // the dictation button, pressed twice, through the voice service
    const box = document.getElementById("box");
    const button = ForgeVoice.micButton(box, { app: "anywhere" });
    document.body.appendChild(button);
    button.click();
    for (let i = 0; i < 50 && button.dataset.state !== "listening"; i++) await wait(100);
    await play("button");
    button.click();
    for (let i = 0; i < 600 && button.dataset.state !== "idle"; i++) await wait(100);
    out.button = { state: button.dataset.state, title: button.title, text: box.value };
  } catch (e) { out.error = e.message; }
  say("DONE " + JSON.stringify(out));
})();
</script>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the probe page and /shared/, and keeps uploads in .got."""

    got: dict[str, bytes] = {}

    def translate_path(self, path):
        if path.startswith("/shared/"):
            return str(ROOT / "shared" / Path(path).name)
        return super().translate_path(path)

    def do_POST(self):
        name = self.path.rsplit("/", 1)[-1]
        self.got[name] = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def run_view(url: str, line: Path, hub: bool) -> dict | None:
    """Load `url` in a view made like the hub's (hub=True) or a pop-out's;
    the page's report."""
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import GLib, Gtk, WebKit2

    sys.path.insert(0, str(ROOT))
    import forge
    import forge_popout

    result: dict = {}
    win = Gtk.Window()
    win.set_default_size(640, 480)
    view = forge.hub_webview() if hub else WebKit2.WebView()
    forge_popout.allow_microphone(view)
    if hub:
        for prop in (
            "allow-file-access-from-file-urls",
            "allow-universal-access-from-file-urls",
        ):
            view.get_settings().set_property(prop, True)  # as forge.py sets them

    def on_title(v, _prop):
        title = v.get_title() or ""
        if title.startswith("PLAY "):
            subprocess.Popen(["pw-play", "--target", SINK, str(line)])
        elif title.startswith("DONE "):
            result.update(json.loads(title[5:]))
            Gtk.main_quit()

    def on_timeout():
        Gtk.main_quit()
        return False

    view.connect("notify::title", on_title)
    win.add(view)
    win.show_all()
    GLib.timeout_add_seconds(90, on_timeout)
    view.load_uri(url)
    Gtk.main()
    win.destroy()
    return result or None


def judge(name: str, got: dict | None, wav: bytes) -> bool:
    """Print what one view did; True when every check passed."""
    if not got:
        print(f"FAIL {name}: no answer from the page in 90 s")
        return False
    if got.get("error"):
        print(f"FAIL {name}: the page said {got['error']}")
        return False
    print(f"info {name} MediaRecorder (old way): {json.dumps(got.get('old'))}")
    new = got.get("new") or {}
    print(f"info {name} ForgeMic: {json.dumps(new)}")
    ok = True
    head_ok = (
        wav[:4] == b"RIFF"
        and wav[8:12] == b"WAVE"
        and int.from_bytes(wav[24:28], "little") == 16000
    )
    print(
        ("PASS" if head_ok else "FAIL")
        + f" {name}: ForgeMic gave a 16 kHz WAV ({len(wav)} bytes)"
    )
    ok &= head_ok
    loud = not new.get("silent", True)
    print(
        ("PASS" if loud else "FAIL")
        + f" {name}: the recording has sound in it (peak {new.get('peak')})"
    )
    ok &= loud
    status, body = voice_call("/api/stt?app=anywhere", wav, "audio/wav")
    text = json.loads(body).get("text", "") if status == 200 else ""
    heard = status == 200 and words(text) == words(LINE)
    print(
        ("PASS" if heard else "FAIL")
        + f" {name}: speech to text heard the line: {status} {text or body[:160]!r}"
    )
    ok &= heard
    button = got.get("button") or {}
    typed = button.get("state") == "idle" and words(button.get("text", "")) == words(
        LINE
    )
    print(
        ("PASS" if typed else "FAIL")
        + f" {name}: the dictation button typed the line: {json.dumps(button)}"
    )
    ok &= typed
    return ok


def inner(tmp: Path) -> int:
    www = tmp / "www"
    www.mkdir()
    (www / "probe.html").write_text(PROBE % (SECONDS * 1000, LABEL))
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(www))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    hub = tmp / "hub.html"
    hub.write_text(HUB % port)
    ok = True
    for name, url, is_hub in (
        ("hub", hub.as_uri(), True),
        ("pop-out", f"http://127.0.0.1:{port}/probe.html", False),
    ):
        Handler.got.clear()
        got = run_view(url, tmp / "line.wav", is_hub)
        old = Handler.got.get("old", b"")
        if old:
            status, body = voice_call("/api/stt?app=anywhere", old, "audio/webm")
            print(
                f"info {name} MediaRecorder to /api/stt: {status} {body[:120].decode(errors='replace')}"
            )
        ok &= judge(name, got, Handler.got.get("new", b""))
    server.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    inside = os.environ.get("FORGE_MIC_CHECK_DIR")
    sys.exit(inner(Path(inside)) if inside else outer())
