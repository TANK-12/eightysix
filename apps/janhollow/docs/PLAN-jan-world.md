# Plan: the Jan world, a living pixel town run by local models

A **multi-session** Forge game, third of three plans (after
`~/Forge/apps/crewroom/docs/PLAN-crew-room-2.md` and `~/Forge/docs/plans/PLAN-pixel-games-tab.md`). Start session 1 with:
*"start the Jan world from ~/Forge/apps/janhollow/docs/PLAN-jan-world.md"*.

## Status (kept current)

Session 1 (Foundation) landed on 2026-09-16: `apps/janhollow` on port 8448, in
the Pixel games group. The live source of truth for this game is now
`apps/janhollow/MANIFEST.json`, with `apps/janhollow/manifests/roadmap.json`
for what each future session should and should not do. Read those two before
this plan; this file stays as the record of what Emerson asked for.

## His words (2026-09-16), in order

> "i also wnat claude to build and run a whole world of haiku agents or 0.5 and
> 0.8 b modles fomr jan idk whateveris colest"

> "actulaly make it justa jan server run world with npcs and stuff"

> "im happy to have more than one moedl runnign ata itme as long as the outputs
> are fine"

> (on which world) "Watch and step in" and "Play as a character", then: "will
> probaly need to be a multi seesion thing as alwasy asi ask make sure there is
> a a realtime upto date manifets as you work for pasta nd futere things"

## Questions asked, answers verbatim

| Question | Options offered | Answer |
|---|---|---|
| Where should the Jan-run NPC world live? | New Forge app / Inside Emberfield / A room in Crew Room | "make ember fild part fo the pixel games tab and put this jan world as a new pixel game" |
| How hard may it lean on Jan and the laptop? | 0.8B one at a time / 2B for smarter NPCs / 0.8B chatter plus 4B narrator | "0.8B chatter plus 4B narrator" |
| Which world is coolest? | Watch and step in / Play as a character / Watch only | Both of the first two (quoted above) |

Haiku agents were considered and dropped by him in favour of Jan only.

## The idea

A pixel town that lives on its own, which you can also play in:

- **Watch**: NPCs with names, jobs, homes, daily schedules, memories and
  relationships go about their day and talk to each other. Every line is
  readable in speech bubbles and a town log.
- **Step in**: walk in as a visitor and talk to anyone by typing.
- **Play**: the narrator invents quests, rumours and events from what has been
  happening, and the town remembers what you did.

## Models (checked 2026-09-16)

| Role | Jan model id | Where it runs | Size |
|---|---|---|---|
| Chatter (every NPC line) | `qwen35-0_8b-spectralquant-calib360-q4_k_m` (Qwen3.5-0.8B) | CPU: its `model.yml` has no `n_gpu_layers` | 416 MB |
| Narrator (events, quests, nightly memory summaries) | `Qwen3_5-4B-IQ4_XS` (Qwen3.5-4B) | iGPU: `n_gpu_layers: 40` | 3.0 GB |

- **Output quality is the condition he set.** Keep exactly one model on the
  iGPU (two there once produced garbage tokens). Validate every reply: parse
  the expected JSON, reject non-English runs and obvious junk, and keep a small
  log of rejected samples.
- **Jan is shared.** It listens on `http://127.0.0.1:1337/v1` (Arcade's pattern)
  as a router with `--models-max 2`, so loading both models can evict another
  app's model. Check `pgrep -a -x llama-server` before a run; if models are
  loaded that this game did not load, wait or ask. Never restart Jan.
- **Idle models leave memory.** Release them when the world is paused or the
  tab is closed.
- One request lane per model, queued: NPC lines take turns. Two concurrent Jan
  requests once froze the laptop (NovelForge's `janclient.py` lock). The
  narrator runs rarely: once per in-game day and on big events.
- Check whether Qwen3.5 thinking output needs turning off for short NPC lines
  before building on it.

## How it should be built

- A Forge app under `apps/<name>` (FastAPI, own `.venv`, next free port) with
  `"group": "pixel-games"` in its manifest and full screen built in.
- **Content is data**, discovered by scanning, never hardcoded lists:
  `~/ForgeGameData/<name>/npcs/*.json` (name, job, personality, home,
  schedule, starting relationships), `locations/`, `events/`, `quests/`
  templates. Adding an NPC is one file.
- **Art** in `~/ForgeArtData` as `<name>-*` packs, editable in Pixel Forge.
  `apps/crewroom/tools/make_art.py` already generates anime pixel people,
  furniture and tiles and can seed villagers.
- The simulation runs in the backend and saves small state (positions, the
  clock, relationships, capped memory logs) under the game's data folder.
  Disk is short, so cap and summarise logs.

## Sessions (seed of `manifests/roadmap.json`; extend it every session)

1. **Foundation**: app skeleton, pixel-games group membership, town map,
   NPCs from data walking their schedules with no LLM yet, save and load, and
   the manifest series set up.
2. **Chatter**: NPC-to-NPC conversations on the 0.8B lane, the quality guard,
   bubbles and a town log.
3. **Narrator**: daily events and rumours on the 4B, memories and
   relationships that change what NPCs say.
4. **Step in**: player avatar, typed conversations with any NPC.
5. **Play**: narrator-made quests, consequences and a town that reacts.
6. Backlog ideas: seasons and weather as palette swaps, festivals, Claude
   sessions from the Crew Room visiting town, NPC voices through Forge's TTS.

## Manifest, from the first hour

He asked for it explicitly: "make sure there is a realtime up to date manifest
as you work for past and future things". Mirror Emberfield:

- `MANIFEST.json`: the single entry point a fresh session reads first.
- `manifests/roadmap.json`: future sessions, each with a why, `do` and
  `explicitly_not`, marked independent or dependent. Grow it every session.
- `manifests/session-NN.json`: what that session intended, did, verified and
  got wrong, with questions and answers verbatim.
- Update them **as each feature lands**, and keep the ranked improvement list
  in both `MANIFEST.json` and the `manifest` block of `forge_app.json`.

## Asked at the start of session 1 (2026-09-16, session ejb-34), answers verbatim

These answers override anything above that disagrees (the "town"/"village"
wording above is now a space station).

| Question | Answer |
|---|---|
| The game's name | "Janhollow" |
| Setting | "Space station" |
| Keep living while the tab is closed? | "make it a setting and stuff for focuse closed and idel and summery of time skip it deppends ont eh world" |
| Which away modes may a world pick? | "Pause when unfocused, Keep running when closed, Idle when closed, Time-skip summary" (all four) |
| Default away mode for a new world | "Pause when unfocused" |
| Starting NPCs | "8 (Recommended)" |
| Day length | "40 min per day" (assumed: a per-world slider plus number field, default 40, since numeric settings get one) |
| Tone | "Cozy crew life" |
| How far may the narrator push events? | "Crew can come and go" (NPCs may transfer off; new ones arrive as generated NPC files) |
| Who is the player? | "New arrival (Recommended)" |
| Station layout | "Several decks with a lift" |
| Chatter amount | "Setting, default moderate (Recommended)" (about one conversation per minute) |
| How far this session goes | "As far as it goes" (after Crew Room 2 and the Pixel games tab, in the same session) |

So: `apps/janhollow`, data in `~/ForgeGameData/janhollow/`, art packs
`janhollow-*`. The away mode is a per-world setting with four values:
`pause_unfocused`, `run_closed` (chatter keeps using the 0.8B), `idle_closed`
(schedules move, no model), `time_skip` (nothing runs; on return fast-forward
and one narrator summary).
