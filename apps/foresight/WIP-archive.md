# foresight WIP archive

Sections moved verbatim from `WIP.md` on 2026-10-07 (overhaul helper-5) to keep the live WIP short. Nothing was rewritten or deleted; original order kept. The full pre-move file is in `~/Forge/backups/2026-10-07-overhaul/wip/foresight-WIP.md`.

## Session of 2026-09-14 (later) — the "get new info, keep old data" button

The user: *"a button to keep old data but the button will get all the new info
that you just added"*.

- **Signals tab: Get all new info for what is held.** `POST /api/sweep` with
  `history: true` sweeps every subject that already has signals with the full
  five-year window from every source (`sweep_subject(history=True)`), then
  `plans.learn()` for each. Falls back to the watchlist when nothing is swept.
- **A race fixed.** `start_sweep` now marks the sweep running before starting
  its thread. The first live check of the button stopped after one poll because
  the status still read idle, and the page had the same bug (it would then wait
  eight seconds before looking again).

### Verified — actually run

- **Tests pass** (4 new in `tests/test_new_info.py`: a history refresh reads
  five years for an already-held source and keeps a 2019 reading; held subjects
  are those with signals; the button sends them with `history`; it falls back to
  the watchlist). `black`, `pyright` 0 errors, `node --check` clean.
- **Live, on a scratch backend**: status read `running = True` straight after
  the request; both subjects re-read (World Bank 173 and 175 figures, 242 and
  156 news items over 60 months), then learned from 11 and 12 series. A
  pageviews reading dated 2015-07-01, planted outside the window, was still
  there afterwards with its detail unchanged.
- Screenshot of the Signals tab with the button and a history sweep running.

### Not verified

- Not pressed against the real `ForesightData` (AN3 unplugged). Expect roughly
  5-10 seconds per subject, most of it paced API calls.

---

## Session of 2026-09-14 — five years of history, and learning from it

The user: *"go through foresight and make it better ... make it learn and take
info for the past year and 5 years of news"*. README section 8 is the design.

### Built

- **Five years on the first sweep.** `sweep.HISTORY_DAYS`; a source this subject
  has never stored reads five years, later sweeps the usual window.
- **`signals/news_events.py`** — monthly count of Current Events items linking
  the subject, read-only from Dossier's new news archive.
- **`fx.py` was broken**: `api.frankfurter.app` now 301s every request. Moved
  to `api.frankfurter.dev/v1`.
- **`trend.py` baseline** is the last 90 readings, not the whole series.
- **Backtest learning** in `plans.py`: `backtest()`, `learn()`,
  `lessons_summary()`, `learned/<slug>.json`, `POST /api/plans/learn`, and the
  Plans tab card *What history taught*. `from_rules()` leaves out claims where
  assuming no change beat a line, and notes the backtest record on the rest.
- **A line is not carried further forward than its readings reach back.** Found
  in the first screenshot: Lemmy, with four days of readings, was projected
  from 14 to 2,640 in two years, and Hacker News counts below zero. Such claims
  are now not made, and the scenario's basis counts them.

### Verified — actually run

- **100 tests pass** (87 before, 13 new in `tests/test_history.py`); two older
  fixtures in `test_plans.py` were 84 days long and asked for a 90-day claim,
  so they were widened by one week rather than weakening the new rule.
  `black` run, `pyright` 0 errors.
- **Live sweep** into scratch roots, real network: Zelenskyy 1,783 days of
  pageviews and 60 months of news counts; Australia 1,827 days of pageviews and
  **1,280 daily exchange rates back to 2021-09-14** on its first sweep.
- **Live backtest over those two subjects**: 23 series; straight-line claims
  held **110 of 306 (36%)**; no change beat a line **29** times, a line won
  **6**. That is the point of it: most of what the rules tier used to assert
  was worse than saying nothing would change.
- Australia's rules scenario after both rules: *4 projections from 14 series; 13
  left out by backtest; 5 not made because the series is younger than the
  forecast*. Every remaining claim carries its record, e.g. population "held 10
  of 12 times when backtested on this series".
- Plans tab photographed in headless Chrome from a scratch backend, with the
  ledger and *What history taught* side by side.

### Not verified

- **No live sweep on the real library** — AN3 was unplugged all session, so the
  real `ForesightData` and the 1,212-subject Dossier library were not reachable.
- A backtest is marked against history the method could have been tuned on.
  36% is a hindcast, kept apart from the live ledger on purpose.
- Several World Bank series for a **person** (Zelenskyy has Ukraine's GDP) come
  from the existing `worldbank.py` resolving citizenship. Pre-existing, not
  changed here, worth deciding on.
- `news_events` depends on Dossier having run *Fill in history* or a research
  pass first; until then it reads nothing.

---

## Session of 2026-09-11 (later still) — real numbers, and a Plans tab

The user, using the app: *"i want it to atore finlcian and economic and
polotacl things not just how may time they wrer searche dup that says nothing
balsicaly findigs is usless"*, then *"also make rules better at natural
language"*, then *"let it have a tab for plans ans scenearios as its a forsight
ai"*. All three are addressed here.

### The app measured only attention, and that was the real complaint

Every signal was a proxy for curiosity or argument. Three sources now measure
something published:

| source | kind | what it is |
|---|---|---|
| `worldbank` | economy | Nine indicators — GDP, GDP per person, population, unemployment, inflation, inequality, life expectancy, military spending, government debt. Annual. The indicator table is **imported from Dossier's** `sources/worldbank.py` rather than copied. |
| `fx` | markets | The subject's currency against the US dollar, daily, from the ECB via frankfurter.app. |
| `gdelt` | politics | Share of world news coverage, and average tone — the first actual feeling signal here. **Off by default**, see below. |

A source can now publish **several series**: `Reading.series` names which one,
and `sweep` splits them into `worldbank.gdp`, `worldbank.unemployment` and so
on. Without that they shared one file and, being keyed by date, silently
overwrote each other — GDP and unemployment for the same year cannot coexist in
one series.

### The z-score was the wrong question for an annual figure

`trend.py` asks "is today unlike this subject's normal". An economic indicator
trends, so its newest year is routinely its largest value and a z-score would
report a breakout every single time. `trend.py` now measures each series'
cadence and leaves anything slower than 45 days to the new **`level.py`**, which
asks the questions a person actually asks of a slow series: where does it
stand, which way did it move, is it a record. The two analysers divide every
series between them and **neither names a source**.

`all_findings` also interleaves by kind now. Strict weight order made the page
useless: a breakout saturates at eight sigma, so two dozen pageview spikes tie
at 1.0 and every economic finding fell below the fold. Nothing is hidden or
reweighted — the strongest kind still leads.

### The Plans tab

`plans.py` plus `/api/plans`. A scenario is branches of the future and **every
branch carries dated, falsifiable indicators**: a named stored series, a
direction, a number and a date. The ledger marks them by arithmetic when their
dates pass, with no model involved, so a scenario written by the think tier is
marked exactly the same way as one written by the rules tier and the two can be
compared honestly.

The rules tier writes one with no model at all: ordinary least squares over each
stored series, carried forward, stated as a claim. That is the baseline any
cleverer forecast has to beat, and it is why the tab works with Jan off.

Two traps that are closed and tested:

- **A reading older than the forecast cannot test it.** An annual series whose
  next figure has not published still holds the reading the projection was drawn
  from; marking against that would score every forecast correct for free.
- **A slow series is not projected to a date it cannot reach.** A yearly figure
  projected three months out is unmarkable, so that claim is never made.

A model's branch is kept only if its indicators name a series this app actually
holds and give a real future date. Anything else is **discarded**, which is the
same rule Dossier applies to an uncited sentence.

### Natural language

- `world.match_subject()` stems words, so *"chinas population"* reaches
  "People's Republic of China". The `-es` rule only fires after a sibilant —
  taking it off everything turned "peoples" into "peopl" and broke that same
  question a second time.
- **Scoped answers.** *"what changed in australia"* returned the whole library's
  movers and mentioned Australia nowhere; *"how much is held turkey"* counted
  the library. Both now answer about the subject when one is named.

### Verified — actually run

- **87 pytest tests pass** (49 before, 38 added), `black` clean across 23 files,
  `pyright --pythonpath ./.venv/bin/python` reports 0 errors.
- **Live data on the real drive.** 173 World Bank figures for Australia across
  nine series; 65 days of AUD/USD; a six-country sweep stored 140–170 readings
  each for Afghanistan, Albania and Algeria and correctly stored **nothing** for
  the Abbasid, Achaemenid and Akkadian empires.
- Findings for Australia read as economics, not search counts:
  *"GDP — 1.8tn US$ in 2025, up 2.4% from 1.76tn — the highest in 20 readings"*.
- The Plans tab photographed in a real browser, and a rules scenario written,
  scored and deleted over HTTP.
- All four of the user's failing questions answered through `/api/ask`.

### Not verified

- **GDELT has never stored a reading here.** The adapter is right — a live 200
  with 86 rows was captured — but every request since answered 429. Dossier
  runs on this machine with four workers and a two-thousand-subject queue and
  uses GDELT too, saturating the per-IP limit. It is registered but
  `enabled=False` so a sweep does not spend eighteen seconds per subject on a
  source that will not answer. Turn it on in `signals/gdelt.py` when Dossier's
  queue is idle.
- **The model path for scenarios has never run against Jan.** It is covered by
  five tests against a stubbed answer, including the discard rules, but no
  think-tier scenario has been generated.
- **No indicator has ever been scored `met` or `missed` in anger.** The ledger
  is covered by eleven tests, but every live indicator is dated months ahead,
  so the scoring path has only run against fixtures.
- Currency is only correct for the ~30 currencies the ECB publishes; anything
  else reads nothing, deliberately.

---

## Session of 2026-09-11 (later) — the rules tier stops refusing

The user typed three questions and was refused all three:

```
population of australia   ->  "not a question the rules tier can settle"
trump                     ->  "not a question the rules tier can settle"
who is important          ->  "no subject matches that name closely enough"
```

All three were answerable from what is already on the drive. The tier was
keyword-triggered, so anything phrased in a way nobody had listed bounced, and
*"who is important"* was worse than a refusal — it matched the `who is` keyword,
went looking for a subject named "important", and failed.

### What changed

- `Solver` gained an optional `handles_stored(question, world)`: a second
  matching pass, run only when no keyword matched, allowed to read the library.
- **`fact` solver** — one stored fact about a named subject, matched against
  the keys that subject actually has rather than a list in `tiers.py`. Adding a
  Wikidata property in Dossier makes it answerable here with nothing edited.
- **`rank` solver** — the library ordered by `dossier_link.ranked()`, with an
  entity-type filter so *"the biggest countries"* does not answer with people.
  It states that the ranking is coverage, not merit.
- **bare names** route to the subject solver.
- `world.match_subject()` was extracted to a module-level function (the tests
  now drive the real rule instead of a stub reimplementing it, which is how the
  stub and the app drifted apart once already) and gained surname matching.
- The refusal now lists what the tier *can* answer, with the words that work.

### Verified — actually run

- All three of the user's questions answered against the real library:
  `Australia — Population: 27.6 million`, `Donald Trump: ...`, and a ranked list
  of fifteen. Also over HTTP through `/api/ask`.
- **49 pytest tests pass** (38 before, 11 added), `black` clean, `pyright
  --pythonpath ./.venv/bin/python` reports 0 errors on `tiers.py`, `world.py`
  and `tests/test_tiers.py`.
- The false positive that the loose matching introduced — *"what is the meaning
  of life"* reaching a company called Orange Life Insurance — is fixed and has
  its own test.

### Not verified

- Only the `rules` tier was exercised. Nothing in this change touches the model
  tiers, but `prefer_rules` now yields to a solver more often, so a model tier
  question that happens to name a held subject will be answered by arithmetic
  where it previously went to Jan. That is the documented intent of
  `prefer_rules`, but nobody has watched it happen on a real model tier call.
- Ranking reads `prominence` from the index, and **no index row currently
  carries one** — every ranking today falls back to how much is held. The
  wording says so, but the prominence path itself is untested against real data.

---

## Verified — actually run, with the numbers observed

- **A real sweep, end to end, on the live library.** Six subjects, ~20 seconds,
  all three sources answering: 91 days of pageviews each, plus Hacker News and
  Lemmy. 614 readings stored across 3 sources. Nothing stubbed.
- **A real breakout, found by arithmetic alone.** Yoweri Museveni's pageviews at
  **2,000 on 2026-09-10 against a usual 1,131 — 6.8 sigma** above his own
  baseline. Photographed in the interface with its sparkline.
- **The rules tier answers with no model**, checked live against the running
  backend with Jan up — all three solvers returned `used_model: false`:
  - *"what is moving right now?"* → the Museveni breakout
  - *"how many subjects do you have?"* → "1212 subjects in Dossier's library, 6
    of them with signal series here, across 3 sources and 614 readings"
  - *"tell me about Moldova"* → "77 sources, 153 dated events", plus its series
  - *"should I move to another country?"* → refused plainly, did not escalate
- **Data really is on AN3.** `/run/media/ejb/AN3/ForesightData`, 121.9 GB free,
  `on_usb: true`. Dossier's 1,212 subjects read from disk beside it.
- **35 tests pass**, no network and no model. `black` clean. `pyright
  --pythonpath ./.venv/bin/python` **0 errors**.
- **Photographed in a real browser** (headless Chrome through the Flatpak, with
  `--virtual-time-budget` to get past the async boot): the Ask tab with its tier
  picker, and the Findings tab with the real Museveni card.

### Three bugs the tests and the screenshots caught

- **"country" contains "count".** Solver matching was a plain substring check,
  so *"should I move to another country?"* was routed to the coverage solver and
  answered with a confident, irrelevant library count. Now whole-word regex.
  This is the failure mode to watch for as more solvers are added.
- **A flat baseline made trivial moves look like emergencies.** With MAD at zero
  the first floor tried was `median * 0.15`, which made 4 → 9 a five-sigma
  event. Replaced with the square root of the level (counting noise). A floor
  proportional to the median was wrong the other way — it made a collapse from
  500 to 5 read as only two sigma. Both cases now have tests.
- **Every view rendered at once.** `shared/forge.css` supplies cards, buttons
  and the palette but **not** `.view`/`.view.on`, `.topbar`, `.pill` or `.hint`
  — Dossier defines those in its own `app.css` and this app had not. Caught by
  the first screenshot, not by any test. Worth knowing for the next new app.

### The slugify quirk, deliberately reproduced

`store.slugify` matches Dossier's exactly, including that NFKD does not
decompose `ł` — so `Lech Wałęsa` really does become `lech-wa-esa` in both. The
test asserts Dossier's actual output, checked by running it. Matching the quirk
matters more than fixing it: the two stores must line up.

---

