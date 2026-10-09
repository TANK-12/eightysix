# U1: every-app sweep (ultracode session)
date: 2026-10-07 · for: Claude · launched by the overhaul commander Kaito (ejb-1f) once helpers 3, 4 and 6 are done

## Emerson's words
- "a forge v2 ... i want a better gui"; "i want everything to look nice, great, pretty and smooth"; "use less power ... i dont want to lower the looks of anything too much though"; "i want new features and optimization please dont remove features i like what i have"; "i want agents to have critics and analysts ... to look at things and try to break it and be critical"; "no sonnet".

## Goal
Every Forge app under ~/Forge/apps reaches the v2 standard: looks (shared/forge.css theme, smooth 150-250 ms transform/opacity transitions, no layout jumps, polished empty/loading/error states, thin styled scrollbars incl. ::-webkit-scrollbar, crisp at 760/1100/1500/1920), power (no polling/animation while hidden: shared/forge_idle.js and the shared power tier from shared/forge_power.js), robustness (bad input, server down, rapid clicks), and useful new features where an app clearly lacks one. Never remove a feature.

## How
- First app: apps/browser. Emerson (2026-10-07): "the forge app browser lowkey never works for me". Find out why (ask him what he sees if logs and a test run do not show it) and make it work reliably. Also Emerson: if something works fine, do not change it.
- Ultracode: fan out one worker per app (all Opus; no Sonnet, no Haiku), each with a harsh critic + breaker pass and an analyst measuring idle CPU visible vs hidden before/after.
- Skip what this wave already covered or another session holds: apps/claude, apps/mission, apps/wallpapers, hub/, shared/ (read-only; report needed shared changes), apps/relay (another session). Check `python3 ~/.claude/skills/crew/crew.py status forge` and `status overhaul` claims; claim each app's folder on crew `forge` before editing, release after.
- Each worker: back up to ~/Forge/backups/2026-10-07-overhaul/sweep/<app>/; app tests green (`apps/<app>/.venv/bin/python -m pytest -q tests`); headless screenshot looked at; black + pyright on touched Python; app WIP.md updated (verified vs not). Never restart Emerson's running Forge, any running app, or Jan; scratch ports with PID files.
- Games (emberfield, arcade, driftpeaks, eightysix, cosmos, janhollow): never lose game state; GPU tests only where the machine is quiet.
- Sudo allowed at above-medium effort (password in ~/.claude/projects/-home-ejb/memory/sudo-password-in-chat-preference.md); never change CPU power caps.
- Finish: one summary at ~/Forge/docs/library/power/2026-10-07-every-app-sweep.md (per app: changed, numbers, tests, left) and a board note to ejb-1f. Do not commit.
