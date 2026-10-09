# Foresight — manifest

_Written 2026-09-11 for a reader with no conversation history. The
machine-readable version of this is the `manifest` block in `forge_app.json`;
the architecture is in `README.md` and the state of play in `WIP.md`._

## What this is

The analysis and planning layer above Dossier, served as a Forge tab on **port
8438** (`order` 11).

**Dossier settles what is true. Foresight works out what it means.** Dossier
holds 1,212 sourced subjects and will not let a model state a claim without a
source sentence behind it. Foresight measures the *attention and argument*
around those subjects, finds where one departs from its own baseline, and
answers questions about it.

The division of labour is enforced, not merely intended: **nothing here opens a
Dossier file for writing.** The only action Foresight can take against Dossier
is asking it to research a subject, and that goes through Dossier's own HTTP
API so its queue and its accumulate-never-duplicate merge rules stay in charge.
That is what keeps the factual record something you can trust has not been
quietly edited by a planner.

## The idea that shapes everything: rules are a tier

Asked which model to use, the user asked instead for maths to be an option:
*"make it so that math and rules can also be a tier option that doesnt use a
lllm to figure stuff out."*

So `rules` sits beside the model tiers as a first-class way of answering, not a
fallback:

| tier | what it is | model | thinking |
|---|---|---|---|
| `rules` | arithmetic and lookups over what is stored | **none** | — |
| `chat` | instant, conversational; the study companion | Qwen3.5-2B | off |
| `analyse` | summarising and judgement | Qwen3.5-4B | off |
| `think` | scenarios and plans, minutes allowed | a 35B-A3B MoE | **on** |

Two properties follow, and both are tested:

- **The app works with Jan switched off.** Signals, findings and every rules
  answer need no model server at all.
- **Every answer reports which tier produced it** (`used_model` in the API, a
  coloured badge in the interface). `tests/test_tiers.py` fails if the rules
  tier so much as touches Jan — a "rules" answer that quietly called a model
  would be the worst outcome here, looking cheap and deterministic while being
  neither.

`prefer_rules` (on by default) lets a solver answer even when a model tier was
selected, and says so. The cheapest correct answer wins.

### Why `think` turns thinking on

Dossier forces `enable_thinking: false` on every call, for a measured reason:
Qwen3.5 is a hybrid reasoning model and otherwise spends its whole budget
narrating, returning an empty `content` field — 16.8 s and no answer, against
0.4 s and "Yes" with it off.

Foresight keeps that for `chat` and `analyse` and **inverts it for `think`**,
where a long chain of thought is the product rather than waste. The user asked
for something that would "think on this dedicated task fro ages", so that tier
gets an 8,000-token budget and a thirty-minute timeout, and its reasoning is
kept and shown in the interface, folded away.

This is also why the tier prefers a **mixture-of-experts** model. An MoE
activates a fraction of its parameters per token — 3B of 35B here — so a long
reasoning chain is affordable on a 12-core CPU. A dense model of the same
nominal size produces the same thinking far too slowly to be usable.

## The three registries

Discovered, not declared. Adding to any of them is one new file.

**`signals/`** — where attention and feeling are read. A signal is *not* a fact;
it is a measurement, and measurements are noisy, gameable and often meaningless
alone. Every source must therefore declare a `caveat`, and the interface prints
it beside the number. A test fails if one is missing.

| source | measures | unit |
|---|---|---|
| `pageviews.py` | Wikipedia daily article views | views a day |
| `hn.py` | Hacker News stories, points, comments | stories a day |
| `lemmy.py` | Lemmy posts, scores, comments | posts a day |

**`analysis/`** — what turns signals into something worth reading. `trend.py`
finds where a subject departs from **its own** baseline, which is a better
question than "is this number big": Trump's pageviews are always enormous, so
the interesting day is the one where they are enormous *for him*.

**Solvers** (in `tiers.py`) — the rules tier's repertoire: `movers`, `coverage`,
`subject`. Declared rather than discovered, because each is a named capability
the interface offers as a button.

## Data

`/run/media/ejb/AN3/ForesightData/`, a **sibling** of `DossierData` rather than
a tenant of it, falling back to `~/ForesightData-local/` when the drive is out.
Everything information-based lives there by the user's instruction. One file
per subject per source holding a dated list, so a sweep rewrites one small file
and a corrupt file costs one series instead of the library.

Readings **merge by date**: re-running a sweep the same day corrects that day's
figure rather than appending a second one.

## What is verified

- A real sweep: six subjects, ~20 s, 614 readings from all three sources live.
- A real finding, by arithmetic alone: Yoweri Museveni's pageviews at 2,000 on
  2026-09-10 against a usual 1,131 — **6.8 sigma** above his own baseline.
- Every rules solver answered live with `used_model: false`.
- 35 tests, no network and no model; `black` clean; `pyright` 0 errors.
- Photographed in a real browser; Forge discovered the app with **no edit to
  `forge.py`**.

## Improvements — what to build next, and why

Stage 1 of four is built. The rest, in the order they are worth doing:

### 1. Scenarios, and a forecast ledger to keep them honest

The `think` tier is wired but nothing generates scenarios yet. When it does,
each branch must emit **dated, falsifiable indicators** — not "tensions may
rise" but "pageviews for X exceed N before 2026-12-01".

The ledger is the half that makes this learn rather than opine: when a date
passes, the app scores its own prediction against what the signals actually
did, and keeps the record. Over months that is a real calibration curve — which
kinds of scenario are worth trusting and which are not. Without it, a planner
is just a confident voice.

### 2. Exposure — the thing that turns anxiety into agency

Foresight knows the world; it does not know where the user sits in it. Given
their country, citizenship, field of study, industry, currency and commitments,
every world signal can be filtered through one question: **does this change
anything for me?** Most people follow geopolitics that will never touch them
while missing the two or three things that will. This is the highest-value
addition in this list.

### 3. Embedding retrieval

`sentence-transformer-mini` is already in Jan (44 MB, on disk — reuse it rather
than downloading another). `world.context_for()` is name matching until then.
Retrieval rather than a vast context window is the right answer on a machine
with no swap, because the KV cache is what eats memory.

### 4. The agent loop

A tool registry where each tool declares `reversible`. The user chose the
policy explicitly: **reversible tools run free** (queue research, fetch a
signal, write a note or scenario, re-rank priorities, schedule re-checks);
**irreversible ones wait for one click** (delete or overwrite, shell, anything
leaving the machine). Full audit log either way, a kill switch, and an
automatic snapshot of `DossierData` before any destructive tool runs.

### 5. The personal half

The user considers this as important as the world half, not an extra: a profile
(job, income, the people they know, how they write and talk), named folders,
browser history, schedule and tasks, and their university portal. Then the
study companion on the `chat` tier, and job/course/opportunity finding.

Credentials are entered **in the app** and stored `0600`, never pasted into a
chat transcript.

### 6. Sentiment

The forum sources currently gather volume and engagement, not feeling. Lexicon
scoring first, with a model only on the ambiguous band — the same shape as
Dossier's triage, which calls a model only for documents scoring 0.28–0.62.

### 7. Smaller, known items

- **Reddit** returns 403 without OAuth. `SignalSpec.needs_credentials` already
  exists and excludes such a source from automatic sweeps; it needs a free API
  app registering and a credentials field.
- **Job-posting trends by skill** would be a signal source like any other, and
  is the concrete way to answer "is what I am studying still being bought".
- **`llm.py` duplicates ~100 lines of Dossier's.** The tier semantics genuinely
  differ but the Jan plumbing and JSON salvage do not. The right fix is
  `~/Forge/shared/py/`, done deliberately rather than as a drive-by refactor of
  a verified app.
- **Hacker News is near-silent on world politics** — four of the first six
  subjects returned zero stories. It is excellent on technology and the
  companies around it. This is on its caveat, not a bug to hunt.

## Gotchas for whoever works on this next

- `shared/forge.css` supplies cards, buttons and the palette but **not**
  `.view`/`.view.on`, `.topbar`, `.pill` or `.hint`. Without them every view
  renders stacked on one page. Dossier defines them in its own `app.css`; so
  does this app now.
- Solver keyword matching is **whole-word**. As a substring check, "should I
  move to another country?" matched the coverage solver, because "country"
  contains "count", and answered with a confident irrelevant number.
- `store.slugify` reproduces Dossier's exactly, **including** that NFKD does not
  decompose `ł`, so `Lech Wałęsa` becomes `lech-wa-esa` in both. Matching the
  quirk matters more than fixing it, or the two stores stop lining up.
- A series needs ~10 readings before any claim is made about it. Pageviews
  supply 91 on the first sweep; HN and Lemmy take weeks of sweeps to build a
  baseline.
