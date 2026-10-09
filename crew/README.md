# The crew board

One file per worker, rewritten by that worker every few minutes while it runs.
Nothing merges into a single file, because several agents writing one file at
once lose each other's edits — this is the same "one file per thing, discovered
by scanning" rule the rest of Forge uses.

    python3 ~/Forge/crew/summary.py          # what everyone is doing, now
    python3 ~/Forge/crew/summary.py --watch  # the same, refreshed

A worker writes `~/Forge/crew/<name>.json`:

    {"agent": "...", "model": "...", "task": "one line",
     "status": "working|done|blocked", "doing": "what right now",
     "done": ["finished things"], "files": ["paths owned"],
     "updated": <unix seconds>}
