folder: ~/Games/eightysix
effort: high
account: hey

# Eighty Six: world look pass (Emerson's dislikes)

date: 2026-10-02 · for: Claude (a Relay session) · written by Tetsu (ejb-36) from Emerson's notes

done when: before/after screenshots of the same views show the world clearly better, fps per preset is the same or better, the suite passes, results/LOOK.md and the PLAN status line are written

Read `~/Forge/sessions/juggernaut-alpha/PLAN.md` (the "Raising the bar" section first), then `results/B4.md`
(the earlier look pass: grain, sun, bloom) and `results/B5.md` "Part 6". Work in `~/Games/eightysix`.

## What Emerson doesn't like (his words, 2026-10-02)
- The game looks "not pretty". His own read, which the evidence backs: **it's the colours, materials and models of the
  world**, not Godot. He wants the big map made **"stupid high quality"**.
- He wants **no upscaling or sharpening** as the base: done in B5 part 6 (every preset native). Do not undo it; win the
  frames back elsewhere.
- He plays on Ultra (native, TAA + MSAA 2x): TAA makes the image soft and smeary in motion. Look at whether a sharper
  anti-aliasing default on Ultra (MSAA only, or FXAA + MSAA) reads better, and measure it.

## The job
1. Before shots: the same 8-10 fixed views on both maps (ground close up, a ruined town, the Ash bridge, a far ridge,
   the Juggernaut beside a building), each preset you change. Numbered folders in `images/`; never delete images.
2. The world's look: ground, rock, concrete, brick, rusted steel, wood, vegetation. Materials should read as worn,
   painted, weathered and dirty, not plastic. A deliberate colour palette per map (a film's grade, not default grey-
   brown). Better textures (CC0: Poly Haven, ambientCG; each listed in `assets/SOURCES.md`), detail and normal maps,
   ambient occlusion baked or in the material, decals (cracks, stains, scorch). Kit models (buildings, walls, props)
   upgraded where they look blocky.
3. Frame rate must not drop: native Medium in towns is 42 fps (target 45), Low in towns 50 (target 60), so find the
   town cost first (props, shadows, draw calls, `b5_fps` "town" label) and pay for the new look from it.
4. After shots of the same views, fps per preset (`tools/bot_run.sh b5_fps --preset=<p>`, quiet GPU only), a row in the
   scoreboard, results in `~/Forge/sessions/juggernaut-alpha/results/LOOK.md` with a 3-5 line "try this" for Emerson,
   the PLAN status table gets a LOOK line, store the numbers in `~/Forge/docs/library/eightysix/`.

## Stay out of (other sessions are in them now)
- `scripts/legion/`, `scripts/ai/`, `data/enemies.json`: Relay 23 (Yuzu, B5 part 7).
- `scripts/combat/combat_fx.gd`, `projectile.gd`, `world/destructible.gd`, the combat-effects settings: Sora (ejb-ef, track A),
  who is making the 57 mm explosions and hit dust bigger.
- Post GPU slots on the crew board `forge` before every bot run; claim the files you edit there.

Commit only your own files. At 95 % of your account's 5-hour meter write the handoff and stop.
