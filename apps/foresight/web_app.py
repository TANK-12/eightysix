"""Foresight - the analysis and planning tab in Forge.

Thin over the registries, exactly like Dossier's backend: it names no
individual signal source, analyser or tier. Adding a source is one file in
`signals/`; the API and the frontend pick it up with no edit here.

Run standalone with:
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8438
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import dossier_link
import llm
import plans
import store
import sweep
import tiers as tiers_mod
from analysis import registry as analysers
from signals import registry as signal_sources
from world import World

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))

app = FastAPI(title="Foresight")

# One sweep at a time. The fetcher paces itself per domain, but two sweeps
# would still double the load on a laptop that is also being used.
_sweep_lock = threading.Lock()
_sweep_state: dict = {"running": False, "done": 0, "total": 0, "log": [], "last": ""}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log(message: str) -> None:
    _sweep_state["log"] = (_sweep_state["log"] + [f"{now_iso()[11:19]} {message}"])[
        -200:
    ]
    print(f"[foresight] {message}", flush=True)


# --- status -----------------------------------------------------------------


@app.get("/api/status")
def status():
    root = store.data_root()
    free = store.free_bytes()
    jan = llm.status()
    return {
        "backend": True,
        "storage": {
            "path": str(root.path),
            "on_usb": root.on_usb,
            "detail": root.detail,
            "free_gb": round(free / 1e9, 1) if free > 0 else -1,
        },
        "dossier": dossier_link.status(),
        "jan": jan,
        "tiers": tiers_mod.describe(),
        "sources": signal_sources.describe(),
        "analysers": analysers.describe(),
        "sweep": {k: v for k, v in _sweep_state.items() if k != "log"},
    }


# --- what is known ----------------------------------------------------------


@app.exception_handler(store.BadSlug)
def _bad_slug(_request, _exc):
    """A slug that is not a folder name names no subject."""
    return JSONResponse({"detail": "No subject stored under that name"}, 404)


def _number(payload: dict, key: str, default: int, low: int, high: int) -> int:
    """A whole number from a request body, clamped. A wrong type is the
    caller's mistake and gets a 400 saying so, not a server error."""
    raw = payload.get(key, default)
    try:
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise TypeError(key)
        value = int(float(raw)) if isinstance(raw, str) else int(raw)
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(400, f"'{key}' must be a number")
    return max(low, min(high, value))


def _sweep_subjects(raw) -> list[dict]:
    """The subjects a sweep was asked for, each with a usable slug and name."""
    if not isinstance(raw, list):
        raise HTTPException(400, "'subjects' must be a list of subjects")
    out = []
    for row in raw:
        if not isinstance(row, dict) or not isinstance(row.get("slug"), str):
            raise HTTPException(400, "Every subject needs a slug")
        try:
            store.check_slug(row["slug"])
        except store.BadSlug:
            raise HTTPException(400, f"'{row['slug'][:80]}' is not a subject slug")
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            name = row["slug"]
        out.append({**row, "name": name})
    return out


@app.get("/api/watchlist")
def watchlist(limit: int = 40):
    return {"subjects": sweep.watchlist(limit=max(0, min(limit, 2000)))}


@app.get("/api/findings")
def findings(limit: int = 100):
    limit = max(0, min(limit, 5000))
    return {"findings": sweep.all_findings(limit=limit), "at": now_iso()}


@app.get("/api/subject/{slug}")
def subject(slug: str):
    store.check_slug(slug)
    rows = {r["slug"]: r for r in dossier_link.library()}
    name = (rows.get(slug) or {}).get("name") or slug
    world = World()
    summary = world.subject_summary(slug, name)
    return {
        "slug": slug,
        "name": name,
        "summary": summary["text"],
        "series": {
            source: store.read_series(slug, source)
            for source in store.sources_for(slug)
        },
        "findings": sweep.findings_for(slug, name),
    }


@app.get("/api/coverage")
def coverage():
    return World().coverage()


# --- gathering --------------------------------------------------------------


def _run_sweep(
    subjects: list[dict], days: int, only: tuple[str, ...], history: bool = False
) -> None:
    fetcher = sweep.make_fetcher()
    _sweep_state.update(running=True, done=0, total=len(subjects), log=[])
    _log(
        f"sweep starting over {len(subjects)} subjects"
        + (" - five years each, keeping every stored reading" if history else "")
    )
    try:
        for row in subjects:
            stored = dossier_link.subject(row["slug"])
            ctx = sweep.Context(fetcher=fetcher, days=days, stored=stored, log=_log)
            result = sweep.sweep_subject(
                row["slug"], row["name"], ctx, only, history=history
            )
            added = sum(s.get("added", 0) for s in result["sources"].values())
            if result["errors"]:
                for source, error in result["errors"].items():
                    _log(f"{row['name']}: {source} failed - {error}")
            _log(f"{row['name']}: +{added} readings")
            if history:
                # The point of the history is what it teaches the rules tier.
                try:
                    learned = plans.learn(row["slug"])
                    _log(f"{row['name']}: learned from {len(learned['series'])} series")
                except Exception as e:
                    _log(f"{row['name']}: learning failed - {type(e).__name__}: {e}")
            _sweep_state["done"] += 1
    except Exception as e:
        _log(f"sweep stopped: {type(e).__name__}: {e}")
    finally:
        _sweep_state.update(running=False, last=now_iso())
        _log("sweep finished")


@app.post("/api/sweep")
def start_sweep(payload: dict | None = None):
    """Gather signals for the most consequential subjects, in the background.

    Returns immediately: a sweep over forty subjects is minutes of network, and
    the user asked for long jobs to be startable and then left alone.
    """
    payload = payload or {}
    if not isinstance(payload, dict):
        raise HTTPException(400, "A sweep request is a JSON object")
    # Checked before anything is marked running, so a bad request starts nothing.
    limit = _number(payload, "limit", 25, 1, 400)
    days = _number(payload, "days", 60, 7, 365)
    raw_sources = payload.get("sources") or []
    if not isinstance(raw_sources, list) or not all(
        isinstance(s, str) for s in raw_sources
    ):
        raise HTTPException(400, "'sources' must be a list of source names")
    asked = _sweep_subjects(payload.get("subjects") or [])
    if _sweep_state["running"]:
        raise HTTPException(409, "A sweep is already running")
    if not _sweep_lock.acquire(blocking=False):
        raise HTTPException(409, "A sweep is already running")
    try:
        only = tuple(raw_sources)
        # `history`: re-read five years for every subject already swept, so
        # the new history and news counts reach what was gathered before them.
        history = bool(payload.get("history", False))
        subjects = (
            asked
            or (sweep.held_subjects() if history else [])
            or sweep.watchlist(limit=limit)
        )
        if not subjects:
            raise HTTPException(
                400,
                "Nothing to sweep - Dossier's library is empty or the AN3 drive "
                "is not plugged in.",
            )
        # Marked running here, not only inside the thread: otherwise a status
        # read straight after this returns can still say idle, and a page that
        # polls on that answer stops watching a sweep that is under way.
        _sweep_state.update(running=True, done=0, total=len(subjects), log=[])
        thread = threading.Thread(
            target=_run_sweep,
            args=(subjects, days, only, history),
            daemon=True,
            name="sweep",
        )
        thread.start()
    finally:
        _sweep_lock.release()
    return {"started": True, "subjects": len(subjects)}


@app.get("/api/sweep")
def sweep_status():
    return dict(_sweep_state)


# --- asking -----------------------------------------------------------------


@app.post("/api/ask")
def ask(payload: dict):
    """Answer a question at a chosen tier, including the tier that uses no model."""
    question = str((payload or {}).get("question", "")).strip()
    if not question:
        raise HTTPException(400, "Ask something")
    tier = str((payload or {}).get("tier", tiers_mod.RULES))
    if tier not in tiers_mod.ALL_TIERS:
        raise HTTPException(400, f"No tier called '{tier}'")
    prefer_rules = bool((payload or {}).get("prefer_rules", True))
    world = World()
    # A model tier gets the stored material to reason from; the rules tier
    # reads the same world directly and needs no text pack.
    context = "" if tier == tiers_mod.RULES else world.context_for(question)
    answer = tiers_mod.answer(
        question, tier=tier, world=world, prefer_rules=prefer_rules, context=context
    )
    return answer.as_dict()


@app.post("/api/research")
def request_research(payload: dict):
    """Ask Dossier to research something. Reversible, so it needs no approval."""
    name = str((payload or {}).get("name", "")).strip()
    if not name:
        raise HTTPException(400, "Name something to research")
    return dossier_link.request_research(
        name,
        str((payload or {}).get("entity_type", "person")),
        str((payload or {}).get("phase", "quick")),
    )


# --- plans and scenarios ----------------------------------------------------
#
# The half that makes this a foresight app rather than a dashboard. A scenario
# is branches of the future, each carrying dated, falsifiable indicators, and
# the ledger marks them by arithmetic when their dates pass. See plans.py.


@app.get("/api/plans")
def list_plans():
    return {
        "scenarios": [s.as_dict() for s in plans.all_scenarios()],
        "record": plans.record(),
    }


@app.post("/api/plans")
def make_plan(payload: dict):
    """Write a scenario about one subject, at a chosen tier.

    The rules tier needs no model and works with Jan switched off; it carries
    every stored series forward and states the result as a claim that can be
    marked. A model tier writes richer branches and every indicator it proposes
    is forced through the same shape.
    """
    slug = str((payload or {}).get("slug", "")).strip()
    if not slug:
        raise HTTPException(400, "Name a subject to plan about")
    store.check_slug(slug)
    tier = str((payload or {}).get("tier", tiers_mod.RULES))
    if tier not in tiers_mod.ALL_TIERS:
        raise HTTPException(400, f"No tier called '{tier}'")

    rows = {r["slug"]: r for r in dossier_link.library()}
    subject = (rows.get(slug) or {}).get("name") or slug
    world = World()

    if tier == tiers_mod.RULES:
        scenario = plans.from_rules(slug, subject)
    else:

        def ask(prompt: str, at_tier: str):
            # prefer_rules off: this is a request for the model's judgement,
            # and a solver answering it instead would silently produce no
            # scenario at all.
            return tiers_mod.answer(
                prompt, tier=at_tier, world=world, prefer_rules=False
            )

        scenario = plans.from_model(slug, subject, tier, world, ask)

    if not scenario.branches:
        raise HTTPException(
            422,
            "Nothing scoreable came back. The rules tier needs stored series to "
            "project - sweep this subject first - and a model tier's branches "
            "are discarded unless they name a series this app actually holds.",
        )
    plans.save(plans.score(scenario))
    return scenario.as_dict()


@app.post("/api/plans/{scenario_id}/score")
def score_plan(scenario_id: str):
    """Mark every indicator whose date has passed. Arithmetic only."""
    scenario = plans.load(scenario_id)
    if scenario is None:
        raise HTTPException(404, "No scenario with that id")
    plans.save(plans.score(scenario))
    return scenario.as_dict()


@app.post("/api/plans/score")
def score_all_plans():
    """Re-mark the whole ledger — cheap, and the only way old forecasts settle."""
    for scenario in plans.all_scenarios():
        plans.save(plans.score(scenario))
    return plans.record()


@app.post("/api/plans/learn")
def learn_from_history(payload: dict | None = None):
    """Backtest stored series against their own past. Arithmetic only.

    Names one subject, or every subject with signals when none is given.
    """
    slug = str((payload or {}).get("slug", "")).strip()
    slugs = [store.check_slug(slug)] if slug else store.subjects_with_signals()
    for one in slugs:
        plans.learn(one)
    return {"learned": len(slugs), "backtest": plans.lessons_summary()}


@app.delete("/api/plans/{scenario_id}")
def drop_plan(scenario_id: str):
    if not plans.delete(scenario_id):
        raise HTTPException(404, "No scenario with that id")
    return {"deleted": scenario_id}


# --- static -----------------------------------------------------------------

if SHARED_DIR.is_dir():
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")


@app.get("/")
def index():
    target = STATIC_DIR / "index.html"
    if not target.is_file():
        return JSONResponse({"error": "static/index.html is missing"}, status_code=500)
    return FileResponse(target)


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
