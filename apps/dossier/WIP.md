# Dossier — state of play

## U1 sweep (2026-10-08, Relay task 74)

Group G12, done by Relay task 77. Report: `sessions/2026-10-07-overhaul/reports/u1-G12.md`.

**Critic follow-up (same day):** "Get new info" now reads progress through
`watch("newInfoWatch", ...)`, so it rests while hidden and survives a server
blink; queue buttons and history start stay disabled while their request is
out (three clicks on deepen used to queue 75); `store.MAX_SLUG = 200`
(`subject_dir` refuses longer, `slugify` cuts to it). Verified in headless
Chrome with the critic's repro scripts and by `pytest` (319 passed); details in
the report's Critic section.

- **Path safety (backend):** `store.subject_dir` refuses a slug that is empty,
  `.`/`..` or holds a slash (`store.BadSlug`, answered as 404). Before this,
  `DELETE /api/subject/%2E%2E` resolved to `subjects/..`, the library itself.
  `dossier.delete` also only removes a name `slugify` could have made (checked:
  all 2,450 folders in `~/AN3-backup/DossierData/subjects` pass).
- **Wrong-typed numbers are a 400, not a 500:** queue recipe/deepen `limit`,
  briefing `days` (now clamped 1-3650), watch `every_hours`/`per_sweep`,
  history `limit`. An unknown briefing `kind` is a 400 (rebuild) or 404 (read).
- **Rests when hidden:** the queue watcher (4 s) and the history watcher (3 s)
  now run through `ForgeIdle.poll` (page loads `/shared/forge_idle.js`): they
  pause while the page is hidden, back off to 30 s while the server does not
  answer (the jobs card says so), and recover by themselves.
- **Looks:** the top bar wraps onto a second row instead of pushing the page
  sideways at 760 px; thin themed scrollbars (incl. `::-webkit-scrollbar`).

**Verified:** `pytest -q tests` 318 passed (new `tests/test_u1_robustness.py`).
Headless Chrome on a scratch copy (port 9020, temp library, Jan pointed at a
dead port): hidden 10 s with the queue running, 0 fetches and 0 timers
(before: 9 fetches); backend killed, 1 fetch in 0-10 s and 2 in 10-30 s,
recovered 27 s after restart (before: never); no horizontal overflow at
760/1100/1500/1920 on world, jobs, links, watch, library (before: 760
overflowed to 1072 px); no page errors. Shots: `/tmp/u1/G12/after-dos-*.png`.
black and pyright (0 errors) on the touched .py files.
**Not verified:** inside the real Forge window (WebKitGTK). Static changes
reach Emerson's Forge on the next page reload; the backend (.py) changes only
on his next Forge restart.

**2026-09-25 (S5, ask A25 "find the files again, I moved them from an N3
to the laptop"):** "N3" is the AN3 drive. His library (2,447 subjects,
492 MB) now sits at `~/AN3-backup/DossierData`; with AN3 unplugged Dossier
fell back to the empty `~/DossierData-local`. Every file in a library is
stored relative to the library folder (only the self-rewriting
`dossier-manifest.json` held the old absolute path), so the fix relinks the
folder, not individual files. New `location.py`: finds library-shaped
folders (index.json + subjects/) under home and mounted drives in 0.08 s,
remembers his pick in `~/.config/forge-dossier/location.json`, and
`store.data_root` uses that pick before AN3 or the fallback (so a re-plugged
AN3 cannot split the library). UI: click the storage pill for the "Library
folder" dialog (found folders with subject counts, "Use this folder", a
"Search here" box); it opens by itself when the folder in use holds fewer
subjects than one found elsewhere. Verified: 304 tests (4 new in
`tests/test_location.py`; `conftest.py` now keeps every test off the real
saved choice); black; pyright 0 errors on the touched files; scratch server
(scheduler off, scratch choice file) auto-offered
`~/AN3-backup/DossierData` with 2447 subjects (screenshot), refused a
non-library folder with 400, and after choosing, `/api/status` storage
reported the new path. **Not done: nothing was chosen for real.** Emerson
picks it in the dialog after Forge restarts Dossier (the running copy has
the old code). Foresight has the same shape of move
(`~/AN3-backup/ForesightData`), not covered here.

**2026-09-19 19:50 (from a PanelForge session):** `janidle.py` was the
thing unloading Jan's 4B under other apps' requests (17 releases in
`outputs/dossier.log` against 14 router unloads today; the shared
`forge_jan.release` cannot unload at all, it gets 401). The CPU-tick test
misses a request that arrived in the last check interval, so before an
unload the watcher now asks the model server's own `/slots`
(`model_ports`, `slots_busy`; unreachable counts as busy). Tests
`tests/test_jan_idle.py` 12 pass. Takes effect when Dossier next starts
(the running Forge was not restarted).

Last touched 2026-09-15. Read `README.md` first for the architecture; this file
is what is **verified**, what is merely **reasoned about**, and what is **not
built yet**. Newest session first.

---

## Session of 2026-09-15 — agreed plan, not built yet

The user: *"check through the dossier app, I'm not sure that it works as
intended ... I want the info collected to be more in-depth and I want bios of
everyone and everything, and the info saved not just in links ... pass through
everything I collected before you add the feature of grabbing more"*. Scope was
settled over several rounds of questions. **Nothing below is built.**

### Order the user chose

1. **Full check, report first.** Tests, every tab on real subjects of each
   type, every button; list what is broken before building. The user reported
   that deep dives do not work, only quick passes do (see findings below).
2. **All-in-one view** per subject: facts, article, history, news, claims,
   quotes, relations, pictures, and the **saved text of each source readable in
   the app** (it is on disk in `text.json.gz`; not yet checked whether any page
   shows it).
3. **One standard research pass** replacing quick, deep and pictures:
   - everything in one go, claims included (~20-27 min per subject; the user
     accepted weeks of running), nonstop, most prominent first;
   - a short TL;DR bio and a longer in-depth bio per subject, written by the
     local model in Jan, every sentence cited (the existing citation gate);
   - every outside name in relations (schools, offices, ideologies, relatives;
     1,100+ of them) becomes a full dossier;
   - news naming the subject, plus a separate labelled section of news about
     closely linked subjects (party, country, wars);
   - the Quick, Deep and Pictures choices are removed everywhere (dossier page,
     queues, seeding) — the user confirmed this — leaving one Research button;
   - the library shows complete / in progress plus markers for picture, bios,
     news and claims. Held data is merged, never replaced.
4. **A progress manifest written about every 5 minutes** while research runs,
   so a laptop crash loses at most a few minutes of state.
5. **At the end of the session that builds this: restart research as a full
   redo of every held subject** with the standard pass. The user said "delete
   all held data if you have to"; it is not needed, because a redo merges, so
   **no data is to be deleted**.

6. **Speed: use the whole iGPU and about half the CPU.** The user: *"all the
   gpu gets used and half the cpu ... if it needs 2 models running at once
   that's fine ... whatever will make this faster"*. Plan: the reason-tier
   model on the iGPU, the triage model on CPU pinned to 6 of 12 logical
   threads, then measure subjects per hour. **Two models on the Iris Xe
   corrupted output before** (see *Speed and scraping* below); only retry it
   behind an automatic garbage-token check on real extractions, and revert if
   the check fires.

### The user's answers to the final nine questions (no further questions wanted)

1. Stop the 4 in-flight deep dives **now** (backend restart; they return to
   queued).
2. When the standard pass is ready: **delete the old queues** (`hh`, `hhhhh`)
   and create one "Standard pass: whole library" queue, most prominent first.
3. Jan may be reconfigured and restarted, **but only after checking that no
   other session is using it**.
4. Model for bios and claims: **measure 4B vs 9B vs 35B-A3B on 3 subjects** and
   use the fastest one whose output passes the quality checks (citation gate,
   span gate, garbage-token check).
5. In-depth bio length: **as long as the sources allow**. Short bio: 2-3
   sentences.
6. Outside names: **every one becomes a dossier, no exceptions** — including
   generic concepts (occupations, religions, ideologies, languages).
7. Linked news: **close ties only** — country, party, spouse or family, and
   wars taken part in.
8. The all-in-one view is a **new "Everything" tab**; Overview stays first.
9. Crash manifest every ~5 minutes: **research progress and build progress,
   written to both AN3 and the internal disk**.

### Step 3 — the standard pass: NOT BUILT. Plan for the next session

Everything above is done; this is what remains of the agreed order. The
research queue is **left paused on purpose**: the user asked for the whole
library to be redone once the new pass exists, and redoing it with the old
quick/deep passes would spend weeks producing results without bios, linked
news or the outside names. Start the redo at the end of the session that
builds this.

1. **Measure before building (Jan).** Check no other session is using Jan
   (`janidle.model_ticks()` CPU moving = in use). Compare the 4B, 9B and
   35B-A3B on 3 subjects for claim extraction and bio writing; pick the fastest
   whose output passes the span gate, `claim_matches_span` and a garbage-token
   check (non-Latin runs / invented words inside JSON). Target: whole iGPU for
   the reason model, the triage model on 6 of 12 CPU threads. Only retry two
   models on the iGPU behind that garbage check.
2. **One `standard` phase in `research/pipeline.py`**: every quick and deep
   source, claim extraction (via `read_articles`), the whole article, filing
   the news archive for the subject (`enrich`), downloading pictures
   (`research/images.py`), and bios. Replace Quick / Deep dive / Update / Get
   pictures with one **Research** button (dossier header in `app.js`
   ~line 456), and remove the phase pickers (`recipe-phase`, `add-phase`,
   `q-deepen` in `index.html`/`app.js`). The user confirmed removing them.
3. **Bios** — new `research/bios.py`: a 2-3 sentence TL;DR and an in-depth bio
   as long as the sources allow, written by Jan from the stored article,
   claims and timeline, every sentence carrying a citation marker, uncited
   sentences deleted (same gate as `ask.py` / `briefing.py`). Store as
   `bios.json` (add to `dossier.FILES`, object file); show at the top of
   Overview and Everything.
4. **Linked news** — during the pass, copy news items from the subject's close
   ties (country, party, spouse/family, conflicts taken part in; from
   `relations.json`) into a separately labelled section, never mixed into the
   subject's own news.
5. **Every outside name becomes a dossier, no exceptions** — the graph's
   ~10,549 outside nodes, queued by prominence after the held library. The
   seven entity types do not fit schools, offices, religions or ideologies:
   add a catch-all `entities/topic.py` (one file, registry).
6. **Library tags** — replace quick/deep with complete / in progress plus
   markers for picture, bios, news, claims (`dossier.reindex` rows +
   `renderLibrary` in `app.js`).
7. **Then**: delete queues `hh` and `hhhhh` (user's choice), create
   "Standard pass: whole library" with redo on, seed every held subject most
   prominent first, then the outside names, and **start it**.
8. Leftovers from the check: 6 briefing, 11 mind-map labels, 12 treaties as
   alliances, 13 news de-duplication, and the 390 px layout.

### Haiku batch manifest (asked for at the end of the session)

`haiku-batch-manifest.json` in this directory: a prompt, commands, stdlib-only
scripts and per-subject statuses for a separate low-cost Claude session
(`claude --model haiku`) to redo the **139 subjects whose deep dives failed**,
most prominent first — `new-info` (article + news) for each, then a deep dive
each in a new queue "Haiku batch: redo failed deep dives" (redo on; older
queues untouched). The session starts and records work; the app does the
research. The file is also that batch's crash record. Not run yet.

### Queue state when paused (2026-09-15)

The user asked for their background research to be stopped until the new pass
is ready. Queue `hhhhh` (id `0daf7ee788`, `redo_held: true`, all `phase: deep`)
held 146 queued, 4 running (Erdoğan, Netanyahu, Lula, Meloni), 1 done. The old
queue `hh` is empty.

### Verified so far this session

- AN3 mounted, backend live on 8437, **2,444 subjects** (802 people, 590
  countries, 460 conflicts, 437 alliances, 87 parties, 68 organisations).
- **253 tests pass.**
- Sample of 20 subjects: 7 have **no `article.json`** (including Zachary Taylor
  and Tô Lâm) and most have **zero news events** — Fill in history has never
  been run on the real library.
- **Deep dives do complete**: Donald Trump's finished today in 1,599 s (+120
  quotes, +101 events, +17 sources, +21 claims).
- The 4 in-flight deep dives were stopped by a backend restart; the queue came
  back paused, 0 workers, 150 queued, 1 done. **Forge did not respawn the
  backend** — it is now running standalone (`setsid nohup uvicorn`, logging to
  `~/Forge/outputs/dossier.log`).

### Full check — problems found (verified against real data unless noted)

Library-wide (2,444 subjects): article 52%, pictures 14%, quotes 18%, claims
**1%** (34), marked deep 173. All 61 news-archive months are downloaded but
news was never filed into most subjects. Every page of one subject per entity
type builds without error, and every read-only route answers 200.

1. **Deep dives "succeed" with nothing extracted, and are then marked deep.**
   139 of 173 deep subjects hold zero claims. Reasons recorded in their
   `history.json`: Jan not reachable at the time (79); Jan 500 *"The model
   produced output that does not match the expected peg-native format"* (36);
   Jan proxy errors (8); read timeouts (6); Vulkan `ErrorDeviceLost` (4);
   connection refused (2); two with no note at all (Ecuador, Moldova — 72 and 67
   documents triaged, zero claims). `dossier.save()` sets `depth = "deep"` from
   the requested phase alone (`dossier.py:180`), so a failed deep dive is
   recorded as done and a redo-off queue would skip it as "already held (deep
   pass)". Nothing in the UI shows the failure.
2. **One Jan error ends all claim extraction for that subject.**
   `pipeline.py:284` breaks out of the article loop on the first
   `JanUnavailable`; there is no retry.
3. **A verified claim can contradict its own quote.** Trump, Record & disputes:
   *"Donald Trump won the 2024 presidential election decisively"*, `verified`,
   quoting *"...Trump won the 2016 presidential election against Democratic
   Party nominee Hillary Clinton."* The span gate (`claims.py:177`) only checks
   that the anchor sentence exists, not that it supports the paraphrase.
4. **Record & disputes shows "Claims · 0 — No claims yet" above the real
   claims** whenever there are no disputed ones (the disputed block renders its
   empty state). Screenshot.
5. **Repeated values in fact rows**: Trump's Party row reads "Republican Party"
   three times. `common.facts_block` joins lists without de-duplicating.
6. **The world briefing was built while Jan was off** and still says so on the
   World tab; "Unattributed" is its top country.
7. **Saved source text cannot be read anywhere in the app** — no route or
   frontend code reads `text.json.gz`.
8. **Missing articles are just missing**: e.g. Zachary Taylor was researched on
   2026-09-11, before articles were collected, and nothing backfilled him.
9. **Jobs tab says "Failures: none"** while 139 deep dives extracted nothing —
   the failures above are recorded only as notes inside each subject's history.
10. **Every Jan error is treated as "Jan unavailable"** (`llm.py:205-208`): a
    single 500 on one article is indistinguishable from Jan being off, and
    `chat_json` turns an unparseable reply into `[]` with no note (likely
    Ecuador and Moldova).
11. **Mind map labels pile on top of each other** around the centre node at 2
    hops (Trump, 90 nodes) and are mostly unreadable. Screenshot.
12. **Treaties are filed as alliances**: "1949 Armistice Agreements", "1975
    Algiers Agreement" and "2020 Nagorno-Karabakh ceasefire agreement" carry the
    *Alliance or bloc* tag in the library.
13. **News page, Germany**: a Britannica page titled "Friedrich Merz" appears as
    a dated news item; "How risky is the German government's borrowing spree?"
    appears twice (DW.com 09-09 and dw.com 09-08) — the domain is not
    case-folded for de-duplication. Not yet traced in code.
14. **The watcher is switched on** (Watch tab) but has never swept, because the
    queue is paused.

### Fixed this session (tests first; backups in `~/Forge/backups/dossier-20260915-standard-pass/`)

`tests/test_check_fixes.py`, 22 tests, written and seen failing before the
fixes. After: **275 passed** (253 before), `black` run, `pyright` 0 errors.

- Problem 1 — `dossier.save()` records `depth: deep` only when the report says
  `claims_complete` (missing key counts as complete, for old callers);
  `RunReport.claims_complete` is set by the new `pipeline.read_articles()`.
- Problems 2 and 10 — `llm.JanRequestFailed` (a subclass of `JanUnavailable`,
  so every old handler still catches it) for a 4xx/5xx reply, a timeout, or a
  reasoning-only reply; a 5xx is retried once after `RETRY_PAUSE` (5 s).
  `read_articles()` skips a failed article and keeps reading; only a real
  connection failure stops it.
- Problem 3 — `claims.claim_matches_span()`: every figure (year, count, amount)
  in a claim must appear in its quoted sentence, or the claim is dropped.
- Problem 4 — Record page omits the disputed block when there are none.
- Problem 5 — `facts_block` and `properties.grouped` de-duplicate list values.
- Problem 9 — `jobqueue._incomplete()`; the Jobs tab's failures list now
  includes deep dives that finished without their claims (new jobs only; the
  139 old ones carry no `claims_complete` key).

**Step 2 built — the Everything tab** (`pages/everything.py`, second tab on all
seven entity types). Blocks: pictures, grouped facts, seats, the whole article,
news, the timeline without news (no limit), every claim, every quote,
relations, **sources with their saved text**, notes. New block kinds in
`app.js`: `pictures` (drawn from the subject's downloaded images) and
`source_texts` (lists every source; `GET /api/subject/{slug}/texts` says which
have text, and `GET /api/subject/{slug}/text/{source_id}` loads one when its
fold is opened). `dossier._held_dir()` refuses any slug `slugify` would not
produce, so `..` never becomes a path. `claims_block`/`quotes_block` now treat
`limit=0` as no limit. `tests/test_everything.py`, 10 tests seen failing
first; **285 passed**, pyright 0, `node --check` ok, Forge CSS token test ok.
Cost: the tab repeats the other tabs' data in the one `/api/subject` response,
so that response roughly doubles (Trump ~0.7 MB → ~1.4 MB).

Everything tab screenshotted on Angela Merkel (desktop, full length, 390 px):
pictures grid with all 6, grouped facts, 45-section article, news, timeline.
Via HTTP: 72 sources with saved text (63,152 words), longest 27,736 words read
back whole; `..%2F..` slug and an unknown source both 404. **At 390 px the page
scrolls sideways and the header leaves a large gap** — from the existing top
bar and header actions row, which this session did not change; not fixed.

### Jan's idle models (the user: "using too much RAM doing absolutely nothing, make it close Jan when we ain't using it")

- Two idle models held ~9.8 GB RSS (2B 5.6 GB on CPU, 4B 4.2 GB). Jan runs a
  llama.cpp **router** (`llama-server --models-preset ... --port <random>`)
  that needs `Authorization: Bearer $LLAMA_API_KEY` (read from the router
  process's own environment) and supports `POST /models/unload {"model": id}`;
  `--models-autoload` is on by default, so the next request loads a model back.
- Verified: both unloaded while idle (0 % CPU over 3 s, no connections, queue
  paused) — **available memory 9.45 GB → 23.08 GB**, Jan still answering.
- Verified: with both unloaded, a request through Dossier's `llm.chat` loaded
  the 2B back and answered in **1.9 s**; the next call took 0.5 s.
- **Built: `janidle.py`**, started from `web_app` startup beside the memory
  guard. Every 30 s it reads each `llama-server --alias` process's CPU time
  from `/proc`; a model whose CPU time has not moved for
  `DOSSIER_JAN_IDLE_SECONDS` (default 300; 0 turns it off) is unloaded through
  the router, found from `/proc` by its `--models-preset` flag with the key
  from its environment. Nothing is released while `llm.in_flight()` > 0 (a
  counter around every Jan request, including ones waiting for a slot).
  `tests/test_jan_idle.py`, 9 tests, seen failing first. 294 passed, pyright 0.
- **Verified live**: the 2B was loaded with one request, then left alone; the
  running backend released it **332 s later** (300 s wait + 30 s check) and
  logged `released idle Jan model ...`; available memory back to 22.1 GB.
  Not observed: a release while another app (the Arcade) is mid-use — covered
  only by the CPU-time rule and its test.

### The crash manifest (asked for: "every 5 mins manifest in case the laptop crashes")

`manifest.py`, started from `web_app` startup: writes at startup and every 300 s
to **`<data root>/dossier-manifest.json` (AN3) and
`~/Forge/outputs/dossier-manifest.json` (laptop disk)**, each via a temp file
and rename; a failing destination never stops the other. Holds the active
queue and its counts, what is running, the last 20 finished, failures, library
size, loaded Jan models, available memory, how to resume, and the path and
modification time of this `WIP.md` (the build progress). The queue itself was
already crash-safe on disk. `tests/test_manifest.py`, 3 tests, seen failing
first.

Not fixed yet: 6 (briefing), 8 (missing
articles — the standard pass), 11 (mind map labels), 12 (treaties as
alliances), 13 (news de-duplication). The 139 subjects wrongly marked deep
still say deep; the standard-pass redo covers them.

Worked as expected in screenshots: World map and arcs, Library grid and
filters, Germany News (496 items, year chips, citations), Economy timeline,
Watch and Jobs tabs render without visible errors.

**Scale correction:** the Connections tab reports **12,993 nodes, 10,549 of
them named by a record but without a dossier** — not the "1,100+" in older
notes. "Every name becomes a dossier" therefore means ~10,500 new subjects on
top of 2,444. At ~25 min each that is months; most-prominent-first ordering is
what keeps it useful.

---

> Older sections moved verbatim to `WIP-archive.md` on 2026-10-07 (overhaul helper-5): from "Session of 2026-09-14 (later) — the "get new info, keep old data" buttons" to "The performance finding that matters most".

## Reasoned about, not verified

- **Bulk runs beyond ~50 subjects.** One 47-subject run completed cleanly (see
  above). A job of several hundred, or one left running for twelve hours, has
  not been observed — though nothing in the 47 suggested a limit.
- **Deep dives at scale.** One measured deep dive was 21 minutes, so ~30 deep
  dives is roughly an overnight run. Only one has been run.
- **Relevance thresholds.** `MIN_KEEP = 0.15` and the triage band 0.28–0.62 are
  judgement calls that behave sensibly on the subjects tried. They have not been
  tuned against a labelled set, and a subject with an extremely common name may
  well need different ones.
- **Extraction quality on hostile layouts.** The reader strips furniture and
  keeps paragraphs; it works on the sites tried. Paywalled and heavily
  scripted pages will yield little, and are simply skipped when they do.

---

## Known gaps

- **Google News gives headlines only.** Its links resolve to the publisher
  client-side, so the body is not reachable from the feed. Headlines still feed
  the timeline, marked `headline_only`, and claims are never extracted from
  them; full text comes from DuckDuckGo Lite. This is a documented limitation,
  not a bug to hunt.
- **Map country matching is by name**, with an alias table for the usual
  collisions (United States of America, Czechia, Dem. Rep. Congo…). A country
  whose Wikidata label is missing from that table will shade as unheld even
  when subjects exist for it. `COUNTRY_ALIASES` in `static/app.js`.
- **GDELT is often rate-limited** (429). It backs off and is skipped; it is
  never on the critical path.
- **Claim quality is bounded by a 4B model.** The span gate stops fabricated
  quotations, but a claim can still be a clumsy paraphrase of a real sentence.

---

## Asked for — all three now built (2026-09-11)

Left here for the record of what was asked and where it landed:

1. ~~**Relationships drawn between subjects on the map**~~ — built as
   `research/arcs.py` + the arc controls on the World tab. Conflict arcs work on
   today's data; alliance arcs need a redo pass (see the session notes above).
2. ~~**A continuously running news watcher**~~ — built as `watcher.py` + the
   Watch tab. Off by default; it has never completed a real sweep.
3. ~~**More economic and social indicators**~~ — built as `sources/owid.py` +
   the Society & development tab, nine series beside the World Bank's nine.
   **IMF is still not done** and would be one more file in `sources/` following
   exactly the same shape.

## The data-loss bug — read this before touching the pipeline

Making source gathering concurrent introduced a variable shadow that cost 146
subjects:

```python
for name, result, error in pool.map(_gather, pending):   # shadows research(name)
...
"slug": store.slugify(name),                             # now the ADAPTER's name
```

Every subject researched after that loop was stored under the name of whichever
source adapter finished last. Because saving *merges* rather than overwrites,
they did not fail — they piled into three directories. One dossier called
"United States" ended up holding **2,009 sources and 3,658 events drawn from
about 146 unrelated subjects**, and every job reported success. Merging made it
worse than plain loss: the data was wrong rather than absent, and there is no
per-subject provenance to unpick it with.

Fixed by pinning `slug = store.slugify(name)` as the first statement of
`research()`, before anything can rebind it, and renaming the loop variables.
`tests/test_pipeline_slug.py` reproduces the failure offline and fails against
the old code. The three conflated dossiers were moved to
`DossierData/quarantine/` rather than deleted, and the affected subjects were
re-researched.

**Two neighbouring bugs found the same way:**

- `data_root()` re-decided on every call and probed with a *shared* filename.
  Under concurrency one thread unlinked the probe another had just written, so
  a working drive was declared unwritable — sending some subjects to the
  fallback directory, and at 16 threads raising outright. It now resolves once
  per process and probes with a unique filename.
- `queue.start()` returned early if any worker was alive, so a worker that
  started while the queue was momentarily empty exited and was never replaced.
  A 146-subject run was quietly proceeding on **one** thread. The pool now tops
  itself up and idle workers wait rather than exit.

## Two things the bulk run exposed

- **Historical states appear as countries.** Citizenship in Wikidata includes
  former states, so "Soviet Union" and "Czechoslovakia" show up in the country
  rollup for people born there. It is honest data, but they can never shade on
  a modern map — which is why 45 of 54 countries are drawn, not all of them.
- **Storage was being wasted 78-fold.** 48 subjects held 3.9 MB of real text
  but occupied **303 MB** on disk: exfat uses a 256 KB cluster, and each of the
  675 per-source extracts (median **181 bytes**) consumed a whole one. Article
  text now goes into one `text.json.gz` bundle per subject, and a migration
  folded the existing 675 files in without loss — **303 MB → 134 MB**. The
  remaining overhead is the nine JSON files each subject keeps, so the floor is
  about **2.3 MB per subject** on this filesystem; a thousand subjects would be
  roughly 2.3 GB of the 117 GB available. Packing those nine into one file
  would cut it further but would cost the property that each file is separately
  readable and repairable.
- **The briefing response was 206 KB.** It carried every event it had
  considered, on every page load, for a panel that shows a summary and a
  country list. `/api/briefing` now trims that to about 5 KB and serves the
  whole thing only on `?full=1`.

## Repairing stored data after a rules change

`dossier.regrade(slug)` recomputes every stored claim's confidence from the
evidence already held — no refetching, and it never touches the evidence
itself. It was used after the numeric-conflict fix above, which turned the one
false `disputed` back into `reported`. Reach for it whenever the corroboration
rules change; the alternative (deleting and re-researching) throws away work.

## Next steps, in the order I would do them

1. **Let the existing *First run* queue finish, or stop it.** It still has jobs
   waiting, which is why the news watcher has never run. Nothing else here
   unblocks until that queue is idle.
2. **A redo pass over the 199 alliances** with *redo subjects I already hold*
   ticked. That is what turns alliance arcs on, and it widens the connection
   graph at the same time, since membership is now an edge kind.
3. **A redo pass over the 212 countries** so OWID figures reach more than
   Germany, and the Society & development tab is populated across the library.
4. Then switch the watcher on and confirm a real sweep end to end — the one
   path in it that tests cover only against a stub.
5. Still open from before: a deep dive over the top 10 by prominence, read
   critically, to judge whether the 4B is good enough for the `reason` tier.
