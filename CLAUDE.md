# Forge

One desktop window hosting many self-contained tools (`ls apps/` is the current
list; there were nineteen on 2026-09-16). `forge.py` is a thin orchestrator
that owns no application logic:
each app under `apps/` keeps its own FastAPI backend, its own `.venv`, and its
own port, exactly as it runs standalone. The launcher starts them, shows a
single GTK/WebKit window with a sidebar shell, and shuts the backends down when
the window closes.

Codec Lab and Codec Player live in the separate `~/anime-codec-lab` git repo;
`apps/codec-lab/` and `apps/codec-player/` are stubs whose `forge_app.json` has
a `root` field pointing there. Several apps talk to Jan (Arcade, Dossier,
Foresight, NovelForge); Jan is shared, so never restart it without checking.
Forge is the only app-launcher entry; the other `.desktop` files are
`NoDisplay=true`. The `forge-session` skill is the start-and-finish routine for
work here.

## Read these first, in this order

Do not re-derive the architecture — it is already written down:

1. The module docstring at the top of `forge.py` — layout, startup model, and
   how app discovery works.
2. `README.md` — the `forge_app.json` manifest fields and the frontend
   contract.
3. `PROGRESS.json` — **the live source of truth for status**: what is done,
   what is verified versus merely reasoned about, what is pending, and
   suggested next steps. It is kept current; trust it over any status written
   elsewhere, including this file, which deliberately records none.

Each app additionally carries its own `README.md` and `WIP.md`.

Only this file and `README.md` live at the root; do not add other `.md`
files there. Hub-wide docs go in `docs/` (`IDEAS.md`, `DESKTOP-REACH.md`),
hub-wide plans in `docs/plans/`, an app's plans in `apps/<app>/docs/`,
session briefs in `sessions/`, and frozen records in `docs/archive/`.

## The rule that matters most

Apps are **discovered, not declared**. Adding or changing an app means dropping
a directory into `apps/` with a `forge_app.json` beside a `.venv` and a FastAPI
app — nothing in `forge.py` should need editing. If a change would require
hardcoding an app name in the orchestrator, that is a sign the manifest needs a
new field instead.

Shared frontend code lives in `shared/` (`forge.css`, `forge.js`) and is served
by every app backend. Put common styling and behavior there rather than copying
it into each app's `static/`.

## Notes

- `~/Forge` is a git repo (initialised 2026-09-26, no commits yet, no remote).
  `.gitignore` keeps out caches, logs, `outputs/`, `backups/`, downloaded
  models/binaries and app runtime state; run `git status` before and after
  work. `backups/` still holds pre-edit copies (ignored by git); keep making
  one before a substantial edit until there is commit history to fall back on.
- Backend logs land in `outputs/<app>.log` — read them before guessing at a
  startup failure.
- More than one Claude session often works in this tree at once. Confirm a file
  still exists and has not moved before editing it.
