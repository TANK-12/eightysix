# Desktop v2: critic and breaker report

date: 2026-10-07 · for: Claude (the session that picks up Desktop v2) · by: the critic helper

## What was tested

- Copies of the live shared files, taken at about 20:22. helper-6 was still editing `forge_particles.js`, `forge_widgets.js`, `forge_depth.js` and `forge_power.js` between 20:18 and 20:22, so line numbers below match that version.
- The copies were served over HTTP (`127.0.0.1:8763`) so that errors named their file and line. Over `file://`, errors from the shared scripts only show as "Script error."
- **Verified** means a headless Chrome check showed it (error capture plus frame counters, or a screenshot). **Reasoned** means it comes from reading the code and was not run.
- Nothing under `~/Forge` was edited apart from this report. No headless Chrome from this check was left running (count 0), and the test server was stopped.

Test kit, all in `/tmp/dv2/critic/`:

- `crit.html`: the showcase page with error capture. Add `min=1` to show every widget at its smallest registry size.
- `break.js`: the breaker suite. `brk.py` runs it.
- `shots.py`: takes the screenshots.
- `run2.json`: the latest results.
- Screenshots: `min_mat.png`, `min_glass.png`, `narrow_mat.png`, `narrow_glass.png`.

## Real bugs (ranked)

1. **Bars visualiser throws when narrow. Verified. Highest priority.**
   - Where: `forge_visual.js:107`, `STYLES.bars`.
   - Each bar's width is `(w*0.7)/64 - 3`. It goes negative under about 275px wide, so `roundRect`'s radius `Math.min(3, bw/2)` is negative and throws `RangeError`.
   - "bars" is the visualiser card's default style, and the card's smallest size is 2×2, which is about 230px. So a 2-column visualiser card stays blank and throws about once a second.
   - Seen on the min-size page in both looks: 4 errors in 3.5 s. Direct calls fail at 200px and 120px.
   - New in v2: the v1 code used a fixed radius of 3.
   - Fix: `bw = Math.max(1, …)` and radius `Math.max(0, Math.min(3, bw/2))`.

2. **Nothing writes the power tier. Verified by searching the tree.**
   - All three files read `theme.power_tier`: `forge_widgets.js:233`, `forge_particles.js:238` and `forge_depth.js:78`.
   - Nothing in the tree sets `power_tier` or sends the `forge-power` event, apart from the tests and `tools/desktop_bench.html`.
   - Also, `ForgePower.tier()` in `forge_power.js:73` returns text like `"reduced: GPU busy"` or `"paused: hidden"`. If the host copies that text in unchanged, the checks for exactly `"reduced"` or `"paused"` treat it as `"full"`.
   - Fix: split on the colon when reading it, and wire the host (hub or desktop) to set `power_tier` and send the event.
   - With the tier set by hand it worked (verified): reduced drew 30 frames a second, paused drew nothing, and after flipping it 400 times only one loop was running.

3. **Particles keep running with nothing to draw. Verified.**
   - With `particle_amount` 0 or below there are 0 particles, but the loop still runs at 60 frames a second (`running="1"`, the frame counter kept climbing).
   - Cause: the run check at `forge_particles.js:244` never looks at the particle count, because `showing()` always returns true.
   - Fix: also require `this.dots.length > 0` (or sparks).

4. **Low frame-rate settings slow the motion down. Reasoned, not measured.**
   - Where: `forge_particles.js:281`, which limits each frame's step to 3 normal frames.
   - Below about 20 frames a second the particles move slower than real time; at 5 frames a second they reach about a quarter of their speed. That breaks the "same speed at any frame rate" goal for battery settings.
   - Fix: allow a step up to the capped frame's length (about 1000/fps), and count only gaps longer than about 250 ms as a pause.

5. **Countdown accepts impossible dates and times. Verified.**
   - Where: `forge_widgets.js:1241`. The date check only looks at the format.
   - `2026-02-31` silently becomes Mar 3 and shows "218 days ago".
   - `2026-13-01` shows "NaN days" and "Invalid Date".
   - Time `25:99` shows "NaN days" and "Invalid Date · 25:99".
   - Time `9:5` is dropped without a word.
   - `0000-01-01` shows "740261 days ago".
   - Fix: reject the date if `isNaN(end)`, or if the year, month and day don't come back the same. Keep hours under 24 and minutes under 60.

6. **`particle_amount` that isn't a number crashes particle setup.**
   - `"abc"` throws "Invalid array length" in `apply()` (`forge_particles.js` around line 127). Verified.
   - A huge or infinite value would keep adding particles until the tab runs out of memory. Reasoned, not run.
   - Settings already limits the value to 0.25–2.5 (`forge_theme.py:784`), so this is low risk.
   - Fix: only accept a finite number, and cap it.

7. **Bad stats show through on the cards. Verified.**
   - Activity (`:1144`) prints values raw: `abc%`, `x%`, and decimals unrounded, e.g. `12.3456%`.
   - Battery shows `NaN%`, and `charging: "no"` counts as true, so it says "⚡ Charging" (`:1215`).
   - The older Disk and System "more" cards crash when `disks` isn't a list or has a `null` entry ("disks.map is not a function", "reading 'mount'").
   - Those cards also print "undefined GB free of undefined GB" and "x B/s".
   - These errors are hidden by `tick`'s try/catch, so the card just freezes.
   - Fix: turn values into numbers and round them before showing them, and skip anything that isn't valid.

## Held up fine (verified)

- Every particle kind (19 of them), with no errors.
- Every visualiser style except bars, at sizes from 1600×1000 down to 0×0, against these levels: no audio, all zeros, empty, 3 values long, NaN, too loud, and text.
- An unknown particle kind falls back to "soft".
- 300 rapid hide/show flips: 0 frames while hidden, 60 a second after, and only one loop running.
- A large gap between frames left no particle with a NaN position.
- Particle frame rates 0, 500, "abc", -3 and null all run uncapped at 60 with no errors; 1 and 5 are capped correctly.
- The visualiser card shows no errors with no audio (`null`) or all-zero audio.

## Looks (ranked)

1. **The Nebula visualiser card is mostly empty.** It's a small blob in the middle of the card, filling maybe 15% of it, and worse at 700px wide. The style is laid out for a whole screen and isn't scaled to the card's width.
2. **A new Network card shows stray dashes.**
   - The graph is drawn from the left over 60 fixed slots (`forge_widgets.js:891`), so two readings make a short "–" at the left edge for each line (visible in glass), above a big empty area.
   - Activity draws from the right; Network should do the same.
3. **The Spectrum style looks unfinished in the static shots** (`/tmp/dv2/show/wisps.png`, `galaxy_only.png`).
   - It's a smooth "mountain" shape with a curled hook at the left end, a hard cut at the right, and a flat reflected band underneath.
   - On the bars style the peak caps float as separate pairs of dashes ("— —") that read like debris.
   - The right side fades into the bright wallpaper stripe.
4. **Ring visualiser in glass at 700px:** the ring sits under the stacked cards, and its spokes poke through the gaps between them like a rendering glitch.
5. **Wisps up close** (`wisps_rt.png`): big muddy brown blurry discs that look like smudges on the lens, not glowing wisps. The comet tails are fine. Galaxy reads as a dotted ellipse, not spiral arms.
6. **Battery card at 2–3 columns:** "Effects ease off when it runs low" wraps to 3 lines, crammed against the ring. Shorten the text or hide it on narrow cards.
7. **Countdown at its smallest size** cuts the title off ("MATH1014 final examinat…"). At full width the big number sits left with the right half empty.
8. **Material cards let the full-screen visualiser show through** as muddy blobs, for example behind the alarm buttons.
9. **Small points:**
   - Activity's labels (about 11px) are tiny next to the values, and the flat white memory line looks like a border.
   - The Weather card at 2×2 shows "… —" placeholders (older card, not v2).
   - An unknown visualiser style quietly draws nothing; it should fall back to "bars".
