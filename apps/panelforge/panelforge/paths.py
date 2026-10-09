"""Where PanelForge keeps its data. Everything lives under ~/PanelForgeData.

Layout (see CONTRACTS.md for the files inside each chapter):

    ~/PanelForgeData/
      series/<series>/series.json
      series/<series>/cast.json
      series/<series>/assets/{cast,extras,backgrounds,props,sfx}/
      series/<series>/chapters/<chapter>/...
      models/            downloaded AI models, 15 GB budget (models.py)
      library/           sound effects and music the user adds
      jobs/              one JSON status file per background job
"""

import os
import re
from pathlib import Path

DATA_ROOT = Path(os.environ.get("PANELFORGE_DATA") or Path.home() / "PanelForgeData")
SERIES_ROOT = DATA_ROOT / "series"
MODELS_ROOT = DATA_ROOT / "models"
LIBRARY_ROOT = DATA_ROOT / "library"
JOBS_ROOT = DATA_ROOT / "jobs"

APP_ROOT = Path(__file__).resolve().parent.parent
TESTDATA = APP_ROOT / "testdata"

_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """Lower-case, dash-separated, safe as a folder name. Never empty."""
    s = _SLUG.sub("-", text.lower()).strip("-")
    return s[:80] or "untitled"


def chapter_slug(number: float) -> str:
    """Chapter folder names sort correctly: 1 -> '0001', 12.5 -> '0012.5'."""
    whole = int(number)
    rest = number - whole
    return f"{whole:04d}" + (f"{rest:.3f}".lstrip("0").rstrip("0") if rest else "")


class BadId(ValueError):
    """A series or chapter id that cannot name one folder (web_app.py: 404)."""


def _part(name: str) -> str:
    """`name` if it is one ordinary folder name, else BadId. Ids arrive from
    URLs, so '..' must not reach the data root and 3000 characters must not
    reach the disk."""
    if (
        name in ("", ".", "..")
        or "/" in name
        or "\\" in name
        or "\0" in name
        or len(name.encode("utf-8", "surrogatepass")) > 255
    ):
        raise BadId(f"no such item: {name[:40]!r}")
    return name


def series_dir(series: str) -> Path:
    return SERIES_ROOT / _part(series)


def chapter_dir(series: str, chapter: str) -> Path:
    return SERIES_ROOT / _part(series) / "chapters" / _part(chapter)


def ensure_roots() -> None:
    for d in (SERIES_ROOT, MODELS_ROOT, LIBRARY_ROOT, JOBS_ROOT):
        d.mkdir(parents=True, exist_ok=True)
