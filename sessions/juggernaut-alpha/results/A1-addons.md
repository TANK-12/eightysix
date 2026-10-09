# Lane A1 helper: Godot add-on candidates for Eighty Six

date: 2026-09-29 · for: Emerson (picks; nothing installed into `~/Games/eightysix`) · written by the
lane A1 helper (Rin, via Relay, started by Sora/ejb-83)

Every candidate already on this laptop lives in `~/Forge/shared/godot_addons/<name>/` (checked via each
folder's `plugin.cfg` / `.gdextension`, plus any `FORGE-PATCH.md`), so "version on this laptop" below is what
that folder actually declares. "Newest release" is the real upstream repo, checked 2026-09-29 via the GitHub
API (`api.github.com/repos/<owner>/<repo>` and `/releases`, `/tags`, `/issues`). Nothing was installed into
`~/Games/eightysix` — Sora owns that repo; this is a shopping list only.

## Recommended now

| Candidate | Upstream | Licence | Here vs newest | Godot 4.7 | For Eighty Six | Pick |
|---|---|---|---|---|---|---|
| **Terrain3D** | [TokisanGames/Terrain3D](https://github.com/TokisanGames/Terrain3D) | MIT | 1.0.2 here = v1.0.2-stable newest (2026-05-19), up to date | Yes, actively pushed (last push 2026-09-26) | The big map's terrain with collision that actually works (B5) — PLAN.md names it explicitly | **yes** (still needs Emerson's plan sign-off, PLAN.md open question 1 — default was "not installed until he says yes") |
| **GUT** | [bitwes/Gut](https://github.com/bitwes/Gut) | MIT | 9.6.1 here; newest is **v9.7.1** (2026-07-10) | 9.6.1's own docs say "Godot 4.6"; **9.7.1 is the one that targets 4.7** — it fixes Godot 4.7's stricter return-type checking on Doubles (mocked test objects), which 9.6.1 predates | Headless `GUT` runs for game logic across every lane, named in PLAN.md | **yes — grab 9.7.1, not the 9.6.1 folder sitting here** |
| **LimboAI** | [limbonaut/limboai](https://github.com/limbonaut/limboai) | MIT | v1.8.1 here = v1.8.1 newest (2026-08-20), up to date | Yes (`compatibility_minimum "4.2"`, pushed 2026-09-04) | A4's Legion AI: behavior trees for Ameise scout, Grauwolf pack flanking, Löwe heavy-fight states | **yes** |
| **Phantom Camera** | [ramokz/phantom-camera](https://github.com/ramokz/phantom-camera) | MIT | 0.11.0.3 here = v0.11.0.3 newest (2026-07-19), up to date | Mostly — issue #670 ("PhantomCameraManager singleton fails to register on Godot 4.7.1", filed against this exact version) closed 2026-07-24 with no new release since, so it's worth a five-minute smoke test on install | Third-person / cockpit / Handler tactical camera switching (A1, A2, A5) | **yes — smoke-test the autoload singleton the day it's installed** |
| **Debug Draw 3D** | [DmitriySalnikov/godot_debug_draw_3d](https://github.com/DmitriySalnikov/godot_debug_draw_3d) | MIT (local `LICENSE`; GitHub's own detector shows `NOASSERTION`, a known quirk of hand-written MIT headers) | No version file; `.gdextension` says `compatibility_minimum "4.4.1"`. Newest tagged release: 1.7.3 (2026-04-04) | Yes (min 4.4.1) | On-screen 3D debug drawing for IK foot targets, gait tuning, AI perception cones, ballistic tracers — useful across A2/A3/A4 | **yes** |
| **Sky3D** | [TokisanGames/Sky3D](https://github.com/TokisanGames/Sky3D) | MIT (local file; GitHub detector again shows `NOASSERTION`) | 2.1 here = v2.1.0 newest (2026-05-19), up to date | Yes | Day/night cycle, volumetric clouds and fog — both named in PLAN.md for both maps | **yes** |

## Later (useful, not urgent, or a known issue to watch)

| Candidate | Upstream | Licence | Here vs newest | Godot 4.7 | For Eighty Six | Pick |
|---|---|---|---|---|---|---|
| **ProtonScatter** | [HungryProton/scatter](https://github.com/HungryProton/scatter) (mirror of [codeberg.org/hungryproton/proton_scatter](https://codeberg.org/hungryproton/proton_scatter)) | MIT | plugin.cfg here says **4.2.0**, but GitHub's newest *tagged* release is only "4.0" (2023-10-23) — no tag matches 4.2.0, so this copy most likely came from the Codeberg mirror, which looks like the project's real primary home now (GitHub repo itself was pushed as recently as 2026-09-27) | **Open issue** — [#255 "Not compatible with 4.7"](https://github.com/HungryProton/scatter/issues/255), filed 2026-06-03, still open with active comments as late as 2026-09-18 | Scattering rocks/shrubs/grass/debris for the asset kit (B3, B5) | **later** — retest once #255 closes; B3 can hand-place the small map's scatter without it |
| **Road Generator** | [TheDuckCow/godot-road-generator](https://github.com/TheDuckCow/godot-road-generator) | MIT | 0.9.3 here = 0.9.3 newest (2026-07-16), up to date | Yes (pushed 2026-09-27) | The roads named for the small map (B3) | **later** — not needed until B3 |
| **Cyclops Level Builder** | [blackears/cyclopsLevelBuilder](https://github.com/blackears/cyclopsLevelBuilder) | MIT | 1.5.0 here = v1.5.0 newest (2026-09-17), up to date | Yes, confirmed ("1.5.0 works with Godot 4.7 and later") | Fast in-editor greyboxing for iterating on level layout | **later** — handy for whiteboxing, but A1's throwaway test level and B3/B5's real maps don't need it |

## No (checked, not a fit for this game)

| Candidate | Upstream | Licence | Here vs newest | Godot 4.7 | Why not |
|---|---|---|---|---|---|
| **Dialogic** | [dialogic-godot/dialogic](https://github.com/dialogic-godot/dialogic) | MIT | 2.0-Alpha-20 here = 2.0-alpha-20 newest (2026-07-21), up to date, still Alpha | Yes (its own `plugin.cfg` says "Godot 4.5+") | Branching-dialogue/visual-novel tool. PLAN.md has no narrative or dialogue system for Eighty Six — reconsider only if a Handler/comms narrative layer gets added later. |
| **Godot-MToon-Shader** | [V-Sekai/Godot-MToon-Shader](https://github.com/V-Sekai/Godot-MToon-Shader) | MIT | 3.4.0 here; upstream has no tagged releases (rolling), last push 2026-07-08 | Reasoned yes (shader-only, no engine-version gate found), not confirmed | An anime cel-shading toon shader for VRM-style faces. Eighty Six's mechs use real-ish PBR materials and an Undertaker decal, not the flat toon look this shader targets. |
| **VRM** | [V-Sekai/godot-vrm](https://github.com/V-Sekai/godot-vrm) | MIT (local `LICENSE`; GitHub detector shows `NOASSERTION`) | `plugin.cfg` here says **2.0.1** — but `FORGE-PATCH.md` in this same folder (2026-09-25) describes patching *this* copy against a "**v2.1.0**" compile failure on Godot 4.7.2. Those two don't agree; whoever installs this should check what's actually on disk before trusting the version string. Newest GitHub tag either way: v2.1.0 (2024-11-08) | Yes once patched (the patch is already applied in this local copy per `FORGE-PATCH.md`) | VRM humanoid-avatar importer. Eighty Six has no VRM avatars — mechs and Legion are Blender `.glb` exports, not VRM. |

## Procedural animation and IK: no addon needed

Godot 4.6 (released January 2026, so already in the 4.7.2 install here) brought inverse kinematics back into
core as a proper framework: a stack of IK modifier nodes on `SkeletonModifier3D` with two-bone, FABRIK, CCDIK
and spline solvers. That covers A2's foot-placement IK directly, no addon required. The one third-party
candidate found, `BobMervell/Procedural-Animation` (GitHub), fails the "actively maintained" bar this list
uses — no updates or issue responses — so it is skipped rather than listed. Nothing else named and maintained
turned up for procedural animation specifically; A2's gait generator is bespoke code against
`refs/anime-motion/ANALYSIS.md` either way.

## Everything checked, not just the shortlist

Every folder in `~/Forge/shared/godot_addons/` was opened for this list (12 total): the six recommended now,
the three for later, the three ruled out above. `debug_draw_3d` and `limboai` carry no `plugin.cfg` (they're
GDExtensions with a `.gdextension` file instead) and both have a `.forge-disabled` marker meaning "optional:
copy in when a project needs it" — neither is wired into any project by default.

## How this was checked

Local versions: read directly from each folder's `plugin.cfg` (or `.gdextension` + `version.txt` for the two
GDExtension-only ones). Upstream data: `curl` against the public GitHub REST API
(`/repos/<owner>/<repo>`, `/releases`, `/releases/latest`, `/tags`, `/issues/<n>`) plus a handful of web
searches to find the correct repo for candidates whose `plugin.cfg` author name didn't map cleanly to a GitHub
org (Cyclops, MToon, VRM, LimboAI's real org is `limbonaut` not `limbo-ai`, ProtonScatter's real repo is
`HungryProton/scatter` not `ProtonScatter`). No addon was installed or copied into any project; this is a
reasoning document only.
