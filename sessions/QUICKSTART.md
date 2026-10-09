# Quick start: what is left after the 2026-09-26 wave

Emerson (2026-09-26): "make sure there is all the handoffs in a quick start
manifests tab so i can quickly get one total new session finishing all your
undone work". This file is that tab: what is **left**, in the order to do
it, with the exact files and checks. Done work is not repeated here; each
section links the brief with the full history. Updated by Finisher (S10) at
18:10 on 2026-09-26.

## Questions for Emerson (QUICKSTART sweep, 2026-10-09, Relay task 123)
Things the sweep could not finish without you. Answer any of them in chat or WhatsApp.
1. **Retro:** last one 2026-09-16 (23 days). Run `/retro` on the hey account when you are on it? And should it
   start by itself once a week (item 7b)? That is one extra session a week, roughly the cost of a normal task.
2. **Shiori** (item 8): Claude's own persona is in (an anxious librarian for fact checks, avatar Izumi, voice
   bf_alice). Keep, rename or tweak? Her mood switches on in the Claude panel after the Claude app restarts.
3. **Teach me** (item 11): pick the first topic (B6 torque bench, Legion path-finding or the HE blast) and a time
   you are free; it needs you there.
4. **Jan front desk** (Relay WhatsApp): you set it to off (Claude first). When you want Jan back on, open Jan and
   a session scores it with `frontdesk.py --samples`.
5. **NovelForge rework** (2026-09-28): the live outline run on the 2B and 0.8B needs Jan open and someone to
   release the 27B Jan loads by default. Do it in a session you start, or change Jan's default model first?
   Same for the other Jan-only checks: Acchan B42's tier evals (`tests/eval_prompts.py`) and typing into its
   shell window by hand on screen.
6. **GPU easing values** (ejb-95): reset your saved Forge settings to the planned values (max_fps 60,
   particle_fps 30, particle amounts 1.25, battery 30/20 fps)? And 30 fps instead of 25 under load?
7. **AI Studio:** OK for GPU test runs and the compact model downloads (Z-Image-Turbo, FLUX.2-klein 4B, Wan2.2
   5B)? Bring back draggable panels?
8. **Hardware checks only you can do:** unplugged power per mode (Power app > Measure CPU watts, Forge open vs
   closed); tell a session if you ever hear the hub music twice; and look at the white-on-white fix (task 57) in
   Forge after its next restart.
9. **Enjoy-style Claude app:** still wanted now that Mission Control has its ideas?

## Mission Control: a proper Claude conversation view (Emerson, 2026-10-07): done

Rebuilt 2026-10-08 (Relay task 109) after Emerson said it still sucked: the chat now fills the window (Mission's bars step
aside), big type with a size slider, anime night look with sprite portraits, tool calls folded into one steps bar per run,
model / effort (to Max) / ultrathink in a popover from the composer chip, everything else in a Session slide-over, Chats
slide-over (Ctrl+K). Sessions list: newest activity first (calm), Archived section, names = task number + short description.
WhatsApp mirror (Emerson's note 1295): the Relay thread live inside Mission (pinned in Chats, nav entry), with a box that
talks to Relay or the boss exactly like WhatsApp (`relay as-whatsapp`).
Details and what is verified: apps/mission/WIP.md (top section).

Done 2026-10-07 (Relay task 67): Chat tab per session (shared renderer shared/forge_convo.js), reply box with Claude/Jan,
model, effort, ultrathink and reasoning pickers, Messages view threading replies to "message everyone", Swarm view, and the
map rebuilt as non-overlapping cards that fill the window with zoom -/fit/+. Details in apps/mission/WIP.md.

"i want mission control to have a better claude forge app for conversations as well but i guess we can also keep the open in claude app".
Want: reading and talking to a session's conversation inside Mission Control, as good as the Claude app (apps/claude, port 8445):
proper chat layout, tool calls folded, live updates, a reply box. Keep the existing "open in Claude app" button beside it.
Reuse the Claude app's conversation rendering through a shared file rather than a second copy. apps/mission is overhaul lane H7,
held by Relay 63 until its commits land; queue as its own Relay task after that.
Emerson (follow-up): "mission control is great but it doesn't have a conversation thing of its own"; he likes the open-in-Claude
button and the quick message to one chat or to all, but "how do I get replies if I wanted one from the message everyone feature".
Today the message goes out as a crew-board note (apps/claude/everyone.py message(): "answer him in your next reply"), so each answer
lands only in that session's own chat. Build: replies come back into Mission Control, shown under the message that asked (one thread
per broadcast, a line per session that answered), plus the per-session conversation view above.
Emerson (more, 2026-10-07): the look can copy the Claude app's interface "or whatever the super great task agent and critic agent
come up with" (free hand on design; one critic agent on the look is approved). "I need good looking things for model, effort, Jan,
Claude, ultrathink, reasoning and all that jazz, and swarm looks and stuff": good-looking pickers for model and effort, Jan vs Claude,
ultrathink / thinking level, visible reasoning blocks, and a swarm view (many agents working at once, who is doing what) that looks great.
Relay task 67 builds it.

- Map view (Emerson, 2026-10-07 ~22:40): "the map in mission control is a bit small", "lots of small text is a no go for me" (his eyes aren't the best), "dont want to be able to scroll right in the map view", "a bit of fat on the side and black space it dont need". Sent to Ren (task 67). Emerson's follow-up: the eyesight remark is "just a fyi thing"; don't change text sizes across Mission Control, only fix the map.

## Hub top bar: app icons push the other icons off screen (Emerson, 2026-10-07): done

Done 2026-10-09 (Relay task 121): the open-app icons scroll sideways in their strip, a "+N" button counts the ones
out of sight and opens the overview, the brand and tray never shrink, and when the bar is still too full the labels,
title, last icon, zen/background and reload give way in steps. Checked headless at 1400, 800 and 500 px (and every bar
width from 500 px at text size 1 and 1.5) with 30 open apps (tests/browser/hub_bar_overflow_harness.js); numbers and screenshots in
docs/library/forge/2026-10-09-hub-top-bar.md. Hub reload picks it up, no Forge restart.

"before all this work, the top bar: when i add apps it will push the icons of non-app stuff off the screen" (pre-existing).
Want: the non-app controls (settings, search, power, clock and the rest) always stay visible; app icons shrink, scroll
sideways or overflow into a "more" menu when there are many. hub/index.html is overhaul helper-3's; asked them (crew note), else fix after.

## Text size and app size settings work badly (Emerson, 2026-10-07): done

Done 2026-10-07 (Relay task 68): sliders preview while dragged and apply once on release (one zoom, one save, one theme to the apps);
no more flip-flop. Measured before/after in docs/library/forge/2026-10-07-size-sliders.md. Hub reload picks it up, no Forge restart.

"in forge before all this work the text size and app size changer doesn't work that well" (pre-existing, not from the overhaul).
Where: Settings size presets and sliders in shared/forge_theme.py (SIZE_KEYS ui_scale/text_scale/icon_scale, SIZE_PRESETS),
ui_scale becomes WebKit zoom in forge.py (page_zoom, set_zoom_level ~929 and ~1389), text_scale/icon_scale are applied by
shared/forge.js/forge.css in each app. Emerson: also "laggy and slow" when changing it. Check first whether every slider tick re-zooms every open app view, saves settings and broadcasts the theme (no debounce); likely fix: preview on the current page only while dragging, apply to all views once on release. Ask Emerson what else goes wrong (some apps ignore it, layout breaks, resets, popouts?).
Those files are held by overhaul helpers 3 and 6; fix after they report (overhaul commander queues it).
Emerson (more, 2026-10-07 ~21:40): "when I change the size it will keep switching, cause I think it thinks the slider moved and
changes setting when the thing resized, but I don't know; also just make it faster". Likely a feedback loop: App size is WebKit zoom
on the page that holds the slider, so the slider rescales under the pointer mid-drag, reads a new value, re-zooms, and so on.
Relay task (see relay status) builds the fix.

## Forge Browser "never works" (Emerson, 2026-10-07): done 2026-10-09

"also the forge app browser lowkey never works for me". Task 74 fixed the first page staying hidden (forge.py 97bfd48). Relay
task 122 tested the real hub and views in a shown window on 11 real sites and fixed: app shortcuts dead once a page had the
keyboard, a crashed page staying blank, local paths turning into searches, a stale app.js after updates. Verified by tests
and the rig (apps/browser/WIP.md says how); not yet on his screen: needs a Forge restart.

## Session names everywhere (Emerson, 2026-10-07): done 2026-10-08

"i want these names to line up with the names in eg app, same goes for relay
and the board". Crew Room, the Board and Relay's page all name a session
through `shared/forge_session_names.py` (Claude-app tab name, else the crew
board's name): Relay shows "Mika (relay-59-work)" on running cards and each
task's last session (Relay task 94; see `apps/relay/WIP.md`,
`apps/board/WIP.md`). Live after the next Forge restart. Still open: "Old
chats not considered active": idle sessions already are not busy in Crew
Room and the Board; ask Emerson whether he wants idle Claude-app chats
hidden altogether.

## Relay WhatsApp (Emerson, 2026-10-06 night): done, Jan part parked
Sweep 2026-10-09: nothing left to build. Emerson later chose Claude first, Jan later, so `whatsapp_frontdesk`
is off (apps/relay/WIP.md); the live Jan score waits for him to turn it on (question 4 at the top).

Built 2026-10-07 (Relay task 50): items 1 and 3 (Jan front desk, "waiting for usage" line); item 2 is covered by 3. Left: score Jan live with `frontdesk.py --samples` once Jan is open.

1. **Say when it is waiting.** A WhatsApp message that can't start a session (usage full) gets no reply at all.
   Send "got it, waiting for usage (resets ~HH:MM)" from the boss (plain Python, costs nothing).
2. **Chat when Claude usage is out.** Emerson wants WhatsApp to work as a general chat, with work started
   only when he asks (chat mode from task 46 already does that split). Idea: answer chat on a local Jan model
   when both accounts are full, so chat never goes silent. Mind the Jan-is-shared and iGPU rules.
3. **Jan answers first, Claude takes over** (Emerson, 2026-10-06): make Jan (local model) the front desk
   for the WhatsApp chat, always, not just when usage is out. Give it a really strong system prompt so it
   handles most messages itself (chat, questions, status via Relay commands like progress/usage) and
   knows when to hand off: anything needing real work or deeper thinking goes to a Claude session with a
   short written handoff (what he asked, context so far). Claude then takes over, does the work and
   replies in the same chat. Needs: Jan model setting owned by Relay (per-app, loads on demand, unloads
   when idle), the prompt kept in a file Emerson can edit, and a test set of sample messages with the
   expected answer-or-hand-off call.

## To do from 2026-10-02 evening (Emerson's chat with Tetsu): done or waiting on Emerson
Sweep 2026-10-09 (Relay task 123): 6, 8 and 9 done, 7a done, 3, 7b and 11 are questions at the top; 0, 1, 4, 5
are his own sessions or wait for him to ask.
Full list, with the wishlist ideas: `docs/library/ideas/2026-10-02-wishlist-and-todo.md`.
- **Eighty Six look (Emerson, 2026-10-03):** more maps, better cities, "actual AAA graphics, not low poly", "way too washed out". Maps: Relay task 36 (maps brief, told on the board). Look: Relay task 37, `sessions/juggernaut-alpha/2026-10-03-look-aaa-brief.md`.
- **Eighty Six clipping (Emerson, 2026-10-03):** camera and legs slip through the floor; sideways or end-over-end rolls clip. Relay task 38, `sessions/juggernaut-alpha/2026-10-03-clip-roll-brief.md`.
0. **Calculus exam: top priority, before any Forge work** (Emerson asked for it to be the most
    important thing). (Emerson, 2026-10-02: "soon", says he knows nothing yet). First ask: exam date,
    course or exam board, and the topic list or past papers. Then a day-by-day plan to the exam, starting from
    basics (functions and graphs, limits, derivatives and rules, then integrals), lots of worked examples and
    practice questions with full solutions. His course is already in Study Companion (apps/study-companion):
    MATH1014 Foundations of Calculus (Dr Tiffany Jones), weeks 1-6 notes in data/MATH1014/ (t1 intro + revision,
    t2, t3 trig, t4 exp/log, t5 limits, t6 differentiation, questions/); ask him for later weeks and past papers. Teach, do not do his homework.
    Until the exam: study first, Forge after as the reward. Short sessions (one topic, about 25 minutes), and
    teach calculus through his own mech game where it fits (speed = rate of change of position, and so on).
    Where he is (2026-10-02, 19:00): basic algebra fine (solved 5x - 9 = 10 -> 3.8; uses a calculator for
    division, fine). Was taught the power rule with d = t^2 -> speed 2t. Left on an open question: the Legion
    moves d = t^3; find its speed formula and the speed at 2 s (answer 3t^2, 12 m/s; let him try first).
    Study guide written: `docs/library/learning/2026-10-02-math1014-study-guide.md` (topics 2-6 from his notes,
    worked examples, practice + answers; all 32 answers checked numerically). Start him on it, topic 4 first.
1. **Eighty Six version 014: done** 2026-10-03 (Tetsu, hey; suite 396/396). Did notes 6, 8, 11-14, 17-20 from
   `juggernaut-alpha/2026-10-02-emerson-notes-012-aim-brief.md` (results/V014.md). **Next:** ricochet/near-miss, aim
   measured, first-person look: `~/Forge/sessions/juggernaut-alpha/2026-10-03-v015-brief.md`. Waiting on Emerson:
   Legion accuracy pick, what "blades horizontal in a slide" means, whether spawn sparks / falling through are gone.
2. **White-on-white text: done** 2026-10-07 (Relay task 57). Hub text on a bright wallpaper, glass panes at high
   strength and the desktop corner buttons; contrast sweeps hub 160/0 and desktop 25/0 in tests/browser/run.sh,
   before/after shots: `docs/library/forge/2026-10-07-white-on-white.md`. Left: look at it in Forge after a restart.
3. **Retro is overdue** (last 2026-09-16): `/retro` on the hey account. Waiting on Emerson (question 1).
4. **Epstein files review** (Emerson's idea, his own session): Dossier, public court records only; keep
   "named in a document" apart from "did something".
5. **Cheap tries from the wishlist** (when he asks): VR cockpit (Godot OpenXR), hover-racer or drone
   prototype, resonance sword / sound gun / light-chamber laser as Eighty Six or Arcade weapons.
6. **Claude panel: `/compact` does nothing.** Typing `/compact` (with or without text after it) in the
   Forge Claude panel arrives as a plain chat message; the compact never runs. Make the panel pass Claude Code's
   built-in commands (`/compact`, `/context`, `/clear`) through to the session, and add a test. Owner:
   `apps/claude`. Seen 2026-10-02; cause not looked at yet. **Done 2026-10-07** (be02b98, Relay task 63 lane H2b):
   a message starting with "/" goes untagged, so /compact, /context run as commands; checked live with the real
   CLI (compact_boundary event, divider drawn). Claude can also queue one itself (`panel_command` tool).
7. **Fix Claude's amnesia** (Emerson: "I hope we can fix your amnesia"). Done 2026-10-02: tonight's slip is a
   failure mode in `~/.claude/self/SELF.md`, and a chat diary started in `docs/library/Notes/chats/`. Still to do:
   (a) a short diary entry per memorable chat (tone and running jokes, not just facts), and make sessions read the
   newest one; (b) the retro starting by itself, weekly, as his self-starting rule asks (it costs tokens per
   run, so say the cost); (c) an optional persona pick (see the rule below). Real learning in the model itself
   is not possible from here; this is note-taking around a fixed model, and that should be said plainly.
   **2026-10-09:** (a) done: a "Chat diary" rule in ~/.claude/CLAUDE.md (read the newest entry before a chatty
   conversation, add a short dated one after a memorable chat). (b) waits on Emerson (question 1). (c) see item 8.
8. **Claude designs its own persona** (Emerson said yes, 2026-10-02). Write it into `~/.claude/self/PERSONALITY.md`
   beside the others as one more mood, not a replacement: the existing six stay (Emerson's waifus are safe).
   First sketch from the chat: a slightly anxious librarian who double-checks every claim, likes terrible puns.
   **Done 2026-10-09 (Relay task 123, 670e798):** Shiori, the `check` mood (fact checks, "are you sure", "look it
   up"), `apps/claude/personas/shiori.json`, written up in PERSONALITY.md and the Tetsu output style. Tests 23
   pass; Avatar Studio shows her on the Izumi card. Emerson to approve or tweak (question 2).
9. **Talk to Claude by voice** (Emerson, 2026-10-02): back-and-forth chat with speech-to-text in and text-to-speech
   out, in the Claude panel. He mentioned new TTS models out recently: look them up, list candidates with their real
   source and wait for his pick (nothing installed without review). Reuse the voices and STT already in ~/Forge and
   Acchan first, and follow the local-compute throttling rule (TTS/STT/LLM share the machine).
   **Done 2026-10-08** (Relay task 113, then 120): mic dictation and spoken replies in the Claude panel
   (`shared/forge_voice.js`, apps/claude WIP "voice"), POST /api/voice/ask, cloned character voices.
10. **Music for friends' copies of Eighty Six** (Emerson, 2026-10-02): the 86 soundtrack stays out of share zips
    (copyrighted, personal use only). Instead: (a) a setting or "music folder" picker so a friend can point the
    game at music they own, using the same data/music.json fallbacks; (b) optionally, bundled royalty-free or
    CC tracks (with licences in assets/SOURCES.md) so the shared game is not silent; (c) the HOW-TO-RUN.txt
    tells friends how to add their own music. **Done 2026-10-08 (Relay 95):** (a) was built in lane A7; (b) three
    Kevin MacLeod tracks (CC BY 4.0) ship as the fallback, credited in game, in SOURCES.md and HOW-TO-RUN.txt;
    music lists offer only tracks really there; (c) readme walks friends through it. Checked on a real export
    run as a friend's machine. Not checked: Windows/macOS hardware, and whether you like the three tracks.
11. **Teach me, not just build it** (Emerson, 2026-10-02): pick one real system in Eighty Six (the B6 torque bench,
    Legion path-finding, the HE blast) and teach Emerson how it works until he can explain it to a friend:
    plain words, small steps, a question back each step, code walked line by line. A running "what I learned"
    note per topic in docs/library/learning/. Goal: build the deep, specific knowledge, one topic at a time.

**Rule (Emerson, 2026-10-02):** when he raises an idea, a wish or a fix in chat, put it on this list, including
small or half-serious ones and ones Claude would not have picked itself. Keep it short and say what is
done and what is not.

## Claude app: names and effort levels (Emerson, 2026-10-01): done
Sweep 2026-10-09: both closed. Name: the per-prompt rename hook plus `crew.touch()` asking every time. Effort: fixed
2026-10-01; **verified live 2026-10-09** with `ps`: the running app sessions carry `--effort high` (3),
`medium` (1) and `xhigh` (2). Original report below. Owner: `apps/claude` + `~/.claude/skills/crew`.
1. **Tab name and crew name disagree.** The session on tab "Koharu" (ejb-ca) signs
   itself "Haru" on the forge crew board. They must be the same name everywhere:
   tab, board and the session's own sign-off. Where it comes from: the tab name is
   `apps/claude/names.py` (picked from the conversation id, saved in its metadata).
   The board gets it through `crew.claude_app_name()` (asks the app's `/api/sessions`
   and looks up the Claude session id), which `notes_hook.py` and `give_persona()` apply.
   **Reasoned, not verified:** a likely cause is the lookup missing (the app's session id
   changes on `--resume`, or the 0.5 s request times out and returns ""), so the board
   keeps or makes up a different name. The session also signs posts from its own
   context, so it repeats whatever name it was told first. Haru's post #521 says it
   already fixed stale persona names on reused ejb-xx names, but on 2026-10-01 they
   still did not match. Fix so the tab name always wins, and tell the session its name.
   Add a test for the miss case.
   **Looked into 2026-10-01 (Mei, ejb-c6), no code changed:** in the data now, tab
   "Koharu" (conversation 47d34aa2f85c) runs session b7d3aa16, which is **ejb-88**,
   shown as "Koharu" on the board. **ejb-ca** is session b2d8760f, whose tab is "Haru"
   (4d127978c9e2). So tab and board agree for both; "Koharu (ejb-ca)" looks like two
   tabs read as one. The only board names that disagree with their tab today (ejb-49,
   -54, -27, -0a, -4f) belong to members last seen 6 to 30 hours ago, before Haru's per-prompt
   rename hook (`notes_hook.rename`, #521) landed; they update on their next prompt.
   The remaining small hole is **closed**: `crew.touch()` used to ask the app only when
   the session id changed, so one timed-out lookup kept a picked name. It now asks every
   time (`~/.claude/skills/crew/crew.py`, test
   `test_a_missed_tab_lookup_is_asked_again_next_time`, red then green; crew + notes_hook
   tests 41 pass). If it shows up again, note the tab's conversation id and run
   `crew.session_names()` to see which ejb-xx it really is.
2. **Effort levels: fixed 2026-10-01 (Mei, ejb-c6), needs a Forge restart to take effect.**
   Cause: a change made *while Claude was mid-turn* kept the running process,
   so the next message went to it with the old effort (and model/permission).
   Idle changes already worked. Fix: `web_app.change_settings` now calls
   `conv.close()`, which ends the process after the turn in progress.
   **Verified:** new test `test_a_setting_changed_mid_turn_applies_to_the_next_message`
   (red before, green after); apps/claude tests 149 pass; the 3 live app
   sessions' real `claude` command lines all carry `--effort` (ps). Not checked:
   whether the level is shown inside the session. Original report:
   **Effort levels seem broken.** Emerson says the effort picker doesn't seem to work.
   Path: picker `static/app.js` (~l.958, 985) -> `web_app.py` settings (~l.345) ->
   `runner.py` `EFFORTS` (l.168) -> `--effort <level>` on the next message (l.257),
   "Default" sends nothing. Not looked into yet. Check: set each level, send a
   message, confirm the real `claude` command line has the flag (and that the
   level shows in the session). Also check that a change mid-conversation applies on
   the next message as the settings note promises.

## Older sections: triage 2026-10-09 (Relay task 123)
Everything from here down is history; checked against git log and the app WIPs. Done since they were written:
GPU easing (committed with task 56), Settings sub-pages (a99362c), Terminal split panes (f9e8c41), B41 panels,
B39 frame cap, Alto, app groups, B18 speed probe, background music silence (S26 item 9), Pixel Forge name
(label is PixelForge), Mission Control and app icons (task 66). Still open: B42 Acchan "local Claude Code" (built; only the Jan tier evals and a by-hand check are left,
question 5), "music heard twice" (never
reproduced; question 8) and the power run (question 8). Still open with no owner and not in the questions: the
full hub on every screen and the Tools improve-next lists.

## S26 (Yui/Tetsu, ejb-be) handoff, 2026-09-28: read first
Emerson: "finish up all the unfinished forge tasks and desktop and make the
widgets and extensions, leave NovelForge alone". Done, committed, checked off
screen (run.sh 780 PASS, pytest 274): S25 widgets/desktop/effect keys (was
left uncommitted), Claude usage bars no longer vanish, #257 silent music
(WirePlumber had saved 0% for "Forge"; fixed live too), glass kinds
Flat/Frosted/Liquid, S24 as one desktop window per screen, S23 2.5D
wallpapers (on in his settings). Also fixed: a desktop-window deadlock from
SIGUSR1 (100% CPU), a 3 s Forge freeze every 30 s off Wi-Fi. Left: "music
heard twice" (#257, not reproduced); the full hub on every screen; live
checks after a Forge restart and a log out/in. Follow-up (10:05): desktop
layer seen working live, ⚙ settings button added; background music still
silent live (measured, not fixed): the next session starts at item 9 of
sessions/2026-09-28-S26-finish-wave.md.

## NovelForge rework (Tetsu, ejb-34) handoff, 2026-09-28: committed 2026-10-09
**Sweep 2026-10-09 (Relay task 123, 8a58a8e, b369f19):** steps 1, 3, 4 done: UI checked headless in both modes
(no page errors), README "Rework" section and a MANIFEST note, committed; a critic's fixes to the delete/reset/rewind
routes are in b369f19 (46 tests pass). Step 2 (live outline run on Jan) waits on Emerson (question 5).
Built and tested with a fake Jan client (38 tests pass), not yet seen in a
browser or run on a live model: model per role in the header (writer, planner),
14 genre presets (Korean first), a checked outline pipeline that never writes
filler, preset-driven prose prompts with prompt caching, BM25 retrieval, and
delete/reset/rewind everywhere. Uncommitted. Left, in order: (1) UI check with
the verify skill, (2) live outline run on the 2B and 0.8B (allowed by Emerson;
**Jan auto-loads the 27B on start, release it at once**), (3) MANIFEST.md,
README, forge_app.json, (4) commit. Paste: "Read
~/Forge/apps/novelforge/WIP.md top section and finish its Improve next list;
load forge-session, verify and lean first."

## S21 (Nene, ejb-c3) handoff, 2026-09-27 evening: read first
Done and checked off screen (needs a Forge restart): a particle pick per
wallpaper, particles that show on bright pictures, Glitter and Paper lanterns,
Orbit and Terrain visualisers, Alt+V rebuilt (no lag, 7 switchable effects),
an app search in Alt+Space. The GNOME extension's settings page is written but
not seen. Brief: sessions/2026-09-27-S21-effects.md. Next, one fresh session
each, in order: S22 widgets + glass + media player + the "go to player" bug,
S23 2.5D wallpapers, S24 monitors (their briefs in sessions/). Paste: "Read
~/Forge/sessions/QUICKSTART.md and do the S22 brief top to bottom; load
forge-session, verify and lean first."

## Emerson's answers, 2026-09-27 afternoon (recorded by Kenji, ejb-eb)
His words, tidied. Follow-up questions are still open; answers go here.
- B41 AI Studio: look at the Board app; make the UI draggable.
- B20 widgets: more widgets, each one editable itself (e.g. the CPU/battery
  widget with more info).
- B40 DONE + checked by Nagi (ejb-6b), needs a Forge restart: Alt+B entrance, Alt+V pulse (brief S19).
  Was: Alt+B: an animation when switching into Alt+B; then a second keybind
  launches a special effect: light pulsing to the music, wallpapers brought
  alive, a proper visualiser feel; borrow PanelForge's old ideas. Only on
  that keybind.
- A22 multiple monitors: go ahead and build it.
  Part (a) pop-out DONE + checked by Tomo (ejb-6b), needs a Forge restart; part (b) one window per screen not started. Brief: sessions/2026-09-27-S19-monitors.md
- Blender and Godot: ignore for now (no Godot character pick).
- App groups: "just let me drag apps and stuff" (he groups them himself).
  DONE + checked by Nagi (ejb-6b): drag an app onto another = folder (brief S19).
- "Pixel Forge": one word (forge_app.json label is already PixelForge).
- DONE (Kenji, see apps/driftpeaks/WIP.md): Alto soundtrack: the files in ~/Music/Alto were one-hour loops. Find where
  each track ends (6-7 min online), put the short tracks in Drift Peaks,
  keep only the game's copy and short ones in ~/Music/Alto, delete the rest.
- Power: he is unplugged now and has been trying the frame-rate settings.
- Then fix the board issues (#257: background music sometimes silent while
  the visualiser moves; the visualiser ignores some audio, above all Qobuz;
  look at the Acchan logs and fix them). Kiko (ejb-e3) declined #257 (#258).
  #257 status 2026-09-27 (Riku): QBZ deafness and the Acchan shutdown crash are fixed;
  the music sounding twice and the silent-music report are still open, see
  sessions/2026-09-27-S20-board-connect-aistudio-panels.md.
- Follow-ups (same afternoon): "do whatever you think is right, don't ask
  questions", so the defaults Kenji offered stand: order Alto, #257,
  A22, B40, B20, groups, B41. Alto plays both tracks in turn on repeat with a
  music volume slider. #257 detail: the hub music makes the visualiser move but
  no sound comes out; his Qobuz ("gbz") app makes sound but the visualiser
  does not move. Monitors: one screen now, often 2-3 more; build (a) pop any
  app out onto another screen first, (b) one window per screen later. B40 key
  Alt+V, whole-wallpaper beat pulse plus edge glow, PanelForge-style parallax.
  B20 widgets: weather, now playing, calendar, notes, disk, network, Jan,
  clock/alarms, each editable (what it shows, size, colour). Groups: drag an
  app onto another like a phone folder, home and sidebar. B41: Board-style
  draggable, resizable panels that remember their layout. Do not close Forge
  for the power measurement for now.

## Sakura (ejb-55) handoff, 2026-09-27 evening
Done + committed: **B27 persona names** (bf9e727 plus crew.py/notes_hook.py
outside git): every crew member gets a name from apps/claude/names.py, and
Claude-app sessions keep their tab name. Hook header "you are Sakura
(ejb-55)", notes "#12 Rika (ejb-34) -> everyone", Board labels and alerts.
Details in apps/board/WIP.md. **Claude app auto-archive** (Emerson: archive
conversations in no folder after 2 hours; next commit after bf9e727):
Settings > Apps hours (default 2, 0 = off), an Archived group with ↩. Details in
apps/claude/WIP.md. Both need a Forge restart to be seen live. Found, not
mine: apps/claude check_enjoy_ui.py "a new task starts with the last picks"
fails on HEAD too; the next Claude-app session should look at it.
Later: that check's failure is fixed (2129f37: parallel saves clashed on one
temp file). Terminal split panes is briefed, not started, for account
"second": sessions/2026-09-27-terminal-split-panes.md. Stopped at 90% of
the 5-hour window and 95% of the week.

## ejb-d1 power handoff (2026-09-27, #185 / #189 / #199)

Emerson: "i want forge to use less power somehow", "is arch really draining
my battery or is it the way i use it", "claude inside forge is way less
efficient than claude in terminal". Done and committed:

- `7840934` Claude panel draws streamed text in 100 ms batches instead of
  re-parsing the whole reply on every word (`apps/claude/static/claude_common.js`).
  Check `tests/browser/claude_stream.html`: 60 deltas went from 60 redraws to 3.
- `c15a323` New setting `battery_fps` (Settings > Speed, "Frame rate on
  battery", default 30). Unplugged, the hub caps frames at
  min(max_fps, battery_fps) and sends it to every open app; plugged in,
  max_fps alone. forge.py stats gained `plugged` (mains adapter), so a battery
  held at a charge limit still counts as plugged. The Power app got an
  "On battery" slider under Frame rate. Checks:
  `tests/browser/hub_battery_fps_harness.js` (9), apps/power tests (138),
  `tests/test_fast_close.py`.
- `3b2ccf3` Desktop particles follow the battery cap too (`desktop/particles.py`
  polls the adapter every 5 s). Checks: `test_desktop_particles.py` (7) and
  `desktop_particles_harness.js` (9).
- Verified: the full `tests/browser/run.sh` gave 513 PASS and 0 FAIL, the
  59 hub/desktop pytest tests passed, and the Power card was screenshotted and
  looked at. No looks changed: at 30 fps on battery, particles keep moving.
- **Not verified live:** these need a Forge restart (hub, forge.py, the
  Claude page), and the desktop particles need one log out and back in. The
  unplug switch itself has not been seen on the real machine (needs the
  charger pulled).

What was measured (on the charger, Performance mode, 5+ Claude sessions and
Jan running, so the numbers are noisy): Forge's page process used 59% of a
core over 20 s, and forge.py's main thread 21% (GTK drawing the page's frames).
The graphics chip was idle only 14% of the time. RAPL package power was 26.5 W
over 10 s. Runtime power management was "auto" on all 24 PCI devices. The
Power app already switches to Battery saver when unplugged (5.7 W against
16 W, see apps/power/WIP.md). Answer to #189 (reasoned from these numbers,
not measured on battery): the Arch setup is tuned. The drain is what runs:
Forge redrawing particles in and behind apps at 60 fps, several Claude
sessions, and Jan's llama-server (about 26% CPU in the Power app's list).

Also done for #225 (`e175d4e` app side, then the hub commit after it):
**Lighter effects** (Settings > Speed, `lite_effects`: Full by default, On
battery, Always). When it's on, looping CSS animations play once and stop
(this also covers the ones the frame cap can't reach, such as the Claude
app's pulsing dot), and the frosted blur goes flat. Particles, the wallpaper
and the visualiser stay. The hub applies `html.forge-lite` to itself and
sends `lite` to every app (`shared/forge_chrome.js`). Verified: hub harness
13/13, `forge_chrome_embedded.html` 13/13, run.sh 529 PASS 0 FAIL, and the
Settings DOM shows the Speed section holding Frame rate cap / Frame rate on
battery / Lighter effects. Not verified: a screenshot of that section (the
page probe photographs before its expression runs) and the live Forge
(needs a restart).

Left for the next session:
3. Measure unplugged, per mode, with Forge open against Forge closed:
   Power app > Measure CPU watts.

**Paste this into a fresh Claude Code session in ~/Forge:**

> Read ~/Forge/sessions/QUICKSTART.md and finish every item under "Left",
> top to bottom. Follow ~/Forge/sessions/README.md "Rules for every session
> in this wave". Load the forge-session, verify and lean skills first. Keep
> each section's brief ## State current as you go.

Rules that still hold: no Forge restart without asking Emerson (his Forge
is running); Jan is shared; nothing installed without his pick; headless
checks only, no GPU renders. Helpers (subagents) only when he asks.

## S18 (ejb-55) handoff, 2026-09-27 morning: read first

Brief `sessions/2026-09-27-S18-quickstart-tools-music.md` (its State says
what is done and checked). Done: music pause/step-aside fast (ea5b75d),
desktop particles settings (8b8f1e5), A7 was already done. Acchan voice done
(🎤/🔈, Kokoro + whisper.cpp already here). Sliders done (particle size/speed/frame
rate, tint strength, drift length). Widgets + Relax done (B20). Left, in order: then B20 widgets and B27 names after
Emerson answers. ejb-94's work is in `2026-09-27-S17-board-fps-aistudio-acchan.md`.

## S14 (ejb-d3) handoff, 2026-09-27 afternoon: read first

Brief: `sessions/2026-09-27-S14-leftovers.md`. Done + committed: Claude app
sizes (bfbe4fe), tile taglines (f630fb0), music honk fix + Folder button
(1347cb6), leaner crew board (~/.claude/skills/crew, not in git). Needs a
Forge restart to be seen: the music fixes. Left, in order, one fresh session
each (usage: run at most two sessions at once; start fresh before ~150k
context, measured 2026-09-27 as the main usage drain):
1. B32 Board app pass: DONE by S17 (ejb-94), commit b07c57e: FYI notes,
   grouped replies, search, desktop alerts. See apps/board/WIP.md.
2. B38 desktop particles steps 2-6: `sessions/2026-09-27-S16-desktop-particles.md`.
3. B39 Power app FPS slider: DONE by S17 (ejb-94), commit 1344f6a. Setting
   `max_fps` (Settings > Speed, and the Power app's Frame rate card).
   shared/forge_framecap.js caps the hub, the apps and desktop particles. GNOME
   has no whole-screen frame cap; the refresh rate (Power modes) is the lever.
4. Godot template leftovers (textured ground/props, Blender->Godot demo):
   `docs/plans/PLAN-blender-godot-upgrade.md` "State 2026-09-27".
5. B27 a distinct persona name per session.
6. Emerson #189 / #199: measured and first fixes done by ejb-d1, see
   "ejb-d1 power handoff" at the top; what is left is listed there.
7. B40 more effects options, above all for Background mode (Alt+B: just the
   wallpaper, particles and visualiser; hub/index.html "background mode").
   Emerson (2026-09-27): "i want the setting or option for more effect and
   stuff especially for when im in alt b". Scope is not pinned yet: ask him
   which effects he means before building. Settings live in the table in
   shared/forge_theme.py (the "Background mode" group), so new options are
   table entries, not markup.

## Current left list (S17 ejb-94, 2026-09-27, read this first)
Done and committed by S17: B32 Board, B39 frame-rate cap, Files restore/
extract/compress/PDF thumbs, Terminal log token, Code chat panel, Claude app
in-page popups (ForgeDialog) plus the same-account flag. Details and checks:
`sessions/2026-09-27-S17-board-fps-aistudio-acchan.md`.

**Emerson's steps:** restart Forge (the Board, frame cap, Files and Claude
popups show after it); sign the Claude app's "second" profile in with his
other subscription (today it's the same account as default, so the meters
match); log out and in once for the desktop-particles extension; answer B41
(AI Studio: cramped when small, draggable panels, or both?).

**Next free session (ejb-fe stopped at 96% usage; B42 step 1 is done: headless shells plus tiered coding prompts; resume from `sessions/2026-09-27-ejb-fe-acchan-local-claude-code.md` and apps/acchan/WIP.md), in order:** the rest of B42 Acchan as a local Claude Code;
~~the xterm search add-on~~ (done by ejb-83, see apps/terminal/WIP.md); B41 once answered; ~~converting the ~38
remaining native popups to ForgeDialog~~ (done by ejb-83: all 40, tests/check_dialogs.py);
then Terminal split panes, shells surviving a restart, Files drag in/out.

**ejb-55:** Acchan voice (TTS/STT), Settings sliders for everything, B20
widgets plus a relax mode (needs Emerson's answers), B27 persona names.

**Nobody yet, needs Emerson's go:** B40 Alt+B effects;
A22 multiple monitors; a Godot character pick; the Alto soundtrack download.

## S17 (ejb-94) new asks from Emerson, 2026-09-27 evening
Brief: `sessions/2026-09-27-S17-board-fps-aistudio-acchan.md`. Both wait on
Emerson's answers to the questions listed in that brief.
- ~~B41 AI Studio UI resizing (apps/ai-studio).~~ Done 2026-09-27: draggable, resizable cards (see apps/ai-studio/README.md 'Panels').
- B42 Acchan as a local Claude Code: terminal / browser / documents / PDF,
  each visible or headless (a toggle), typing into terminals, and a
  system prompt tiered for 0.8B/2B/4B/9B. Emerson's words and a 4-step start
  are in the S17 brief's "Next session" section. Voice (TTS/STT) is ejb-55's.
- Tools leftovers done by S17 (Files restore/extract/compress/PDF thumbs,
  Terminal log token, Code chat panel). Code's Restricted Mode was already
  fixed (S11) and is re-checked 14/14. Emerson said yes to the xterm search
  add-on: it's the first leftover in the S17 brief.

## Left after the 2026-09-27 wave (S11 Kiln, S12 Hagane, S13 Suzu): do these first

Updated by Hagane (S12) 2026-09-27 ~01:20. Ledger with Emerson's words and
state: `sessions/2026-09-27-S12-hub-apps-wave.md` (B-items) and
`sessions/2026-09-27-S13-apps-finish.md`. Everything done is in local git.
**Needs a Forge restart to be seen:** music play/pause + background start,
visualisers, particles fix, fold-on-button, draggable popups, Jan Tune's new
port 8461, the Board jump buttons.

In order (hub items: `hub/index.html`, checks in
`tests/browser/hub_music_fix_harness.js`, run `tests/browser/run.sh`; never
leave a headless Chrome running: `pgrep -fc "[-]-headless=new"` must be 0):
0. **B34 GPU/CPU while Forge isn't seen**: done by S15 (ejb-35), commit e0d246f, checked off screen; **live check left** (needs a Forge restart; steps and findings in `sessions/2026-09-27-S15-quickstart-hub.md`). How it works: GNOME sends a fully-obscured event ~4 s after the window is hidden; forge.py then unmaps the page, WebKit marks it hidden, animations stop, cava stops, music keeps playing. Setting: Speed > Rest while Forge is hidden.
0b. B37 wallpaper apply on GNOME: DONE 2026-09-27 (commit 0271f54). The desktop setters are per desktop, GNOME uses gsettings light+dark, and Forge follows GNOME's picture. Still to check live: pick a wallpaper in the Wallpapers app with "Desktop" and with "Both".
0c. **B38 particles on the desktop**: done by S15 (d001ad3). Left: Emerson logs out and in once, ticks Wallpapers > Particles on the desktop, and checks they sit behind the windows. Also done: particles keep drawing behind open apps (afb11d5, setting Particles behind open apps).
1. B32 Board app: DONE (S17, b07c57e).
2. B7 background effects: done + checked by S15 (277d483): Settings > Home screen, 'Wallpaper follows the pointer' and 'Time-of-day tint'.
**Next session bundle (Emerson 2026-09-27: "save this widgets for a next session alongside the efficiency and power usage")**: B20 home widgets (ask the 8 questions at the end of the S15 session first; they are listed in sessions/2026-09-27-S15-quickstart-hub.md), plus efficiency and power: #185 the Claude app inside Forge (87% of a core measured while streaming), #199 making the Claude manifest/handoff work cheaper, #194/B39 the frame-rate slider in the Power app, and "I want forge to use less power somehow". ejb-d3's measurement (#201): the usage drain is several sessions at once and long contexts, so one or two sessions and a fresh start before ~150k context.
3. B4 Now playing: done + checked by S15 (b57fbf4): each row has prev/play/next and its own volume.
4. B20 home widgets and layouts: a widget registry, drag and resize, saved layouts.
5. B18 speed: done by S15 (b6596c0): apps behind another app rest like a background tab; probe tests/browser/hub_speed.py. Next speed win is the Claude app page (Emerson #185).
5b. DONE by S17 (1344f6a), needs a Forge restart to be seen. Was: **B39 frame-rate slider in the Power app** (Emerson #194: "let the power app control the fps ... only render frames like 1 fps or 30 fps with a slider"): a Forge-wide cap for its own animations (particles, visualiser, games through forge_chrome.js's frame wrapper), 1-60 fps, and find out whether a system-wide GPU cap is possible on GNOME. Ties in with the older A26 frame-rate-cap question.
6. **A22 multiple monitors** (Emerson 2026-09-27, asked again: "make it work with multiple monitors"; his idea, which is optional: one Forge window per monitor with linked sub-apps). At minimum: open on the pointer's monitor, full screen fills the monitor the window is on, pop an app out into its own window on another monitor, and keep animating on a monitor that is visible but not focused (see B34). Kiln's notes are in the S11 brief. Then A5.
7. S14 (ejb-d3) has B14 Claude sizing, tile taglines, Godot leftovers and B27 names; see its brief.
Done in the 2026-09-27 wave: see the S12 brief State.

## Needs a Forge restart to be seen (all done and checked off screen)
Now playing on the music button, hide/archive, the dock and popups, full
screen fixes, background start (Hub); the Claude app's Enjoy layout and
roadmap, image paste, avatar off, usage bars (Chat); Files, Terminal and
Code (Tools). Demo path for Emerson: `sessions/DEMO.md`.

---

## Hub (S7): brief `sessions/2026-09-26-S7-forge-polish.md`

Done and checked: A4 background start, A6 hide/archive, A9 + A27 + A30 Now
playing (music button controls app media, desktop players and background
music; music to 200% with levelling; steps aside while an app plays),
A13, A16, A23 dock, A25 popups, A26, A33.

### Left
1. **A7 Settings with sections and sub-pages.** `apps/settings/` renders
   `shared/forge_theme.py` SETTINGS by their `group`; give groups a
   sub-page each (a list of sections on the left, the section's settings on
   the right), searchable, nothing removed. Check: apps/settings tests +
   headless screenshot; `tests/test_hub_*.py`.
2. **A14 zen mode** — DONE 2026-09-26 apart from its Settings (see PROGRESS.json session_2026_09_26_zen_and_view_media_work). Was: (S2's A4, promoted): home without tiles/dock/bar
   (wallpaper, big clock, focus timer, one-line intention, optional ambient
   sound through `Music.play()/pause()`), a bar button and a key enter it,
   Esc leaves. Settings for what shows. Check: a new `tests/browser`
   harness block + screenshot.
3. **A22 multiple monitors + pop-out**: Forge opens on the monitor the
   pointer is on, full screen fills the monitor the window is on, an app can
   pop out into its own window (a manifest-free forge.py feature: a second
   Gtk window hosting that app's URL). Same on Hyprland and GNOME. Check:
   unit tests for the monitor choice; a live test copy of forge.py on its
   own socket (see A4's check in the brief).
4. **A5 speed**: measure hub first paint and app open times before and
   after (write the numbers down), fix the worst.
5. **A2/A3 polish and embarrassing-stuff sweep**: the helpers' findings
   are below under "Polish findings"; then S2's leftovers (A12 overview
   check, A10 home declutter, S2's improve-next list in its brief).
6. Now playing gap: pages inside the Browser app are native views, not
   frames, so their media is not listed. forge_views.py could report each
   view's media (run a small script in the view, like forge_media.js).

## Chat (S8): brief `sessions/2026-09-26-S8-claude-enjoy-browser.md`

All done and checked: A8, A15 Enjoy layout, A21, A24, A28 roadmap, A29, A32.
Improve-next list in `apps/claude/WIP.md` (Task* tools for plans, model
pickers in the Enjoy task view, a date strip on the roadmap, drag loose
tasks onto a project).

## Tools (S9): brief `sessions/2026-09-26-S9-terminal-files-code.md`

Done and checked: A17 Terminal, A18 Files. A19 Code done except one gap.

### Left
1. DONE (S11 9a58241, re-checked by S17 14/14). Was: **Code's Restricted Mode banner** still shows (`apps/code/WIP.md`
   "Open" #1). Emerson's call: accept it, or keep hunting. Ask him first.
2. After a Forge restart: open Files, Terminal and Code inside Forge and
   screenshot them; try `claude` in Terminal with an image on the
   clipboard (Ctrl+V).
3. The "Improve next" lists in `apps/terminal/WIP.md`, `apps/files/WIP.md`,
   `apps/code/WIP.md`.

## Older briefs (2026-09-25) waiting on Emerson's picks
- S4 A31: a real character for the Godot template (board note 24, options
  1-4; S4 recommends 1, Quaternius).
- S5 A26: frame-rate cap (note 28: built-in Forge cap and/or MangoHud) and
  A19 Webtoon question (note 7).
- S3 A7/A20: the Alto soundtrack download (note 30, about 220 MB into
  ~/Music/Alto; S7 counted A20 as the go-ahead, but the disk is short, so
  confirm first). S3 A6 not started (see its brief).

## Polish findings (helpers, 2026-09-26 18:00)
- Fixed: hub error cards for an app that is missing or not answering now
  say so in plain words (hub/index.html, the error card lines; the old
  jargon about virtualenvs and backends is gone). run.sh ALL PASS.
- Swept clean: every app's label/tagline, TODO/FIXME/lorem/debug text in
  apps' pages, all-caps copy (only MediaForge's and NovelForge's two-tone
  wordmarks, which are deliberate), hub colours and contrast in all looks.
- Reverted: the apps helper renamed Arcade's "Phosphor" wordmark to
  "Arcade", but Phosphor is its deliberate codename (README, MANIFEST), so
  it is back.
- Ask Emerson: "Pixel Forge" is two words while the other Forge apps are
  one (NovelForge, PulseForge...). Rename, or is it deliberate?
- To do: a few tile descriptions are cut off mid-sentence on the cards
  (Jan Tune, Board); shorten those tagline strings in their forge_app.json.
  (2026-10-01: looks done already. The longest tagline is now 46 chars, and Jan Tune's reads
  "Find each Jan model's fastest settings". No card screenshot taken.)
- Demo check: hub Python tests 60 pass, browser run.sh ALL PASS, the Media
  app plays through a video element that Now playing sees.

## ejb-95 GPU easing, Alt+V fixes and real-depth 2.5D handoff (2026-09-29)

Emerson asked for: Forge and the desktop layer easing off when the GPU is busy (visualiser off, then fewer particles, then 25 fps, particles never under 20), battery values chosen by Claude, Alt+V at full refresh rate, the Alt+V/Alt+M bugs fixed, 2.5D without a restart, a better 2.5D/3D, and less GPU when nothing is seen. Pre-edit copies: `backups/2026-09-29-gpu-ease/` (includes his `settings.json`).

**What changed**
- `shared/forge_gpuload.py` (new): reads every other program's GPU busy time from `/proc/<pid>/fdinfo` (DRM fdinfo, no root), leaves out Forge's own WebKit processes, gnome-shell and the video engine, and turns it into level 0-3 (up at once, down one step after 10 s of calm). `shared/gpu_heavy.json` is the registry: friendly names and programs that count as heavy (games). Run `python3 shared/forge_gpuload.py` to watch it live.
- `shared/forge_power.js`: `values(theme, onBattery, {gpu, battery})` now applies the ladder: level 1 visualiser off, 2 half the particles, 3 max 25 fps (particle fps capped at 25, never pushed under 20). On battery the visualiser is off unless `battery_visualiser` is on; at or under `battery_saver` % it goes to level 3. `paired()` is the old pairs-only resolver.
- `shared/forge_theme.py`: new Speed and detail settings `gpu_ease`, `gpu_ease_note`, `battery_particle_fps` (20, min 20), `battery_visualiser` (off), `battery_saver` (20%); `particle_fps` and `desktop_particle_fps` get the battery twin; new defaults `particle_fps` 30, `battery_particles` 0.5. 2.5D: `wall_3d_mode` (depth / layers), `wall_3d_drift`; the theme now carries `wallpaper_depth`.
- `forge.py`: the stats push carries `gpu` every 3 s; `hub/theme.js` is watched and the 2.5D layer keys are pushed into the running hub when `forge_layers` finishes (**the 2.5D-needs-a-restart bug**); Alt+V/Alt+B/Alt+Z give the hub's view the keyboard focus.
- `hub/index.html`: the Alt+V fixes (cause: keys Alt+V does not use sent focus to the hidden home search box; a focused control in the closed popup; an app frame holding focus). Alt+V/Alt+B now take the focus back, the search box is never focused in background mode, Alt+M in Alt+V opens *and* closes the popup, the popup no longer closes when a dropdown opens (window blur), H/?/F1 show the full key list wrapped. Alt+V runs uncapped (60 = screen rate) whatever the plug or the load. Easing from `forgeSetStats`, with a one-line note at the top.
- `shared/forge_depth.js` (new) + `Depth3D` in the hub: real-depth 2.5D, a WebGL shader ray-marching the depth map (16 steps), the cut-out pinned at its own depth on top, pointer + slow drift + beat, draws only while moving. Drift stops on battery and under load. Falls back to two layers without WebGL.
- Desktop: `desktop/particles.py` samples the GPU and battery every 5 s and passes `gpu_level`/`battery` in the theme; `particles.html` and `forge_desktop.js` apply the easing (the desktop visualiser goes off too). The GNOME extension writes `$XDG_RUNTIME_DIR/forge-desktop-under.json` with the screens a maximised or fullscreen window hides; `particles.py` rests those screens (before, a maximised window never counted, because the top bar and dock left the desktop "partly visible").

**Verified**
- `tests/test_forge_gpuload.py` 8 passed; `tests/test_speed_detail.py` 15 passed; with desktop_particles, forge_layers and hub_fx: 45 passed (dossier venv).
- `tests/browser/run.sh`: the new `hub_ease` block has 26 PASS: the ladder, the note, Alt+V at 60 under load, arrows and numbers still working after a focused search box, after an unused key and after the popup, a dropdown keeping the popup open, Alt+M closing it, battery 30/20/half/no visualiser, low battery 25 fps, real depth mounting and drawing, Two layers turning it off. The rest of run.sh passes.
- The live meter read other programs at about 6% on this laptop. The extension passes a syntax check (`node --check`).

**Not verified / not done**
- `hub_ease` "moving the view bends the picture": **fixed 2026-09-30 (Chihiro, ejb-d5)**. It was the check, not the renderer: it now reads the whole middle row and passes (run.sh hub_ease 27/27 PASS). Real-depth screenshot with his real wallpaper done too (headless, software WebGL): it bends correctly, see docs/library/forge/2026-09-30-real-depth-check.md. The whole ejb-95 job is still **uncommitted** (hub/index.html, shared/forge_power.js, forge_theme.py, the new forge_depth.js and forge_gpuload.py, run.sh, harnesses): Emerson decides whether to commit it.
- Nothing seen in the running Forge: **Forge needs a restart** and **the extension needs a log-out and log-in** (GNOME Wayland reloads extensions only then). No screenshot of the real depth yet.
- Emerson's saved values were **not** reset yet (his settings.json has max_fps 48, particle_fps 25, particle_amount 1.75, desktop amount 2.0, desktop visualiser 40 fps). The new defaults only apply to settings he never changed. Planned values: max_fps 60, particle_fps 30, desktop_particle_fps 30, desktop_visualiser_fps 30, particle_amount and desktop_particle_amount 1.25, battery_fps 30, battery_particle_fps 20, battery_particles 0.5. Set them with `python3 shared/forge_theme.py --set key=value` (backup already taken).
- Levels 25 fps on a 60 Hz screen paces unevenly (every 2nd or 3rd refresh); 30 would be smoother if Emerson agrees.
- Not built: "pause when idle" (GNOME already stops frames when the screen blanks; the lock screen turns the extension off). `forge_layers.py` could also save the subject depth so the hub skips its one-off sampling.

## forge_media "with its length" flake (Kohaku ejb-ae, 2026-09-30, stopped at the usage limit)
- **Fix applied 2026-10-01 (Mei, ejb-c6):** before pressing play, `forge_media_parent.html` now waits until the child's `<audio>` knows its length, pacing the wait with fetches. A pending fetch pauses Chrome's virtual clock, so the wait runs in real time. **Verified:** 7/7 standalone (4 of them with every core busy) and a full `run.sh` with 826 PASS, 0 FAIL. **Not verified:** that the flake is gone, because it never failed on demand before either.
- Seen once: in a full `tests/browser/run.sh` run, `forge_media` FAIL "with its length :: 0" (the only fail in that run; hub_ease passed after Chihiro's fix).
- **Verified:** run on its own it passes 9/9 three times in a row, and 4 more times with all 12 cores busy (`python3 -c "while 1: pass"` per core). So the feature works; the check is flaky and I could not make it fail on demand.
- **Reasoned, not verified:** the check waits 30 × 100 ms in Chrome's *virtual* time (`--virtual-time-budget=6000` in run.sh), while the tone's length (metadata) loads in real time. When the laptop is busy with other work, the length can arrive after the virtual wait is over. Likely fix, in `forge_media_parent.html` only: wait for the child's `<audio>` `loadedmetadata`/`durationchange` event (resolve at once if `duration > 0` already) instead of counting timer ticks, then check the latest report. Run it standalone and in a full run.sh before calling it fixed.
- No files were changed. Claims released. Do not commit ejb-95's uncommitted GPU-easing work with it (Chihiro's note: that is Emerson's call).
- Coordination note: Chihiro (ejb-d5) and I both picked the hub_ease item at once. Before starting a QUICKSTART item, `crew claim` its files and post one line on the forge board.

- (2026-10-07) Copy the interface of Enjoy (https://enjoy.dev/, agent-orchestration desktop app) for the Claude app, "for some other day". Mission Control (overhaul wave) borrows its ideas first. Emerson, same day: Mission Control taking Enjoy's good features may make the full copy unneeded; check after the wave before building one.

- (2026-10-07, **done** be02b98, see 2026-10-02 item 6) Claude app: typing /compact in a Forge tab reaches Claude as plain text and does not compact. Make /compact work from the panel (or offer a "fresh session from handoff" button).

- 2026-10-07: Mission Control icon -> something cool based on the Claude logo; Jan Tune vs Power icons too similar, make app icons cooler (in overhaul HANDOFF.md).
- 2026-10-07: after the overhaul wave, a dedicated power-optimization run (Forge GPU still high with an app open; measure live after GNOME re-login, AC vs battery).
- 2026-10-07 (done): screenshot and record keys. GNOME's built-in snip tool is bound to Super+Shift+S (snip, opens in screenshot mode) and Super+Shift+R (opens in record mode), on top of the existing Print and Ctrl+Shift+Alt+R, set through `gsettings org.gnome.shell.keybindings show-screenshot-ui / show-screen-recording-ui`. **Verified:** both keys pressed through ydotool opened the UI in the right mode (seen on a live screenshot). Ctrl+Shift+S/R were left alone because apps use them for Save As and hard reload. Shots save to ~/Pictures/Screenshots and the clipboard; recordings save to ~/Videos/Screencasts.

- Eighty Six (Emerson, 2026-10-07 22:10): park building; he'll dedicate time later. Wants an amazing guide + handoff + roadmap from 0.1 to beta (task 65). Power/performance testing runs last, after everything else.

## AI Studio: 2026 image/video models (2026-10-08)

Brief `sessions/2026-10-08-ai-studio-new-models.md` (for a fresh session on
"default"); research in `docs/library/ai-studio/2026-10-08-new-image-video-3d-models.md`.
Compact models (Z-Image-Turbo, FLUX.2-klein 4B, Wan2.2 5B video) to download
after Emerson OKs the disk use; big ones (Qwen-Image, Wan 14B, LTX-2.3/2.5,
HunyuanVideo 1.5) listed but not downloaded; 3D worlds (HY-World 2.0) checked
for whether they can run here at all.
Added later the same day: AI Search channel findings
(`docs/library/ai-studio/2026-10-08-ai-search-channel-findings.md`: Qwen-Image
2.1 Q3 GGUF, MiniMax H3 GGUF, Ideogram 4, PiD, LTX 2.5). Emerson's asks:
every model is a press-to-download card, rebuild AI Studio properly ("made it
with poor Opus 5.0"), rebuild whatever doesn't work, and treat video and 2D
animation as the main win. All of this is in the brief's update section.
Status 2026-10-08 (evening): **AI Studio rebuild done** by crew ai-studio
(details apps/ai-studio/README.md "Rebuild (2026-10-08)"). Open: Emerson's OK
for GPU test runs; Close app + reopen AI Studio to load the new backend;
whether to bring back draggable panels.
