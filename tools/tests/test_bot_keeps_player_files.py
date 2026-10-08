"""A bot run must never save over the player's own settings (Relay 110, 2026-10-08).

Bot runs start from the player's settings.cfg, then change the graphics preset (--preset) and run
"setting" steps (squad size 0, move hints off). Picking a preset saves every setting, so each run used
to write its own values into the player's file: his preset flipped between Low and Ultra with every
check run and his squad went to 0 wingmen. This plays a tiny bot script headless in a sandboxed user
folder (XDG_DATA_HOME) and checks the player's file is byte for byte the same afterwards.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GODOT = os.environ.get("GODOT", "godot")
PLAYER_SETTINGS = "[gameplay]\n\nsquad_size=3.0\n"
BOT_SCRIPT = """{"name": "keeps_player_files", "steps": [
  {"at": 0.0, "setting": "gameplay.squad_size", "value": 0.0},
  {"at": 1.0, "quit": true}
]}"""


@unittest.skipUnless(shutil.which(GODOT), "needs the godot binary")
class BotKeepsPlayerFiles(unittest.TestCase):
    def test_a_bot_run_saves_its_settings_beside_the_players_not_over_them(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="eightysix-bot-") as tmp:
            user = Path(tmp) / "data" / "godot" / "app_userdata" / "Eighty Six"
            user.mkdir(parents=True)
            (user / "settings.cfg").write_text(PLAYER_SETTINGS)
            script = Path(tmp) / "keeps_player_files.json"
            script.write_text(BOT_SCRIPT)
            out = Path(tmp) / "out"
            run = subprocess.run(
                [
                    GODOT,
                    "--headless",
                    "--path",
                    str(ROOT),
                    "--",
                    f"--bot={script}",
                    f"--out={out}",
                    "--preset=low",
                ],
                env={**os.environ, "XDG_DATA_HOME": str(Path(tmp) / "data")},
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertTrue(
                (out / "report.json").exists(), "the bot ran:\n" + run.stderr[-2000:]
            )
            self.assertEqual(
                (user / "settings.cfg").read_text(),
                PLAYER_SETTINGS,
                "the player's settings.cfg is untouched",
            )
            bot_file = user / "bot_settings.cfg"
            self.assertTrue(bot_file.exists(), "the run's own save went somewhere")
            saved = bot_file.read_text()
            self.assertIn('preset="low"', saved)
            self.assertIn("squad_size=0.0", saved)


if __name__ == "__main__":
    unittest.main()
