# A long research job is running

Started 2026-09-10. **847 subjects queued**, roughly 10–11 hours of work.
It runs inside the Dossier backend, not inside any Claude session, so closing
Claude does not stop it.

## What it is doing

Quick passes over every head of state, head of government, party holding seats,
live conflict, alliance, sovereign country and large company that Wikidata
knows about and the library does not already hold.

**It uses the CPU only.** A quick pass never loads the 4B model, so the iGPU
stays free for whatever else you are running. Only a *deep dive* uses the iGPU.

## Checking on it

```
curl -s localhost:8437/api/queue | python3 -m json.tool | head -30
```

Or just open Dossier in Forge — the Jobs tab shows progress, the live log and
any failures. The header pill shows `<done>/<total>` while it runs.

## Stopping or pausing it

```
curl -s -X POST localhost:8437/api/queue/pause -d '{}' -H 'Content-Type: application/json'
curl -s -X POST localhost:8437/api/queue/start -d '{}' -H 'Content-Type: application/json'
```

Pausing lets the four in-flight subjects finish and starts nothing new.

## Several queues

Work is organised into named queues and **one is active at a time**. The four
workers only pull from the active one, so a list of companies can sit untouched
while a list of leaders runs.

```
curl -s localhost:8437/api/queues | python3 -m json.tool
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"name":"Companies"}' localhost:8437/api/queues
curl -s -X POST localhost:8437/api/queues/<id>/activate -d '{}' \
  -H 'Content-Type: application/json'
```

Everything under `/api/queue` acts on whichever queue is active, so the commands
above and below have not changed meaning.

## Work already done is not done again

Each queue carries a **redo subjects I already hold** setting, off by default.
Off, a job whose subject is already in the library is marked `skipped` when it
comes up to run rather than researched a second time — checked at the moment the
job starts, not only when it was queued, because a subject can arrive in between.
A deep dive on a subject held only at quick depth still runs, so deepening works.

Turn it on for one queue when the pipeline has learned to collect something the
old dossiers are missing:

```
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"redo":true}' localhost:8437/api/queues/<id>/redo
```

## If the machine restarts

The queue is on disk (`/run/media/ejb/AN3/DossierData/queue.json`) and anything
left mid-flight is put back to `queued`, so nothing is lost. **A pause is
remembered too** — pause it, shut down, come back tomorrow, and it is still
paused with everything intact, waiting for you to press Resume. Nothing starts
working on its own when the app opens.

The file is version 2 (several queues). An older single-list file migrates
automatically on first load and the original is kept beside it as
`queue.json.v1-backup`.

Bring it back with:

```
cd ~/Forge/apps/dossier
FORGE_SHARED_DIR=~/Forge/shared setsid nohup .venv/bin/python -m uvicorn \
  web_app:app --host 127.0.0.1 --port 8437 > ~/Forge/outputs/dossier.log 2>&1 &
curl -s -X POST localhost:8437/api/queue/start -d '{}' -H 'Content-Type: application/json'
```

Or just launch Forge, which starts every app's backend anyway.

## It protects the machine

This laptop has no swap, so running out of memory locks it up rather than
slowing down. llama.cpp's prompt cache cannot be bounded from Jan's settings
(Jan rewrites the file that would carry it on every start), and a model server
was measured growing from 1.4 GB to 7.2 GB over one long run.

So a guard checks free memory every 45 seconds and **pauses the research on its
own** if less than ~2.2 GB is left, resuming once there is 4 GB again. Pausing
lets the in-flight subjects finish and starts nothing new. You will see it in
`~/Forge/outputs/dossier.log`:

```
[dossier] only 2100 MB free - pausing research to keep the machine responsive
[dossier] 4300 MB free again - resuming research
```

If you find it paused and want it going regardless, close something memory-heavy
and it resumes by itself, or force it with the start command above.

## While it runs

The daily and weekly briefs write themselves — a scheduler thread checks every
30 minutes and generates one when due. They land in
`DossierData/briefings/<kind>/<date>.json` and show on the World tab.

## Not finished

The Settings panel (model pickers per tier, and a "reset Jan and apply the
settings Dossier needs" button) is built in `janctl.py` but not yet wired to the
interface. The fullscreen helper is in `shared/forge.js` but not yet used by
Dossier's page. Neither is needed for this job.
