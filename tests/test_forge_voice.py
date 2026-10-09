"""Tests for shared/forge_voice.py (stdlib unittest; run: python3 -m unittest tests/test_forge_voice.py)."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import forge_voice as fv  # noqa: E402

WAKE = {
    "claude": ["claude", "cloud", "clawed", "tetsu"],
    "jan": ["jan", "acchan", "a chan"],
}


class SpeechText(unittest.TestCase):
    def test_markdown_becomes_sentences(self):
        md = "# Done\n\n- Fixed the **parser**\n- Added `tests`\n\nSee [the docs](https://x.io/a) or https://www.github.com/foo/bar"
        self.assertEqual(
            fv.speech_text(md),
            "Done. Fixed the parser. Added tests. See the docs or a link to github.com/foo/bar.".replace(
                "github.com/foo/bar", "github.com"
            ),
        )

    def test_code_and_tables_are_not_read_out(self):
        md = "Here it is:\n```python\nprint('x')\n```\n| a | b |\n|---|---|\n| 1 | 2 |\nThat's all."
        out = fv.speech_text(md)
        self.assertNotIn("print", out)
        self.assertNotIn("|", out)
        self.assertTrue(out.endswith("The code is on screen."))

    def test_limits(self):
        text = "One. Two. Three. Four."
        self.assertEqual(fv.speech_text(text, max_sentences=3), "One. Two. Three.")
        long = "Short one. " + "word " * 400
        self.assertLessEqual(len(fv.speech_text(long, max_chars=100)), 103)
        self.assertEqual(fv.speech_text(""), "")


class CleanHeard(unittest.TestCase):
    def test_noise_and_hallucinations_are_dropped(self):
        for heard in [
            "[BLANK_AUDIO]",
            " Thank you. ",
            "(music playing)",
            "you",
            "Thanks for watching!",
            "Thank you. Thank you.",
            "Thanks for watching! Thank you.",
        ]:
            self.assertEqual(fv.clean_heard(heard), "", heard)

    def test_real_words_beside_a_hallucination_stay(self):
        self.assertIn("Pause the music", fv.clean_heard("Thank you. Pause the music."))

    def test_fillers_and_numbers(self):
        self.assertEqual(fv.clean_heard("Um, uh, open firefox"), "Open firefox")
        self.assertEqual(fv.clean_heard("volume forty five"), "Volume 45")
        self.assertEqual(
            fv.clean_heard("set brightness to a hundred percent"),
            "Set brightness to 100 percent",
        )
        self.assertEqual(
            fv.clean_heard("remind me in five minutes"), "Remind me in 5 minutes"
        )
        self.assertEqual(fv.clean_heard("open one note"), "Open one note")
        self.assertEqual(fv.clean_heard("volume seven"), "Volume 7")


class SplitTarget(unittest.TestCase):
    def test_wake_names(self):
        self.assertEqual(
            fv.split_target("Hey Claude, what's left on Eighty Six?", WAKE),
            ("claude", "what's left on Eighty Six?"),
        )
        self.assertEqual(
            fv.split_target("Cloud. Check the build", WAKE),
            ("claude", "Check the build"),
        )
        self.assertEqual(fv.split_target("Jan: volume 40", WAKE), ("jan", "volume 40"))
        self.assertEqual(
            fv.split_target("a chan open files", WAKE), ("jan", "open files")
        )
        self.assertEqual(fv.split_target("Tetsu", WAKE), ("claude", ""))

    def test_no_wake_name(self):
        self.assertEqual(
            fv.split_target("January plans please", WAKE), ("", "January plans please")
        )
        self.assertEqual(fv.split_target("open firefox", WAKE), ("", "open firefox"))
        self.assertEqual(
            fv.split_target("Clouds are nice", WAKE), ("", "Clouds are nice")
        )

    def test_registry_wake_map_loads(self):
        reg = fv.load_registry()
        self.assertIn("claude", reg["wake"])
        self.assertEqual(fv.split_target("Clawed, hi")[0], "claude")
        for row in reg["models"]:
            self.assertIn(row["kind"], ("stt", "tts"))
            for rel in row["files"].values():
                self.assertFalse(Path(rel).is_absolute(), rel)


class Controls(unittest.TestCase):
    def test_controls(self):
        self.assertEqual(fv.is_control("Stop."), "stop")
        self.assertEqual(fv.is_control("okay stop"), "stop")
        self.assertEqual(fv.is_control("Never mind"), "cancel")
        self.assertEqual(fv.is_control("Say that again?"), "repeat")
        self.assertIsNone(fv.is_control("stop the music"))
        self.assertIsNone(fv.is_control("open firefox"))


class _Fake(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, format, *args):
        pass

    def _reply(self, code: int, body: dict):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.seen.append(("GET", self.path, self.headers.get("X-Forge")))
        self._reply(200, {"state": "idle", "version": 1})

    def do_POST(self):
        size = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(size)
        self.seen.append(("POST", self.path, self.headers.get("X-Forge"), body))
        if self.headers.get("X-Forge") != "1":
            return self._reply(403, {"error": "no header"})
        if self.path.startswith("/api/stt"):
            return self._reply(200, {"text": "open firefox", "model": "x", "ms": 5})
        asked = json.loads(body or b"{}") if self.path in _SPEECH else {}
        if asked.get("text") == "fail":
            return self._reply(503, {"detail": "Breeze is not downloaded"})
        busy = asked.get("voice") == "busy"  # Jan busy: the fast voice speaks
        said = (
            ("kokoro-v1", "af_heart") if busy else ("breeze-tts-2", asked.get("voice"))
        )
        if self.path == "/api/say":
            fell = "Jan is busy" if busy else None
            return self._reply(
                200, {"model": said[0], "voice": said[1], "fell_back": fell}
            )
        if self.path == "/api/tts":
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"\0\0" * 16000)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("X-Voice-Model", said[0])
            self.send_header("X-Voice-Voice", str(said[1]))
            self.send_header("X-Voice-Seconds", "1.0")
            if busy:
                self.send_header("X-Voice-Fell-Back", "Jan is busy")
            self.end_headers()
            return self.wfile.write(buf.getvalue())
        self._reply(200, {"ok": True, "state": "listening"})


_SPEECH = ("/api/say", "/api/tts")


class Client(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_calls_carry_the_header(self):
        _Fake.seen.clear()
        with mock.patch.dict("os.environ", {"FORGE_VOICE_URL": self.url}):
            self.assertEqual(fv.status(), {"state": "idle", "version": 1})
            self.assertTrue(fv.say("hello", app="claude"))
            self.assertEqual(fv.ptt("tap"), {"ok": True, "state": "listening"})
            self.assertEqual(fv.transcribe(b"RIFF....", app="acchan"), "open firefox")
            self.assertTrue(fv.ensure_running(timeout=1))
        paths = [s[1] for s in _Fake.seen]
        self.assertIn("/api/ptt/tap?target=auto", paths)
        self.assertIn("/api/stt?app=acchan", paths)
        self.assertTrue(all(s[2] == "1" for s in _Fake.seen))
        said = next(s for s in _Fake.seen if s[1] == "/api/say")
        self.assertEqual(json.loads(said[3]), {"text": "hello", "app": "claude"})

    def test_down_service_is_none_not_a_crash(self):
        with mock.patch.dict("os.environ", {"FORGE_VOICE_URL": "http://127.0.0.1:9"}):
            self.assertIsNone(fv.status())
            self.assertFalse(fv.say("x"))
            self.assertIsNone(fv.ptt("tap"))

    def test_say_report_and_clip_say_what_spoke(self):
        with mock.patch.dict("os.environ", {"FORGE_VOICE_URL": self.url}):
            r = fv.say_report("hi", voice="busy")
            self.assertEqual((r["ok"], r["model"]), (True, "kokoro-v1"))
            self.assertEqual(r["fell_back"], "Jan is busy")
            with tempfile.TemporaryDirectory() as t:
                out = Path(t) / "x.wav"
                r = fv.clip("hello", out, model="breeze-tts-2", voice="86-lena-en")
                self.assertTrue(r["ok"])
                self.assertEqual(out.read_bytes()[:4], b"RIFF")
                got = (r["model"], r["voice"], r["seconds"], r["fell_back"])
                self.assertEqual(got, ("breeze-tts-2", "86-lena-en", 1.0, None))
                self.assertIn("already exists", fv.clip("again", out)["error"])
                self.assertTrue(fv.clip("again", out, overwrite=True)["ok"])
                if shutil.which("ffmpeg"):
                    ogg = Path(t) / "note.ogg"
                    self.assertTrue(fv.clip("hello", ogg)["ok"])
                    self.assertEqual(ogg.read_bytes()[:4], b"OggS")
                r = fv.clip("fail", Path(t) / "y.wav")
                self.assertEqual(r, {"ok": False, "error": "Breeze is not downloaded"})
                self.assertFalse((Path(t) / "y.wav").exists())
        with mock.patch.dict("os.environ", {"FORGE_VOICE_URL": "http://127.0.0.1:9"}):
            self.assertIn("did not answer", fv.say_report("x")["error"])

    def test_cli_say_and_clip_print_what_spoke(self):
        env = {"FORGE_VOICE_URL": self.url}
        with mock.patch.dict("os.environ", env), mock.patch.object(
            fv, "ensure_running", return_value=True
        ), tempfile.TemporaryDirectory() as t:
            with contextlib.redirect_stdout(io.StringIO()) as o:
                self.assertEqual(fv.main(["say", "--voice", "busy", "hi"]), 0)
                out = str(Path(t) / "a.wav")
                self.assertEqual(fv.main(["clip", "hi", "--out", out]), 0)
            self.assertIn(
                "kokoro-v1 (af_heart) speaks it instead: Jan is busy", o.getvalue()
            )
            self.assertIn("saved", o.getvalue())
            with contextlib.redirect_stderr(io.StringIO()) as e:
                self.assertEqual(fv.main(["clip", "hi", "--out", out]), 1)
            self.assertIn("already exists", e.getvalue())

    def test_clip_keeps_only_the_asked_voice_and_say_tells(self):
        env = {"FORGE_VOICE_URL": self.url}
        with mock.patch.dict("os.environ", env), mock.patch.object(
            fv, "ensure_running", return_value=True
        ), tempfile.TemporaryDirectory() as t:
            out = Path(t) / "lena.wav"
            r = fv.clip("hi", out, voice="busy")  # Jan busy: the fast voice spoke
            self.assertIn("speaks it instead: Jan is busy", r["error"])
            self.assertFalse(out.exists())
            r = fv.clip("hi", out, model="kokoro-v1")  # another model answered
            self.assertIn("breeze-tts-2 (None) spoke it, not kokoro-v1", r["error"])
            self.assertFalse(out.exists())
            self.assertTrue(fv.clip("hi", out, voice="busy", any_voice=True)["ok"])
            with contextlib.redirect_stdout(io.StringIO()) as o:
                self.assertEqual(fv.main(["say", "--model", "kokoro-v1", "hi"]), 0)
            self.assertIn("spoke it, not kokoro-v1", o.getvalue())
            b = str(Path(t) / "b.wav")
            with contextlib.redirect_stderr(io.StringIO()) as e:
                self.assertEqual(
                    fv.main(["clip", "hi", "--voice", "busy", "--out", b]), 1
                )
            self.assertIn("nothing saved", e.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                args = ["clip", "hi", "--voice", "busy", "--any-voice", "--out", b]
                self.assertEqual(fv.main(args), 0)


class Release(unittest.TestCase):
    def test_up_that_overtakes_its_down_is_sent_again(self):
        seq = [{"state": "idle"}, {"state": "listening"}]
        with mock.patch.object(fv, "ptt", side_effect=seq) as sent, mock.patch.object(
            fv.time, "sleep"
        ) as nap:
            self.assertEqual(fv.ptt_up("jan"), {"state": "listening"})
        self.assertEqual(sent.call_args_list, [mock.call("up", "jan")] * 2)
        nap.assert_called_once_with(0.3)

    def test_up_that_lands_is_sent_once(self):
        busy = {"state": "transcribing"}
        with mock.patch.object(fv, "ptt", return_value=busy) as sent, mock.patch.object(
            fv.time, "sleep"
        ) as nap:
            self.assertEqual(fv.ptt_up(), busy)
        sent.assert_called_once_with("up", "auto")
        nap.assert_not_called()

    def test_cli_up_goes_through_the_retry(self):
        with mock.patch.object(
            fv, "ptt_up", return_value={"state": "listening"}
        ) as up, mock.patch("builtins.print"):
            self.assertEqual(fv.main(["up", "--target", "jan"]), 0)
        up.assert_called_once_with("jan")


class Hotkeys(unittest.TestCase):
    def test_hyprland_block_is_idempotent_and_backed_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            hypr = Path(tmp)
            (hypr / "custom").mkdir()
            binds = hypr / "custom" / "keybinds.lua"
            binds.write_text('hl.bind("SUPER + ALT + P", hl.dsp.exec_cmd("x"))\n')
            self.assertIn("written", fv.install_hyprland(config_dir=hypr))
            text = binds.read_text()
            self.assertEqual(text.count(fv.HYPR_BEGIN), 1)
            self.assertIn("release = true", text)
            self.assertIn("SUPER + ALT + P", text)
            self.assertEqual(len(list((hypr / "custom").glob("keybinds.lua.bak-*"))), 1)
            self.assertIn("already set", fv.install_hyprland(config_dir=hypr))
            self.assertEqual(binds.read_text(), text)

    def test_hyprland_conflict_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            hypr = Path(tmp)
            (hypr / "custom").mkdir()
            (hypr / "custom" / "keybinds.lua").write_text("-- empty\n")
            (hypr / "variables.lua").write_text('kbX = "SUPER + ALT + Z",\n')
            self.assertIn("already used", fv.install_hyprland(config_dir=hypr))
            self.assertEqual(
                (hypr / "custom" / "keybinds.lua").read_text(), "-- empty\n"
            )

    def test_gnome_conflict_dry_run_and_set(self):
        store = {"list": "['/a/']", "/a/": "'<Super>v'"}
        calls = []

        def run(*args):
            calls.append(args)
            if args[0] == "get" and args[2] == "custom-keybindings":
                return store["list"]
            if args[0] == "get" and args[2] == "binding":
                return store.get(args[1].split(":", 1)[1], "''")
            if args[0] == "list-recursively":
                return ""
            return ""

        self.assertIn("would bind", fv.install_gnome(dry_run=True, run=run))
        self.assertFalse(any(c[0] == "set" for c in calls))
        with mock.patch.object(Path, "home", return_value=Path(tempfile.mkdtemp())):
            self.assertIn("now runs", fv.install_gnome(run=run))
        sets = [c for c in calls if c[0] == "set"]
        self.assertIn(fv.GNOME_PATH, sets[0][3])
        self.assertEqual(sets[-1][2:], ("binding", "<Super>z"))
        store["/a/"] = "'<Super>z'"
        self.assertIn("already used", fv.install_gnome(run=run))


if __name__ == "__main__":
    unittest.main()
