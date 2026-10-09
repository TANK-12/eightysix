# H6 Desktop v2 report (helper-6, Kana)
date: 2026-10-07 · for: both

**Checks passed.** tests/test_desktop_v2.py and the related hub/desktop tests:
69 passed, 1 skipped; key tests (test_hub_keys, test_hub_fx, test_restart,
run with apps/dossier/.venv which has gi): 20 passed; tests/browser/run.sh:
1000 PASS. Its failures: hub_fx's style count (fixed, 7 -> 9). hub_level and
hub_music_skip fail because off-screen WebKit cannot get a GL context here;
that is the environment, not these files. black and pyright: 0 errors on the
Python I touched.

Full write-up (what is new, numbers, what is left):
`docs/library/desktop/2026-10-07-desktop-v2.md`. It went there because
docs/library/power is claimed by helper-4.

## Design decision
I upgraded the files in place and kept the existing registries: one
W.define per widget, one KINDS entry per particle kind, one STYLES entry per
visualiser style. The changes put cost before looks only where they are
invisible:
- particle motion uses the frame's time, so it is the same at any frame cap;
- shapes are batched into a few paths and draws;
- glows and shapes are pre-drawn sprites, not a gradient per frame;
- nothing draws while hidden, paused or with nothing to show;
- the power tier is read from the eased theme that helper-3's
  forge_power.js gives the host, so there is one rule for it and nothing is
  reduced twice.

The wisps, the galaxy and the widgets-only layout are locked: polish only.

## Files
- shared/forge_particles.js, forge_visual.js, forge_widgets.js,
  forge_widgets.css, forge_depth.js
- shared/forge_theme.py: particle and visualiser labels, wallpaper words, and
  the Alt+W / Alt+Q keys
- tests/test_desktop_v2.py, tests/desktop_v2_node.js,
  tests/test_hub_widgets.py, tests/browser/hub_fx_harness.js
- tools/desktop_bench.py and tools/desktop_bench.html
- Pre-edit copies are in backups/2026-10-07-overhaul/desktop/.

## New
- **Particles:** wisps, galaxy, depth and parallax, motion per second (fixes
  note #931).
- **Visualiser:** spectrum and nebula styles, peak caps on bars, a bass glow
  on the ring, batched drawing.
- **Widgets:** activity, battery, countdown, world clocks, focus timer, to-do
  and moon; an analogue clock; a date option.
- **3D wallpaper:** the zoom fix behind an open app; drawn at 3/4 resolution
  with fewer ray steps.
- **Keys:** Alt+W and Alt+Q are in the key registry.

## Numbers
Software drawing, one run per side, under heavy load. These are indicative
only; Emerson then said to stop measuring until one proper test.
- Everything on, hidden: CPU 5.0 -> 1.1% of a core (-78%).
- Everything on, paused tier: CPU -54%.
- Everything on, visible: CPU -8%.
- Bars visualiser: JS time per frame -53%.
- Ring visualiser: JS time per frame -40%.
- Widget visualiser: 60 -> 30 fps.

GPU % was not measured. The bench has a --gpu flag for the final test.

## Critic/breaker findings
**Fixed:**
- the bars style threw on narrow cards;
- tier text such as "reduced: GPU busy" was not recognised;
- the loop kept running with 0 particles;
- particles moved slowly under 20 fps;
- the countdown accepted impossible dates and times;
- a non-number particle amount crashed setup;
- NaN or frozen cards on bad stats;
- the nebula card was mostly empty;
- the Network graph started from the left;
- the spectrum had a hook at one end and a hard cut at the other;
- the battery text was too long on narrow cards;
- the memory line looked like a border.

**Left (cosmetic):**
- the ring style shows through the gaps between cards (the host's layout);
- the countdown title cuts off at the smallest card size.

## Needed from others
- **helper-3, hub/index.html** (notes 13 and 14): the forgeKey handlers for
  "widgets" and "close-app", plus a WidgetsPage mode and its CSS. Pass
  power_tier into Particles.look() and ForgeWidgets.apply(), and call
  ForgeDepth.set({tier}). Make the hub and desktop visualiser loops follow
  the tier.
- **helper-3, forge.py:** add "widgets" to the grab_focus tuple in on_key.
- **forge.py and desktop/particles.py:** add
  `stats["temps"] = forge_sysinfo.temperatures()` to the 30 s slow block.
- **Proper test with Emerson:** AC and unplugged, GPU per client:
  `tools/desktop_bench.py backups/2026-10-07-overhaul/desktop --runs 3 --gpu`.

## Against reports/desktop-v2-critic.md (checked item by item)

I had already fixed the report's real bugs 1 and 3 to 7 (see "Critic/breaker
findings" above). After the fixes I reran the critic's own break script
(/tmp/dv2/critic/brk.py). It found no errors in any visualiser style,
particle kind or stats case. The countdown rejects 2026-02-31, month 13 and
year 0000, and ignores the times 25:99 and 9:5.

Bug 2, "nothing writes the power tier", is fixed only on my side. My files
read `power_tier`, including texts like "reduced: GPU busy" and "paused:
hidden". The host pages still have to write it, and those are helper-3's
files (see "Needed from others").

Looks I fixed: looks items 1 (Nebula), 2 (Network graph), 3 (Spectrum and the
bar caps) and 6 (battery text). From the small points, the Activity labels
are bigger, the memory line is now dashed, and an unknown style now draws
bars.

Left unfixed:
- Looks item 5, wisps up close (the soft brown discs), and the galaxy
  reading as an ellipse: Emerson locked both looks ("look cool", "sick"), so I
  did not redesign them.
- Looks item 4, ring spokes showing between stacked cards at 700px: the hub
  page decides where the ring sits.
- Looks item 8, the full-screen visualiser showing through Material cards:
  that is the cards' see-through fill, which already existed.
- Looks item 7, the countdown title cut off at the smallest card size, and
  the right half of the card empty at full width.
- Small point: the Weather card shows "… –" placeholders at 2x2. That card is
  older than v2 and was not changed.
