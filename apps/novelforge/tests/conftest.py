"""Shared test helpers: a temporary NovelMakerData, and a fake Jan client that
answers from a script, so nothing here ever talks to a real model."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novelforge import project as projectmod  # noqa: E402
from novelforge.janclient import Completion  # noqa: E402


@pytest.fixture
def data_dirs(tmp_path, monkeypatch):
    """Point projects, series and the trash at a temp folder."""
    dirs = {
        "projects": tmp_path / "projects",
        "series": tmp_path / "series",
        "trash": tmp_path / ".trash",
    }
    for d in dirs.values():
        d.mkdir()
    monkeypatch.setattr(projectmod, "PROJECTS_DIR", str(dirs["projects"]))
    monkeypatch.setattr(projectmod, "SERIES_DIR", str(dirs["series"]))
    monkeypatch.setattr(projectmod, "TRASH_DIR", str(dirs["trash"]))
    monkeypatch.setenv("FORGE_JAN_SETTINGS_DIR", str(tmp_path / "jan"))
    return dirs


SYLLABLES = (
    "ka ro mi te su na ha lo pe ri ga do yu ben sil tor mak ven zu qua fen "
    "lim dor sap wen kel bra tis mun gol har vek pim jor"
).split()


def word(rng):
    return "".join(rng.sample(SYLLABLES, rng.choice((2, 3))))


def prose(names=("Kang Jin-Woo", "Soo-Ah"), sentences=45, seed=1):
    """Varied, non-looping prose with dialogue, for the quality checks. The
    words are nonsense on purpose: repetition detectors only see variety."""
    rng = random.Random(seed)
    out = []
    for i in range(sentences):
        who = names[i % len(names)]
        body = " ".join(word(rng) for _ in range(rng.randint(5, 11)))
        if i % 3 == 0:
            out.append(f'"{body.capitalize()}," {who} said.')
        else:
            out.append(f"{who} {body}.")
    return " ".join(out)


def outline_line(c, hero="Jin-Woo", other="Soo-Ah"):
    """A distinct, well-formed outline line for chapter c."""
    rng = random.Random(1000 + c)
    w = lambda n: " ".join(word(rng) for _ in range(n))  # noqa: E731
    return f"{w(2).title()} | {hero} {w(5)} while {other} {w(4)} | " f"{w(6)} | {w(5)}"


class FakeClient:
    """Answers complete() from `handler(system, user) -> str`, recording every
    call so a test can see what was asked."""

    base_url = "http://127.0.0.1:9"

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict] = []

    def complete(
        self,
        model,
        system,
        user,
        max_tokens=1024,
        temperature=0.7,
        kill=None,
        on_delta=None,
        extra=None,
        **_,
    ):
        self.calls.append(
            {"model": model, "system": system, "user": user, "extra": extra}
        )
        text = self.handler(system, user)
        if on_delta and text:
            on_delta(text)
        return Completion(text, "stop", len(text) // 4, 0.01, False)

    def list_models(self):
        return []

    def ping(self):
        return False


class FakeStyle:
    def active_style_notes(self):
        return ""

    def retrieve(self, goal, top_k=2):
        return []


def make_engine(p, handler, profile_label="small", settings=None, planner=None):
    from novelforge.catalog import profile_for
    from novelforge.config import DEFAULTS
    from novelforge.engine import NovelEngine

    ids = {"tiny": "t-0.8B", "small": "s-2B", "medium": "m-9B", "large": "l-27B"}
    profile = profile_for(ids[profile_label], 16000)
    s = dict(DEFAULTS)
    s.update({"ram_guard": False, "reconcile_every": 0})
    s.update(settings or {})
    logs: list[str] = []
    client = FakeClient(handler)
    eng = NovelEngine(
        p,
        client,
        ids[profile_label],
        FakeStyle(),
        profile,
        s,
        log=logs.append,
        planner=planner,
    )
    return eng, client, logs
