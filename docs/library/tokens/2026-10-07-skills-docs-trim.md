# Skills and handoff docs trimmed, same information
date: 2026-10-07 · for: both · by helper-5 (Mio), crew overhaul (task 5)

Why: every session loads all skill descriptions and CLAUDE.md, and re-sends
its whole context on every call, so bytes in always-loaded or often-read files
cost tokens in every session. Emerson (2026-10-07): "where you can make skills
and documents more efficient but still have info".

Backups of everything touched: `~/Forge/backups/2026-10-07-overhaul/skills/`
(each old SKILL.md, plus `pace-full/`) and `.../wip/` (each old WIP.md).

## Skills (~/.claude/skills, own skills only)

| skill | SKILL.md bytes before -> after | description bytes (always loaded) |
|---|---|---|
| ask-checklist | 3,052 -> 2,953 | 251 -> 223 |
| crew | 10,134 -> 9,279 | 398 -> 381 |
| forge-session | 5,063 -> 5,167 | 385 -> 375 |
| godot-forge | 6,487 -> 5,810 (+ addons.md 1,025) | 196 -> 196 |
| lean | 4,969 -> 4,397 | 295 -> 313 |
| mech-forge | 8,423 -> 7,056 (+ kit.md 1,975) | 264 -> 264 |
| model-pick | 1,945 -> 1,364 | 302 -> 311 |
| pace | 3,778 -> retired | 270 -> 0 |
| retro | 4,517 -> 4,577 | 288 -> 288 |
| safe-shell | 4,819 -> 4,920 | 357 -> 335 |
| screen-capture | 3,220 -> 3,191 | 353 -> 324 |
| verify | 5,533 -> 5,399 | 382 -> 344 |
| **total** | **61,940 -> 54,113** (-12.6%) | **3,741 -> 3,354** (-10%) |

What changed, by skill:
- **pace: retired** (`gio trash`, copy in backups `pace-full/`). Emerson banned
  it on 2026-09-21 after it was 45% of his usage (memory
  `dont-use-pace-skill.md`); its description still cost 270 bytes in every
  session. The 70/92 usage rule itself stands (CLAUDE.md, `usage.py`);
  `~/.claude/tools/pace.py` and its settings permission were left alone.
- **lean:** batching is now section 1 (was 4). Section 6 now points at
  model-pick instead of restating an older model split (Opus design / Sonnet
  execute / Haiku bulk), which the 2026-10-03 registry superseded.
- **model-pick:** was a stale cache: it said the default is Sonnet 5.5 medium,
  the registry says Opus 5.5 medium (2026-10-03). It now reads `default`,
  `never`, `max_effort` and `ladder` from `~/Forge/shared/model_advice.json`
  instead of restating them; the Eighty Six rule and the benchmark figures
  live in the registry and the 2026-09-30 benchmarks doc (checked present).
- **crew:** batching rule moved to the top for every mode; notes section
  regrouped (reply / ack / close rules together). Same commands and rules.
- **mech-forge / godot-forge:** add-on lists and reference packs moved
  verbatim into `kit.md` / `addons.md` beside each skill (progressive
  disclosure), with a pointer naming what is there.
- **safe-shell:** sudo line updated to the current fact (the password lives
  in memory `sudo-password-in-chat-preference.md`, the old line said he gives
  it in chat); added that the CPU power caps are deliberate; `ydotool` noted.
- **forge-session:** new rule: a WIP.md past about 25 KB gets older dated
  sections moved verbatim into `WIP-archive.md` (the PROGRESS.json rule,
  applied to app WIPs); read WIP-archive only for history.
- **retro:** may propose retiring banned or unused skills.
- ask-checklist, verify, screen-capture: wording only, descriptions shorter.

Rules deliberately dropped: none. Restatements dropped in favour of their
single source: model-pick's numbers and Sonnet 5 / effort rules (registry),
lean's model split (model-pick).

Skills created: none. No procedure showed up as clearly re-derived across
recent sessions that an existing skill does not already cover; the one
repeated chore found (WIPs growing into history piles) became a rule in
forge-session instead.

## Handoff docs archived (moved verbatim, nothing deleted)

Apps outside the overhaul wave only. Each WIP.md keeps its current-state top,
the newest sessions, open items and next steps, with a `> Older sections moved
verbatim to WIP-archive.md` pointer where the cut was.

| app | WIP.md before -> after | WIP-archive.md | moved |
|---|---|---|---|
| dossier | 58,382 -> 27,938 | 30,929 | 2026-09-11 to 09-14 sessions, old verified/speed notes |
| pulseforge | 49,178 -> 15,899 | 33,850 | v1-v8 (2026-09-07/08) passes |
| acchan | 31,926 -> 17,809 | 14,535 | 2026-09-22 and 09-23 (session 2) status |
| novelforge | 31,792 -> 7,279 | 24,926 | 2026-09-04 to 09-07 sessions |
| foresight | 22,711 -> 6,343 | 16,857 | 2026-09-11 to 09-14 sessions, old verified notes |

Checked: for each app, the sorted lines of the old WIP.md equal the sorted
lines of new WIP.md + archive body, minus the pointer lines (only extra blank
lines differ). Not archived: claude, relay (in this wave), pulseforge
MANIFEST.md, READMEs (architecture, not history).

## CLAUDE.md

Proposal only, not applied: `2026-10-07-claude-md-proposed.md` beside this
file (8,845 -> 6,896 bytes, batching moved to the top).
