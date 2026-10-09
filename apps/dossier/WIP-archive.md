# dossier WIP archive

Sections moved verbatim from `WIP.md` on 2026-10-07 (overhaul helper-5) to keep the live WIP short. Nothing was rewritten or deleted; original order kept. The full pre-move file is in `~/Forge/backups/2026-10-07-overhaul/wip/dossier-WIP.md`.

## Session of 2026-09-14 (later) — the "get new info, keep old data" buttons

The user: *"a button to keep old data but the button will get all the new info
that you just added"*.

- **Per dossier: Get new info** beside Update. `POST /api/subject/{slug}/new-info`
  → `enrich.start(slugs=[slug], refresh_articles=True)`; 404 for a subject not
  held, 409 while a pass is running. The page polls `/api/history`, reloads the
  same tab, and shows "Added N news items … Everything already held was kept."
- **Library-wide:** the Watch card is now titled *Get all the new info*, its
  button *Get new info for every subject*, and the hint states that old data is
  kept.
- `enrich.run()` gained `slugs` and `refresh_articles`; a subject with no
  Wikipedia article is now logged as skipped instead of passing silently.

### Verified — actually run

- **253 tests pass** (5 new in `tests/test_new_info.py`: only the named subject
  changes, an event already held survives, the article is refreshed only when
  asked, and the route's 200 / 409 / 404). `black`, `pyright` 0 errors,
  `node --check` clean.
- **Live, on a scratch backend** with the data from the session below: Get new
  info on Australia kept all **411** stored events (244 news, 114 indicators,
  36 projections, 16 headlines, 1 founding) - same count and kinds before and
  after, no duplicates - and refreshed the article.
- Screenshots: the button in the dossier header, and the renamed Watch card
  showing the run's log.

### Not verified

- The button has not been pressed against the real library (AN3 unplugged).

---

## Session of 2026-09-14 — five years of news, and the whole article

The user: *"i want dossier to get information on everyone and everything, the
information you coded it for isn't really enough, it just does timelines, i want
more info ... past year and 5 year of news"*. README section 6e is the design;
this is what was checked.

### Built

- `research/news_archive.py` + `sources/news_archive.py` — Wikipedia's Current
  Events portal, sixty month pages shared library-wide, matched to a subject by
  its article title and redirects. Filed `kind: news`, `confidence: reported`,
  with outlet citations.
- `sources/wikipedia.py` keeps the whole article as sections → `article.json`.
- Pages **In depth** (`profile`) and **News** (`news`), added to all seven
  entity types right after Overview. Two new block kinds in `app.js`:
  `article`, `news`.
- `enrich.py` + Watch tab card **Fill in history** + `GET/POST /api/history`,
  `POST /api/history/stop`.
- `dossier.add_events()` — merge events/article into a held subject without the
  per-subject reindex.
- Overview's timeline excludes news; `timeline_block` past its limit now keeps
  the **newest** entries (it kept the oldest).

### Verified — actually run

- **248 tests pass** (226 before, 22 new in `tests/test_news_archive.py`);
  `black` run; `pyright` 0 errors on every touched file.
- **Parser against a real month** (`Portal:Current events/March 2022`, 725 KB):
  709 events in 0.18 s, 698 with subject links, 646 with a topic chain.
- **Live research runs** into a scratch data root, real network, Jan off:
  - the whole archive: **61 months, 28,730 events, 16 MB**, downloaded once
    during the first subject (that subject took 150 s; the next took 12.7 s);
  - *Volodymyr Zelenskyy*: 61 redirect names, **159 archive items** (2021: 5,
    2022: 55, 2023: 20, 2024: 36, 2025: 21, 2026: 22), newest dated the day
    before the run and citing Reuters; article 34 sections, 12,823 words;
  - *Australia*: **244 archive items**, 35–57 a year; article 32 sections,
    9,624 words.
- **Screenshots** from a scratch backend in headless Chrome: the News page
  (175 items with Google News, year chips, citation tags, topic chains), the
  In depth page with folding sections, and the Watch tab card reading
  "61 of 61 months held, 28,730 events".
- The relaunched real backend on 8437 serves `/api/history` and lists the new
  source and pages.

### Not verified

- **Fill in history has not run against the real library.** AN3 was unplugged
  all session, so the real 1,212-subject library was not reachable; it was
  exercised by its test only. Expect about one Wikipedia redirect request plus
  one article request per subject, so a 1,212-subject library is roughly
  20–40 minutes, most of it paced API calls.
- The archive's first download happens inside whichever research job runs
  first, holding a lock the other workers wait on. With four workers that is a
  two-to-three-minute stall once. Running Fill in history first avoids it.
- News page with 1,500 items (the cap) was not timed in the browser; groups are
  built only when opened, which is the mitigation.
- Portal items are editors' summaries. A subject linked under another article
  (a ministry instead of its minister) is missed; that is on the page's hint.

---

## Session of 2026-09-11 (later still) — the IMF, and the only source that reports the future

`sources/imf.py`. One new file and nothing else edited, which is what the source
registry is for. Free, no API key, and it was the one named in this manifest's
own improvement list.

### Why it is not just a second World Bank

The World Bank publishes what an economy **did**. The IMF's World Economic
Outlook publishes what its staff **expect** it to do, several years out, and
revises twice a year. That is a different kind of fact and it is stored as one:

- a year in the past → `kind: "indicator"`, `confidence: "verified"`
- the current year or later → `kind: "projection"`, `confidence: "reported"`,
  the title says *(IMF projection)* and the detail says *"a projection by IMF
  staff, not an observed figure"*

**The current year counts as a projection.** The year is not over, so the figure
has not been observed; the WEO publishes it as a staff estimate. Storing it as a
measurement would be wrong by exactly the margin this source exists to keep
visible. The summary document handed to a model quotes only observed figures, so
a forecast can never be read back as a fact.

Six series: real GDP growth, inflation, unemployment, government balance,
government debt and the current account, from 2015.

### Verified — actually run

- **102 figures for Australia** against the live API, 36 of them projections,
  newest measured 2025 and first projection 2026.
- The API has a quirk worth knowing: asking for one country answers with
  **every country in the world**, so the filtering is done in the adapter. There
  is a test for it — Sudan's numbers must not end up in Australia's dossier.
- **8 new tests, 226 pass in total**, `black` clean, `pyright` reports 0 errors.

### Not verified

- No subject has been researched through the live pipeline with this source
  enabled — the adapter was driven directly. It is restricted to `country` and
  `political_system`, so the next country the queue reaches will exercise it.
- `countrycodes.iso3()` is shared with the World Bank adapter and resolves
  against the World Bank's country list. The IMF uses ISO3 too and every code
  tried matched, but the two lists are not guaranteed identical.

---

## Session of 2026-09-11 (later) — two dead controls, both silent

Both of these were invisible failures: nothing errored, nothing logged, the
feature was simply inert. Worth reading before adding anything to the frontend.

### The Full screen button did nothing, and it was not Dossier's fault

`static/app.js` guarded the wiring with `if (window.ForgeChrome)`. That guard
was **always false**. `ForgeChrome` was declared as a top-level `const` in
`shared/forge.js`, and a top-level `const` in a classic script goes into the
global *lexical* environment, never onto `window`. The button was never bound
to anything.

The helper is now `shared/forge_chrome.js`, which assigns `window.ForgeChrome`
and wires the `go-fullscreen` button, the `f` key and Escape by itself the
moment it loads. Dossier's `app.js` has nothing to do; the script tag is the
whole integration. It also takes real fullscreen now, and `forge.py` takes the
GTK window with it.

**Verified:** the button was confirmed present and bound in a DOM dump of the
running app, and 28 checks covering the helper pass in headless Chrome
(`~/Forge/tests/browser/run.sh`).

### The mind-map labels were black on black

`app.css` drew them with `fill: var(--fg)`. Nothing in Forge has ever defined
`--fg`. An unresolved `var()` with **no fallback** makes the whole declaration
invalid, so `fill` reverted to its initial value — black — on the near-black
graph canvas.

They are now `var(--text)` with a background-coloured halo painted behind the
glyphs (`paint-order: stroke fill`), so a label stays readable where it crosses
an edge or another label. Outside nodes are dimmer but legible; the centre node
is green and bold.

**Verified:** screenshotted at `#/links/angela-merkel` in the running app — 90
nodes, all labels readable. `~/Forge/tests/test_css_tokens.py` now scans every
app stylesheet for `var()` references to tokens nothing defines, and was
confirmed to fail when this bug is put back.

---

## Session of 2026-09-11 — arcs, a watcher, and a second indicator publisher

The user asked for improvements, "in separate tabs where it seems better". Three
of the four items in *Asked for, not built yet* below are now built. The fourth,
seat-share bars, turned out to be **already built and rendering** — `app.js` has
a `seats` block case drawing the bar, the majority marker and the other chambers
beneath — so it was left alone rather than rebuilt.

### Verified — actually run, with the numbers observed

- **Arcs between countries, on the real library.** `research/arcs.py` built
  **69 arcs in 0.01 s** from the 1,212 subjects held, merging correctly:
  Finland–Soviet Union is one line carrying **4** wars. Photographed in a real
  browser: **51 drawn, 18 skipped** because the map has no border for a
  historical state like the Soviet Union. Hovering names the dossiers behind an
  arc; clicking opens one. **8 tests.**
- **The honesty rule, tested.** Wikidata's participant list records no *sides*,
  so two participants are never joined to each other — a conflict joins each
  participant to where it was fought, and a conflict with no recorded location
  draws nothing. There is a test that fails if that changes.
- **The watcher refuses to trample the user, on real state.** Asked to sweep
  against the live library it answered *"waiting: the First run queue is still
  working"* and queued nothing. **13 tests** cover the three refusals — a pause,
  a busy queue, the memory guard — plus the rule that a deferred sweep is not
  recorded as having happened, so the clock does not restart and the refresh is
  retried rather than skipped. Photographed: the stalest subjects and the most
  recently refreshed both list real names.
- **Our World in Data, live.** **21 dated figures for Germany in 0.9 s** across
  all nine indicators. Every slug and column was checked against the live
  endpoint first; `literacy-rate`, `corruption-perception-index` and
  `primary-energy-consumption-per-capita` returned nothing or 404 and were
  dropped rather than left in to fail quietly. **15 tests**, no network.
- **End to end, for real, into the live library.** A quick pass on Germany
  merged in **18 s**: sources **21 → 27**, timeline **42 → 68**, 21 OWID figures
  stored, **nothing lost**. The Society & development tab was then photographed
  showing all 21, each linking to the chart it came from.
- **The World Bank source still works after being refactored** onto the shared
  country resolver: 25 dated figures for Germany in 1.4 s, checked live.
- **218 tests pass**, 36 of them new. `black` applied; `pyright
  --pythonpath ./.venv/bin/python` reports **0 errors** — it caught two real
  ones in `arcs.py`, where a starred tuple unpack made a dict key an
  indeterminate size.

### How to photograph this app, which earlier sessions could not

Headless Chrome through the Flatpak works, and the missing piece was never the
browser — it was the wait. This app boots asynchronously, so a capture at the
load event gets an empty page. `--virtual-time-budget` is what gets past it:

```
flatpak run --share=network --filesystem=<dir> \
  --command=/app/extra/google-chrome com.google.Chrome \
  --headless=new --disable-gpu --no-sandbox --window-size=1600,1050 \
  --virtual-time-budget=15000 --screenshot=<dir>/shot.png \
  "http://127.0.0.1:8437/#/subject/germany/society"
```

`grim` fails (GNOME has no wlr-screencopy) and the GNOME D-Bus screenshot is
refused, so this is the route. Dossier tabs now have their own URLs
(`#/subject/<slug>/<page>`), which is what makes a specific tab photographable.

### Not verified

- **No sweep has ever completed.** The watcher is off by default and the
  existing *First run* queue still has jobs waiting, so it has correctly
  refused every time. The deferral path is verified; the path where it actually
  queues and the jobs run is covered only by tests against a stub queue.
- **Alliance arcs draw nothing yet** — see below.
- The arc hover and click were read out of the code and photographed at rest;
  nobody has moved a mouse over one.

### The one thing worth redoing the library for now

**Alliance membership was never collected.** The 199 held alliances carry only
`ideology` in their relations, because `RELATIONS` in `sources/properties.py`
had no entry for Wikidata's *Has part*. That is now fixed — `Has part`,
`Part of` and `Parent organisation` are in the table — but like every previous
widening it only applies to subjects researched *after* it landed. Alliance arcs
are built, tested and will draw as soon as the data exists; until then the map
shows conflict arcs only. A queue with *redo subjects I already hold* ticked,
seeded with the alliances recipe, is what fills them in.

The same applies to OWID: only Germany has its figures so far, because it was
the end-to-end check. The other 211 countries have World Bank figures only.

---

## Verified — actually run, with the numbers observed

- **Pictures, on the real drive.** Six found for Angela Merkel, downloaded to
  `subjects/angela-merkel/images/` (902KB across five portraits and a
  signature), and a second run correctly reported all six **skipped**. Serving
  checked over HTTP (200, `image/jpeg`); a path-traversal attempt returned 404.
  Capped at two per kind afterwards — five portraits of one person is most of a
  megabyte for nothing.
- **Speech, for real.** A **3 minute 41 second** mp3 tour of Angela Merkel
  (2.6MB) rendered in **74 seconds** of CPU, and a 4.7s spoken answer to "What
  offices did she hold?" — *"She served as Chancellor of Germany from 2005 to
  2021 [13]"* — with the `[13]` present in the transcript and absent from the
  audio. Nothing was installed: it runs NovelForge's Piper against the voices
  already in `~/NovelMakerData/tts_voices/`.
- **107 Wikidata properties, every code checked.** One query against the live
  endpoint proved seven of my additions were fabricated — including six I had
  invented by suffixing a letter to dodge a dict key collision. They were
  removed; the 107 that remain all resolve.
- **The library says what places a subject.** After a reindex of all 1,080,
  Angela Merkel reads *Federal Chancellor of Germany · Christian Democratic
  Union · Germany*. 496 of 1,080 carry an office.
- **182 tests pass**, 23 of them new. `black` clean, `pyright` **0 errors**.

**Not verified:** no human has seen any of the new interface — the portrait
beside a dossier name, the placing line in the library, name links inside
claims, the audio player, the mind map or the Queues card. The Chrome extension
is not set up here and headless Firefox captures at the load event, before this
app's async boot renders anything. Everything behind the interface is checked
over HTTP against the real library.

**Why the library is worth redoing now.** Pictures, the wider property table and
the 38-kind relation table all only apply to subjects researched *after* this
session, and about 869 of the 1,080 held predate it. That is why the graph has
1,765 edges rather than several times that, and why only 496 subjects show an
office. New queue → tick *redo subjects I already hold* → seed the same recipes
→ then a *pictures each* pass over the same list.

- **The connection graph, on the real library.** 2,218 nodes (1,080 with a
  dossier, 1,138 named by someone's record but not researched), 1,765 edges,
  built from disk in **0.03s**. The live API answered *how are Trump and Putin
  linked* in four hops — independent politician, Alexander Lukashenka, the
  Communist Party of the Soviet Union — each hop naming the dossier that
  recorded it. No model is called anywhere in this path.
- **The mind map's layout maths.** Run in node against a real 60-node
  neighbourhood: **21ms**, no NaN coordinates, centre node pinned, closest pair
  48.8px apart. That test found a real bug — the layout spread 679×776 into a
  700×520 box, so the map started partly off-screen. Fit-to-view was added and
  re-checked: all 60 nodes now land inside the canvas.
- **Relations are declarative and 38 kinds wide**, up from four named inline in
  `sources/wikidata.py`. `properties.edges_from()` is a pure function with its
  own tests, including the case where one party arrives under both `Party` and
  `Member of` and must produce a single edge.
- **155 tests pass**, 16 of them new for the graph. `black` clean, `pyright`
  **0 errors** across every file touched this session.

**Not verified:** nobody has looked at the mind map or the Queues card in a real
browser. The Chrome extension is not set up here, and headless Firefox captures
at the load event — before this app's async boot renders anything — so neither
could be photographed. The layout maths, the API and every element id are
checked; the drawing itself is not.

**The one thing that is now worth redoing the library for:** the wider relations
table only applies to subjects researched *after* it landed. The ~869 already
done still carry the thin four kinds, which is why the graph has 1,765 edges
rather than several times that. Make a queue, tick *redo subjects I already
hold*, seed the same recipes into it. The merge accumulates, so nothing already
held can be lost.

- **Several saved queues, migrated off the real file.** The live
  `queue.json` (1,575 jobs) was migrated on a copy first: all 1,575 preserved,
  ids and order identical, the only change being the 4 in-flight jobs reset
  `running` -> `queued` by design. The live backend was then restarted and did
  the same to the real file, keeping `queue.json.v1-backup` beside it.
- **Work already held is skipped, on real data.** "Angela Merkel" queued into a
  fresh queue with redo off was marked `skipped — already held (deep pass)`
  rather than researched again. A deep dive on a quick-held subject still runs.
- **A pause survives a shutdown.** Written to the queue record, read back after
  a reload. Nothing auto-starts when the app opens, so a paused queue is still
  paused the next morning.
- **The memory guard no longer clears a pause the user set.** Its hold is a
  separate in-memory flag; the user's pause is the saved one.
- **139 tests pass** (`.venv/bin/python -m pytest tests/ -q`), about 22 of them
  new for the above. `black` clean. `pyright` shows one error and it is
  pre-existing — confirmed by running it against the pre-change files.

**Not verified:** nobody has looked at the new Queues card in a real browser.
Headless Firefox screenshots at the load event, before this app's async boot
renders anything, so the card could not be photographed; every element id the
new JavaScript reaches for was cross-checked against `index.html` instead.
F11 fullscreen and clicking a source link both need a human in the Forge window.

- **A quick pass, end to end, on a real subject.** Angela Merkel: **56 seconds**,
  33 documents from 6 sources, 41 dated timeline entries, 35 quotes (30 with a
  citation). Repeated after tuning; the first version of the same run took 667
  seconds.
- **Accumulation.** Saving the same research result twice added 0 sources, 0
  timeline entries, 0 quotes, and lost nothing. Proven on real data and again in
  `tests/test_merge.py` with synthetic data.
- **89 tests pass** (`.venv/bin/python -m pytest tests/ -q`), no network, no
  model. They cover URL canonicalisation, SimHash duplicate collapse, relevance
  scoring including the namesake penalty, the corroboration tiers, the merge
  rules, registry completeness, and all three citation gates.
  Several caught real bugs:
  - SimHash put three year-variants of one wire story in three clusters. It is
    now a prefilter only; Jaccard makes the decision.
  - "890,000 in 2015" vs "1,200,000 in 2015" was not flagged as a conflict
    because the two spans shared a year.
  - The fix for that then over-fired: reading the finished deep dive by hand
    showed a claim marked `disputed` because one span mentioned a year and
    another a duration. Numeric conflict now compares **like with like** — a
    figure only contradicts another figure of the same unit ("16 years" against
    "18 years"), never a year against a duration.
  - SEC full-text search returns every filing that *mentions* a name, and forty
    Dean Witter fund filings had been recorded as verified events in Merkel's
    life. Only a filing by the subject itself now becomes a timeline entry; the
    rest stay as documents and are scored on relevance like anything else.
  - **The library index was wiped once, for real.** While the USB drive was
    busy being synced, a `subject.json` read failed transiently; `reindex`
    treated the subject as absent and wrote an empty index over a good one. No
    research was lost — every data file was intact and a rebuild restored it —
    but the whole library looked empty. `reindex` now carries a subject's
    previous index row forward when its file will not parse, refuses to replace
    a good index with nothing when subject directories exist, and `library()`
    rebuilds rather than believing an empty index. Three tests cover it.
- **`black` applied; `pyright --pythonpath ./.venv/bin/python` reports 0 errors.**
- **Every HTTP route returns 200**, and the UI was screenshotted in headless
  Chrome: the world map renders, Germany shades as the one country held, and the
  header shows the live queue, AN3 storage and Jan's three tiers.
- **A 47-subject bulk run, start to finish, zero failures.** Every current
  head of government, seeded from Wikidata and ordered most-covered-first:
  **47 subjects in ~48 minutes**, fastest 26 s, median 52 s, slowest 251 s.
  It added **606 sources and 1,163 dated events**. The library now holds 48
  subjects across **54 countries** — 675 sources, 1,260 events, 546 quotes.
- **The on-disk queue survives a restart.** The backend was stopped and started
  while holding 48 finished jobs; all of them, and all 48 subjects, came back.
- **The world briefing is real and cited.** Built over 625 dated events across
  45 countries; every sentence carries its event markers and **zero uncited
  sentences had to be dropped**. The map shades 45 of those countries.
- **Seat share works and picks the right chamber.** Verified live: Labour
  198/650 in the Commons (30.5%), Conservatives 349/650 (53.7%, a majority),
  CDU 164/630 in the Bundestag (26.0%), Republicans 220/435 in the US House
  (50.6%) with the Senate listed beneath. Getting there took three corrections,
  each caught by looking at the answer rather than the code:
  Wikidata's *preferred* statement for the CDU pointed at the Bundesrat (17 of
  69); ranking chambers by size then picked the European Parliament (720) over
  the Bundestag; and doing the same for Britain picked the House of Lords (808)
  over the Commons (650). The rule is now: the party's **own country's** chamber
  first, **lower house** ahead of upper, then size. "House of commons" is
  recognised as a lower house by following `subclass of` one step.
- **Wikidata candidate picking uses `instance of`, not description text.**
  Searching "Labour Party (UK)" as a party returned the *1992 Labour Party
  leadership election*, and matching on words fails because that description
  contains "party" too. Candidates are now checked against the Q-numbers each
  entity type already declares, with a retry on the bare name when a list
  carries a disambiguator like "(UK)".
- **All eight sources reached live, no API keys**: Wikidata (API + SPARQL),
  Wikipedia, Wikiquote, DuckDuckGo Lite, Google News RSS, SEC EDGAR full-text,
  GDELT, World Bank (19 dated figures for Germany, verified).
- **The registry design held under a real test.** Adding the World Bank source
  and the economy page after the app was finished took exactly two new files
  plus one line in each of the two entity types that wanted the page. No change
  to the backend, the pipeline or the frontend.
- **Seed recipes return real lists**: 209 current heads of government, 249 live
  conflicts, 244 alliances — ranked by how many language Wikipedias carry the
  subject (Trump 334, down to 10 for minor figures).
- **Jan two-tier routing**, both models auto-detected. Its Local API Server was
  off at startup and pointed at `Qwen3_6-27B-Q4_K_M`, which is not on disk; it
  was enabled and repointed at Qwen3.5-4B, with the 2B second.
- **A full deep dive, start to finish.** Angela Merkel, **1253 seconds (21
  minutes)**: 209 documents gathered → 203 distinct stories, 50 borderline
  documents triaged (5 rejected as a different subject), 12 articles read into
  57 raw claims, merged to **47 claims — 4 verified, 43 reported**. Merged into
  the existing quick-pass dossier: +54 sources, +47 claims, +96 events, and
  nothing lost. The stored dossier now holds 69 sources, 47 claims, 97 timeline
  entries and 35 quotes.
- **The claims are good.** Spot-checked by hand: "She served as Chancellor of
  Germany from 2005 to 2021" carries **5 independent voices** (britannica,
  politicaldna, wikidata, wikipedia, zeit.de); every span checked was a real
  sentence from the cited article.

### Speed and scraping (the second pass over this)

Measured, not guessed — a quick pass was profiled before anything was changed.

**The scraping bug that mattered most.** `extract()` stripped page furniture by
matching class and id substrings, and Wikipedia puts a feature flag on its
`<html>` element called `vector-feature-main-menu-pinned-clientpref-1`. That
contains "menu", so the **root element was decomposed and every Wikipedia page
returned an empty document** — as did any site whose wrapper happened to contain
one of those words. Only 5 of 10 search results survived extraction. The
extractor now matches class tokens individually, never touches `html`/`body`/
`main`/`article`, refuses to drop any element holding more than a quarter of the
page's paragraphs, and picks the article container by scoring text density
rather than trusting a tag name. Wikipedia went from **0 to 25,680 words**, and
the keep rate from **5 of 10 to 10 of 10**, median 2,892 words each.

**Where the time went, and what fixed it:**

| | before | after |
|---|---|---|
| Web search + article fetch | 22.2s (5 docs) | **6.5s (10 docs)** |
| World Bank indicators | 9.1s | **2.3s** |
| One quick pass, alone | ~55s | **34.2s** |
| Bulk throughput | 69 subjects/hour | **157 subjects/hour** |
| Triage call (2B) | 1–2.6s | 0.24s on GPU — **reverted, see below** |
| 2B memory | 12.0 GB | 1.4 GB with the context fix alone |

Fetching is network-bound, so it was made concurrent: a shared process-wide
`Fetcher` with **per-domain** pacing (a per-domain lock, not a global one — the
first attempt held one lock across the sleep and serialised everything), source
adapters gathered in parallel, World Bank's nine indicator calls issued
together, Wikidata's label batches together, and the queue running four subjects
at once.

**Do not put both models on the iGPU — it corrupts generation.** The 2B had no
`n_gpu_layers` and `cpu_moe: true`, so it ran on the CPU. Moving it onto the
iGPU looked like the biggest win available: triage went from ~1.5s to **0.24s**
and its memory from 12 GB to 1.4 GB. It also **silently corrupted the 4B's
output**. With both models resident, the 4B began emitting garbage tokens
mid-string inside otherwise well-formed JSON — `midtermudemidterm`, `20чник`,
`闰月`, `"共建"`, `femaleautant` — which is exactly the failure that would poison
extracted claims without anyone noticing. The Iris Xe has no dedicated memory,
and Vulkan produced wrong results rather than failing. Putting the 2B back on
the CPU made output clean again on the first try (0 non-latin characters,
well-formed JSON). **This was found only because the daily brief came back
empty**; nothing else would have surfaced it. Deep dives run since are the ones
to re-check if anything looks odd.

**What did not work, recorded so it is not retried:** raising queue workers from
3 to 6 made no difference (90 vs 96/hour); concurrent LLM calls gave 0.94×;
disabling the prompt cache was 5.86s against 6.30s. Under load the binding
constraint is the shared iGPU, not the CPU — load average stayed **under 1.0 on
12 cores** throughout. More workers cannot fix that.

**A Jan configuration limit worth knowing:** Jan regenerates
`llamacpp/router.preset.ini` on every start, so edits to its `[*]` section do
not persist, and neither do values written into `llamacpp/settings.json`. Only
per-model `model.yml` keys survive — `ctx_size`, `n_gpu_layers`, `cpu_moe` and
`parallel` do; `cache_ram`, `threads` and `cont_batching` do not. The unbounded
prompt cache (`cache-ram = -1`) therefore cannot be fixed from configuration,
which is why the app sends `cache_prompt: false` on every request instead.

### The performance finding that matters most

`chat_template_kwargs: {"enable_thinking": false}` on every Jan call. Qwen3.5 is
a hybrid reasoning model and will otherwise spend its entire token budget in
`reasoning_content` and return an **empty** `content` field. Measured on this
machine: **16.8 s and no answer** with thinking on, **0.4 s and "Yes"** with it
off. If claim extraction ever starts returning nothing, check this first.

Two smaller wins: asking for a six-word anchor instead of an echoed sentence
took an article from 216 s to 115 s, and reading one document per story cluster
avoids paying twice for the same report.

---

