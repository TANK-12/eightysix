"""Shared fakes for the world tests: a fake sd binary and fake parts."""

import sys
from pathlib import Path

FAKE_SD = r"""#!{python}
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
if "--help" in args:
    print("{help}")
    sys.exit(0)
log = Path(os.environ.get("FAKE_SD_LOG", "/dev/null"))
if str(log) != "/dev/null":
    with open(log, "a") as f:
        f.write(json.dumps(args) + "\n")
if os.environ.get("FAKE_SD_SLEEP"):
    time.sleep(float(os.environ["FAKE_SD_SLEEP"]))
if os.environ.get("FAKE_SD_FAIL"):
    sys.exit(3)
from PIL import Image
out = args[args.index("-o") + 1]
n = int(args[args.index("--video-frames") + 1])
w = int(args[args.index("-W") + 1]); h = int(args[args.index("-H") + 1])
for i in range(n):
    Image.new("RGB", (w, h), (i * 10 % 255, 80, 160)).save(out % i)
"""

HELP_WITH_VACE = "  --control-video <string>  path to control video frames"
HELP_OLD = "  --steps <int>  number of sample steps"


def make_fake_sd(folder, help_text=HELP_WITH_VACE):
    path = Path(folder) / "sd"
    path.write_text(
        FAKE_SD.replace("{python}", sys.executable).replace("{help}", help_text)
    )
    path.chmod(0o755)
    return path


def make_parts(folder, entry):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for p in entry["parts"]:
        (folder / p["filename"]).write_bytes(b"x")
    return folder
