# Arcade ("Phosphor") — manifest

_Written 2026-09-07 for a reader with no conversation history. The machine-
readable version of this is the `manifest` block in `forge_app.json`._

## What this is

Thirteen small modules — **nine games and five generative experiments** — in one
cabinet, served as a Forge tab on **port 8433** (`order` 6). Everything visual
and playable lives in a single `static/index.html` using Canvas 2D and Web
Audio, with **no libraries**. The same file is also published as a claude.ai
Artifact, so the page runs with or without the backend.

The Python backend (`web_app.py`) exists only for the two things a browser tab
cannot do alone:

1. **Jan.** The LLM server is a different origin, so the page can't call it
   directly. `POST /api/jan/chat` proxies to `JAN_BASE_URL` (default
   `http://127.0.0.1:1337/v1`) and auto-detects whichever model Jan currently
   has loaded.
2. **Memory.** Hearsay's NPC state is persisted to `~/ForgeArcadeData/` so a
   reload doesn't wipe the case.

`GET /api/status` reports `{backend, jan, model}`; the page calls it once on
load and degrades gracefully if it 404s (Artifact) or Jan is off.

## The nine games

| Game | Verb | Notes |
|---|---|---|
| **Standing Wave** | steer & survive | Play field is a live cymatics simulation driven by the FFT of your MP3. Bright antinodes drain you; ride the dark nodal lines. **Needs a track.** |
| **Aphelion** | aim & release | Gravity slingshot. The predicted trajectory uses the same integrator the probe flies, and turns cyan when the shot will reach the beacon. |
| **Zero Beat** | tune | Match a target waveform harmonic by harmonic; the monitor tone detunes with your error, so a match is an audible unison. |
| **Hearsay** | question | Five crew, one wiped log, gossip that spreads between NPCs. **Uses Jan** for phrasing only — see the rule below. |
| **Escapement** | swing | One button: hold to catch the ring above, release at the top of the arc. A real pendulum constraint — the rope only pulls. |
| **Catenary** | swing, fairly | Escapement's sibling, built on one promise: **no course is ever impossible**. Rings are never further apart than `REACH`, and holding the rope reels it to `MINROPE`, so `MINROPE + REACH = 358 < 360 = GRAB` — the next ring is always inside the grab radius and the rope hands itself forward while you hold. Buffered grab, a drawn reach circle, three ropes instead of one life. |
| **Waveguide** | rotate | Rotate the amber mirrors so the beam lights every receiver. Splitters and walls are fixed scenery. |
| **Downbeat** | jump | One-button rhythm runner; the track is onset-analysed up front and the runner's position is driven straight off the audio clock, so you jump *on* the beat. **Needs a track.** |
| **Lanternfall** | drift & flare | Your light is your life and it burns down; sparks feed it. Shadow wisps hunt you and shy from a bright lantern, so a dim one is hunted. A flare (click/space) spends light to stun wisps in reach, and stunned wisps break into sparks, so flaring into a crowd pays for itself. Combo up to x9. Sparks and eyes show through the dark, so nothing is a surprise. Added 2026-09-27 (S12). |

## The five experiments

Nothing to win; each opens with a console of sliders and keeps running.

| Experiment | What it is |
|---|---|
| **Physarum** | Slime-mould transport networks. Thousands of agents sense the trail ahead and steer toward the strongest, then deposit. Sensor angle and reach decide veins vs spirals vs lace. Deposit rate rides the bass with a track loaded. |
| **Gray–Scott** | Reaction–diffusion. Feed and kill are the whole system; a thousandth either way changes the species. Paint with the pointer. |
| **Divergence** | An ensemble of double pendulums released a millionth of a radian apart. They agree for about ten seconds and then never again. |
| **Filament** | Divergence with the lid off. The same real physics — a planar chain of 2–4 links solved as a mass matrix and integrated with RK4 — but the ensemble's starting curve, the colour meaning, the trail and a kaleidoscope mirror are all controls. Drawn as the *curve* it is rather than as loose dots, with each segment faded by its own length, which is what keeps full chaos legible instead of grey. |
| **Waterfall** | Your track as a scrolling log-frequency spectrogram with a live waveform scope above it. **Needs a track.** |

## The rule that keeps Hearsay coherent

**The engine decides what an NPC says. Jan only decides how they say it.** The
case — culprit, motive, true locations, who saw whom, the keystone observation
that breaks the cover story — is generated deterministically in JavaScript.
When you ask a question the engine computes the *content* of the answer and
hands it to Jan as "convey exactly this, in your own voice." So a small local
model can ramble or go off-tone without corrupting the mystery, and the game is
fully winnable with Jan switched off.

## Fullscreen

Press **F** (or the **Full** button). Any non-menu screen posts
`postMessage({forge:"chrome",hidden:true})` so `hub/index.html` hides its
sidebar, and hands it back on the menu.

## Where data lives

`~/ForgeArcadeData/hearsay_save.json` — only Hearsay persists anything. Nothing
is written into the app folder.

## Dependencies

**Required:** fastapi, uvicorn, httpx. Nothing on the frontend — Canvas 2D +
Web Audio only, so there is nothing to pin or update.

## Running it standalone

```bash
cd /home/ejb/Forge/apps/arcade
FORGE_SHARED_DIR=/home/ejb/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8433
```

Then open <http://127.0.0.1:8433>. Jan must be running on port 1337 for
Hearsay's dialogue to come from the model rather than the fallback.

## API surface

`GET /api/status`; `POST /api/jan/chat`; `GET` / `POST` / `DELETE`
`/api/hearsay/save`; `GET /` serves the page.

## Forge theme (2026-09-27, S13)

Inside Forge, Arcade follows the hub's theme like the other apps. How:
`static/index.html` loads `/shared/forge_chrome.js` only when framed
(`window.parent !== window`), and that script applies the hub's
`{forge:"theme"}` message as Forge tokens on `<html>`. Arcade's own tokens
read those first and fall back to the phosphor palette: `--void` from
`--bg`, `--void-2`/`--void-3` from `--panel`/`--panel-2`, `--ink`/`--ink-soft`
from `--text`/`--muted`, `--amber` from `--accent` (only when Settings
unifies accents), `--red`/`--green` from `--bad`/`--good`. Arcade's old
`--panel` token is now `--card`. When themed, the menu canvas is cleared
instead of painted, the ambient pattern keeps only its glowing lines, and the
stage canvas has alpha (framed only), so the wallpaper glass shows. The games
keep their opaque phosphor ground and colours on purpose.

**Verified** in headless Chrome (a fake hub page on Arcade's own origin,
sending a purple theme): tokens applied, wallpaper shows through the menu,
standalone is identical to before (screenshot compared), Aphelion starts
framed and standalone with no page errors. The test server needs
`FORGE_SHARED_DIR` set, as forge.py sets it. **Not verified:** the real hub
in WebKitGTK (needs a Forge restart; Emerson's Forge was not touched).

## Known gaps (verified vs reasoned)

- **Not visually verified.** There is no screenshot capability in the agent
  sandbox and the Chrome extension is not connected, so the layout, feel and
  balance of every module are unconfirmed — Downbeat's jump / gravity constants
  in particular are reasoned, not playtested.
- Static checks that **do** pass: `tools/smoke.js` (every module, 3000 frames,
  random input), `tools/wg_sweep.js` (30,000 Waveguide boards over levels
  1–20, zero unsolvable, zero handed over already solved), JS syntax,
  element-id cross-check, registry-target resolution, backend endpoint
  round-trips.

## Other docs

`README.md` — the fuller design notes, including how a module is registered
(one registry entry with `begin / frame / pointer / key / hud` callbacks), how
`setPhase()` gates every screen and all audio, and the load-bearing invariant
in Waveguide's level generator (build, then verify by tracing the intended
solution before placing decoys and walls).
