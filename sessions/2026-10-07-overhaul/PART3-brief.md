folder: ~/Forge
effort: xhigh
model: opus
account: default
done when: the final review swarm, the U1 every-app sweep, the analyst table and the docs in sessions/2026-10-07-overhaul/HANDOFF.md "Next" are done or reported blocked, with tests run and each lane committed

Forge overhaul wave, part 3 (commander): final review, U1 every-app sweep, docs.
date: 2026-10-07 · for: Claude · queued by Relay task 63 (Noa)

Read ~/Forge/sessions/2026-10-07-overhaul/HANDOFF.md first (its "Update 22:30" section says what part 2 finished), then PLAN.md, REVIEW-SWARM-brief.md, U1-every-app-sweep-brief.md and reports/.

Do, in order:
1. Final review swarm (REVIEW-SWARM-brief.md): a harsh critic, an analyst and a breaker on the wave's commits 35ef508, 994989b, be02b98, b132a41, b84d33b. Opus only, never Sonnet. Fix what they confirm, test, commit per lane.
2. Analyst table: CPU/GPU/frame-time %, AC vs battery. First priority (Emerson, crew note 971): live GPU with an app open in front of Forge is still high after the restart; find what is still drawing. A ~10 min unplugged run needs Emerson's OK: ask on the crew board, do not wait on it. Plan it now; its measurements run in step 5, last.
3. U1 every-app sweep: run U1-every-app-sweep-brief.md as the commander (Forge Browser first).
4. Docs: PROGRESS.json, the touched apps' WIP.md, a docs/library entry for the wave, HANDOFF.md.
5. Last of all (performance runs go after all other work, Emerson crew note 1054): the analyst table's measurements, and the glass frame-rate re-measure in docs/library/forge/2026-10-07-glass-blur-freeze.md "Still to do" (expect about 60 fps in flat, frosted and liquid).
Also look first at the 6 tests/browser/run.sh FAILs listed in HANDOFF.md "Update 22:30".

Rules: Opus only. Batch hard (each request at least ~10 s of work). Never restart Emerson's Forge, the Claude app on 8445, Relay or Jan; never touch the CPU power caps. Coordinate on crew board "forge"; claim files before editing. Other sessions may be live in this tree (task 67 held apps/mission and shared/forge_convo.* on 2026-10-07); check `crew.py status forge` for claims. Commit only your own paths, never `git add -A`; split a mixed file by hunk (`git apply --cached`). Keep messages to Emerson short; WhatsApp him only when done or blocked.
