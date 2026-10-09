# Foresight — state of play

## U1 sweep (2026-10-08, Relay task 74)

Group G12, done by Relay task 77. Report: `sessions/2026-10-07-overhaul/reports/u1-G12.md`.

**Critic follow-up (same day):** a failed `/api/status` at load no longer
leaves the page dead (boot retries on a ForgeIdle poll and the sweep poll
always exists); `store.MAX_SLUG = 200` with `/api/plans` and
`/api/plans/learn` checking it (a 200 kB slug was a 500); the job log wraps
long lines; "score plans" cannot be double-sent; `tests/conftest.py` gives
every test a temp data root, so `pytest` no longer touches
`~/AN3-backup/ForesightData` (verified by its mtime). 126 passed; details in the
report's Critic section.

- **Reads the library Dossier actually uses:** `dossier_link` now follows
  Dossier's own Location choice (`~/.config/forge-dossier/location.json`,
  env `DOSSIER_LOCATION_FILE`) before AN3 and `~/DossierData-local`. Since
  the library moved to `~/AN3-backup/DossierData` (2026-09-25) Foresight was
  reading the 2-subject local fallback instead of 2,450 subjects.
- **Its own data follows too:** `store.data_root` uses an existing
  `ForesightData/` beside that chosen library (it is never created there).
  On this laptop that is `~/AN3-backup/ForesightData` (488 signal folders and
  plans) instead of `~/ForesightData-local` (2 signal folders). Assumption:
  the AN3 copy is the real one; the local folder is left untouched.
- **Bad sweep input is a 400 that starts nothing:** `limit`/`days` must be
  numbers, `sources` a list of names (a bare string used to be split into
  letters), `subjects` a list of objects with a valid slug.
- **Path safety:** `store.check_slug` (`BadSlug`, answered as 404) guards
  `series_path`, `sources_for` and `/api/subject/{slug}`; list limits clamped.
- **Rests when hidden:** the sweep poll (8 s idle, 1.5 s while a sweep runs)
  now runs through `ForgeIdle.poll`: paused while hidden, backs off to 30 s
  while the server does not answer (the sweep card says so) and recovers by
  itself. Before, it ran while hidden and stopped for good after one failure.
- **Looks:** the top bar wraps instead of overflowing at 760 and 1100 px; thin
  themed scrollbars.

**Verified:** `pytest -q tests` 123 passed (new `tests/test_u1_robustness.py`).
Headless Chrome on a scratch copy (port 9021, temp data): hidden 10 s, 0
fetches and 0 timers (before: 1 each); backend killed, 1 fetch in 0-10 s and 1
in 10-30 s, recovered 21 s after restart (before: never); no horizontal
overflow at 760/1100/1500/1920 on all five views (before: 1118 px at 760 and
1100); no page errors. black and pyright (0 errors) on the touched .py files.
**Not verified:** the real Forge window, and the live app against
`~/AN3-backup` (the backend on 8438 was not running and was not started).
Backend changes reach Emerson's Forge on its next restart; static ones on reload.

Written 2026-09-11, at the end of the session that started it. Read `README.md`
first for the architecture; this file is what is **verified**, what is merely
**reasoned about**, and what is **not built yet**.

This is **stage 1 of a four-stage plan**. The plan is at
`~/.claude/plans/shimmying-frolicking-cosmos.md` and was approved before any
code was written.

---

> Older sections moved verbatim to `WIP-archive.md` on 2026-10-07 (overhaul helper-5): from "Session of 2026-09-14 (later) — the "get new info, keep old data" button" to "The slugify quirk, deliberately reproduced".

## Reasoned about, not verified

- **A sweep over hundreds of subjects.** Six went cleanly in 20 s, so ~40 is a
  couple of minutes. Nothing in the six suggested a limit, but the pacing has
  not been tested against a long run.
- **Hacker News and Lemmy as sentiment proxies.** They currently measure
  *volume and engagement*, not feeling. Whether argument volume correlates with
  anything useful is untested.
- **The `think` tier has never been run.** It is wired, and `chat`/`analyse`
  resolve, but no scenario has been generated because nothing generates one yet.
  Its long-timeout, thinking-on path is unexercised.

---

## Known gaps

- **Reddit returns 403 without OAuth.** Registering a free API app is the fix;
  `SignalSpec.needs_credentials` already exists and excludes such a source from
  automatic sweeps.
- **Hacker News is nearly silent on most world politics.** Of the six subjects
  swept, four returned zero stories. It is excellent on technology and the
  companies around it and close to useless elsewhere — which is on its caveat.
- **A subject needs ~10 readings before any claim is made about it.** Pageviews
  supply 91 on the first sweep, so breakouts appear immediately there; HN and
  Lemmy take weeks of sweeps to build a baseline.
- **`llm.py` duplicates roughly a hundred lines of Dossier's.** The tier
  semantics genuinely differ, but the JSON salvage and the Jan plumbing do not.
  The right fix is `~/Forge/shared/py/`, done deliberately as its own task
  rather than as a drive-by refactor of a verified app.

---

## Next steps, in the order I would do them

1. **Sweep properly** — 100+ subjects, and watch it finish. That is the biggest
   unverified claim here.
2. **Stage 2: scenarios and the forecast ledger.** The ledger is the part that
   makes it learn rather than just opine: every scenario emits dated,
   falsifiable indicators, and when the date passes the app scores itself
   against what the signals actually did.
3. **Embedding retrieval** using the `sentence-transformer-mini` already in Jan,
   replacing the name matching in `world.context_for()`.
4. **Stage 3: the agent loop** — tool registry with its `reversible` flag,
   approval queue, audit log, kill switch.
5. **Stage 4: the personal half**, which the user considers as important as the
   world half — profile, folders, browser history, schedule, tasks, the
   university portal, and the study companion on the `chat` tier.

## The think-tier model, decided

The user set the budget — "only if it'll fit on 28gb of RAM or go for something
smaller" — so the choice was made from the real architecture rather than a guess.
`Qwen3.6-35B-A3B` is **40 layers, 2 KV heads, head_dim 256**, which is
**80 KiB of KV cache per token**:

| quant | weights | KV @32k | compute | total | vs 28 GB |
|---|---|---|---|---|---|
| IQ3_XXS | 13.2 GB | 2.7 | ~1.5 | ~17.4 GB | lots of room |
| Q3_K_M | 16.6 GB | 2.7 | ~1.5 | ~20.8 GB | comfortable |
| **IQ4_XS** | **17.7 GB** | **2.7** | **~1.5** | **~21.9 GB** | **~6 GB spare** |
| IQ4_XS @64k | 17.7 GB | 5.4 | ~1.5 | ~24.6 GB | tight |

**IQ4_XS** was chosen: real 4-bit rather than 3-bit, and still clear of the
ceiling. `cpu_moe: true` keeps the expert tensors off the Iris Xe, which
matters because Dossier's WIP records that two models resident on that iGPU
silently corrupted generation. Only 8 of its 256 experts are active per token.

### Downloaded and verified as a file

17,730,509,792 bytes, exactly the size advertised. The GGUF header parses
clean: **v3, 733 tensors, 54 metadata keys**, `general.architecture:
qwen35moe`, `general.name: Qwen3.6-35B-A3B`, quantized by Unsloth with an
imatrix. Same architecture family as the Qwen3.5 models Jan already runs, and
Jan's llama.cpp backend is build **b9967**.

### The table above was wrong, and the metadata is why

The GGUF carries `full_attention_interval: 4` and a set of `ssm.*` keys. **This
is a hybrid model**: only every fourth layer — 10 of the 40 — keeps a real KV
cache, and the other 30 use SSM state, which is a fixed size no matter how long
the context grows. The cache therefore costs about **20 KiB per token, not 80**:

| context | KV cache | total resident |
|---|---|---|
| 32k | 0.62 GiB | ~19.9 GB |
| **64k** | **1.25 GiB** | **~20.5 GB** |
| 128k | 2.50 GiB | ~21.9 GB |
| 256k (native max) | 5.00 GiB | ~24.6 GB |

`ctx_size` is set to **65536**, deliberately, because it is safe under *both*
readings of that metadata: ~20.5 GB if the hybrid layout works as described,
and ~24.6 GB if it turns out every layer caches after all. Both are inside the
28 GB budget. With no swap a wrong guess locks the machine up rather than
swapping, so the setting that is correct either way wins over the optimistic
one. 128k is very likely fine and is the first thing to try after measuring.

**Still not verified: that it loads, and what it actually costs.** Everything
above is arithmetic over metadata. Jan was already running and is shared
between the user's sessions, so it was deliberately not restarted to pick the
model up — measure `MemAvailable` before and after a load and write the real
number here. If it overruns, `IQ3_XXS` at 13.2 GB is the step down and needs no
other change.

### The no-swap safeguard

Because this machine has 31 GB and **no swap**, running out of memory locks it
up rather than degrading. `llm.chat()` now refuses to *start* a thinking call
when `MemAvailable` is under 3 GB, raising `NotEnoughMemory`, and the interface
shows that as a plain answer pointing at the rules tier. Refusing costs an
answer; not refusing costs the session. Three tests cover it, including that
only the thinking tier is gated — the small models are not the risk.
