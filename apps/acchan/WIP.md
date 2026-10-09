## Voice commands and the shared voice service (2026-10-08, Relay task 113, helper-4 Ami)

- `POST /api/voice/command {text, use_model?, source?}` -> `{handled_by: fast|phrase|jan|none, reply, calls: [{tool, args, ok}], ms}` (`acchan/voice_command.py`, route in `web_app.py`). Order: `router.fast_path`, then `acchan/phrases.py`, then (use_model) the agent once, no streaming, 90 s cap, conversation id `voice`. The reply is cut to two short plain sentences.
- From `source: "voice"` nothing risky runs: `risky=True` tools plus any whose name says close/trash/delete/move_path/write/edit/append/run/type/press/keys/fill/click/send/clipboard/forget/convert (`voice_blocked`); the reply says to confirm it in Acchan. In the agent path a `_VoiceAgent` refuses those tools the same way.
- `@tool(..., phrases=[...])`: natural examples with `{param}` slots, or `(phrase, fixed_args)`; risky tools get none (the registry drops them). Declared on apps, media, system, windows and browser tools. Matcher: stdlib, normalises (contractions, fillers like um/please/could you/hey acchan, articles), exact template match scores 1.0, slot-free fuzzy match by difflib ratio, threshold 0.85, slots of at most 5 words and not starting with talk words; number slots must be digits.
- `launch_app`: name and arguments are `shlex.quote`d on the bare-command path (the injection the review found).
- `acchan/voice.py`: speak and listen try the shared voice service first (`POST :8467/api/tts {text, app: "acchan"}`, `POST :8467/api/stt?app=acchan` raw audio, header `X-Forge: 1`; `FORGE_VOICE_URL` overrides) and fall back to the old Kokoro/Piper and whisper-cli paths (kept as `_speak_local`, `_transcribe_local`). `status()` gains `service`. Manifest has `"voice": {"listens": true, "speaks": true}`.
- **Verified**: `tests/test_phrases.py` (30 natural sentences, 20 chit-chat/negative, risky tools phrase-free, every slot is a parameter) and `tests/test_voice_command.py` (fast hit, phrase hit, risky refused from fast path and phrases, blocked/allowed sweep, use_model false -> none, model answer shortened with the voice allow-list, launch_app quoting, service-then-fallback for speak and listen, all faked); whole suite 300 passed. A scratch server on port 18451 answered "what's the time" and "hey acchan could you tell me the time please" by phrase (5-19 ms) and "tell me a story" with use_model false as none. Real round trip through the live shared service: TTS 3.0 s (61 KB WAV), STT heard "Open Firefox.". black and pyright clean (0 errors).
- **Not verified**: the agent path (`handled_by: "jan"`) against a real Jan model (only faked); the page's own mic and speaker buttons through the service in a browser; whether the service's STT answer is always `{"text": ...}` (anything else falls back to whisper-cli). Relay commands as Acchan tools (`acchan/tools/relay.py`, in the Contract) are not built.

## U1 sweep (2026-10-08, Relay task 74; Koharu, Relay task 85)

Changed:
- Page rests and backs off: the status poll returns false while the server is
  away (`ForgeIdle.poll(status, 15000, { backoff: 2, maxMs: 30000 })`); the
  status line reads "Server not answering, retrying" with a red dot, and when
  the server answers again the chat list and the Claude / Study tabs that
  failed to load are fetched by themselves.
- Page robustness: chat list, open chat, delete, settings save, tool list and
  tabs no longer throw on a dead server (a calm note instead; the Settings
  dialog still opens and says the tool list could not be loaded); a double
  click on a chat's ✕ sends one delete; an empty list says "No chats yet".
- Looks: below 1000 px the message box takes its own row (at 760 px it was
  squeezed to a sliver between the model picker and the buttons) and the chat
  list narrows to 200 px; thin themed scrollbars (incl. `::-webkit-scrollbar`);
  new messages and tool cards fade in (180 ms, opacity + transform); the ✕
  fades; code blocks use `var(--bg)` instead of a hardcoded colour; reduced
  motion honoured.
- API: conversation ids must be a plain name (`[\w-]{1,120}`,
  `conversation.valid_id`): an id like `../settings` sent to /api/chat used to
  write the chat over `settings.json`, now it starts a fresh chat; the
  OpenAI route keeps only letters, digits, `_` and `-` of the caller name. A
  corrupt conversation file is a 404, not a 500. /api/settings refuses wrong
  types and unknown choices with 400 (a string `reply_limit` used to be
  stored and break every later reply) and `settings.load()` drops bad values
  from a hand-edited file. /v1/chat/completions answers 400 for messages that
  are not a list of objects or an empty last message; the shell input route
  answers 400 for a body that is not an object.
- New `tests/test_u1_robustness.py` (16 cases, no model runs).

### Critic follow-up (same day)
- A `#c=<id>` link to a chat that no longer exists left the chat list empty;
  it now loads the list (browser check: 24 chats show on `#c=nope`).
- One odd file in the conversations folder (`[]`, `{}`, a bad `updated` or
  `messages`) made `GET /api/conversations` a 500; such files are skipped.
- `Conversation.load` refuses a file whose stored `id` is not a plain name
  (a hand-edited `"../settings"` would have saved outside the folder).
- The `voice` setting must be one of `voice.VOICES` (was any string).
- 3 more tests in `tests/test_u1_robustness.py`; full suite 221 passed.

Verified: pytest 218 passed in the full run except one timing test in
test_shells.py that failed once while headless Chrome ran beside it and then
passed 3 of 3 alone (not touched here). black + pyright 0 errors on the
touched .py files. Headless Chrome on a scratch copy (port 9000, temp data
dir, Jan models dir pointed at an empty temp folder): shots at
760/1100/1500/1920 plus an open chat, Settings, server down and empty list
looked at (`/tmp/u1/G10/shots/after-acchan-*`); hidden 10 s = 0
fetches/timers/rAF, 1 fetch on coming back; server killed: 1 fetch in 0-10 s,
2 in 0-45 s, the status line says so and recovers by itself after restart;
triple click on ✕ (fetch stubbed) = 1 request.
Not verified: anything that makes Jan answer (not allowed in this sweep).
Page changes reach Forge on the next reload; the .py changes on the next
restart of Acchan's backend (acchan.service or Forge).

# Acchan: work in progress

## Status (2026-09-27, ejb-fe then ejb-34): B42 "local Claude Code"

Emerson: headless is the default, never ask before running commands, and closing
Acchan must close every headless thing it started; "whatever is best" and
"everything I could want" for the rest. Brief: ~/Forge/sessions/2026-09-27-ejb-fe-acchan-local-claude-code.md.

Built:
- `acchan/background.py`: every background child starts on one long-lived launcher
  thread in its own session with PR_SET_PDEATHSIG. `stop()` kills the whole
  session (a job that moved to its own process group too), so atexit, a crash
  or kill -9 all take everything down.
- `acchan/shells.py`: headless bash on a pty; cd/env/venv carry over; exit code
  from a marker line; job control off (`set +m`) so `cmd &` jobs die with bash
  even on kill -9 (no ctrl+z for that reason). Transcript in DATA/shells/<name>.log.
- Tools (tools/shell.py): shell_run, shell_send, shell_read, shell_list,
  shell_show, shell_close; run_command kept.
- `shell_show` / terminal_view "visible": a gnome-terminal (or kitty) running
  `acchan/shell_window.py`, which follows the transcript and sends each typed line
  (Ctrl+C passed on) through POST /api/shells/<name>/input. It closes when the
  shell ends, and so with Acchan. (Emerson #237: the first version only watched.)
- `open_terminal`: with no command it always opens a real terminal on screen (a
  person asked for one); with a command and terminal_view "headless" it runs in a
  background shell and returns the output.
- `acchan/headless_browser.py`: Acchan's own `firefox --headless` with its own
  profile (DATA/headless-firefox), BiDi on a free port, started on first use
  through background.py. page_* tools use it when no account is named and
  browser_view is "headless" (default); account "main" = Emerson's Firefox,
  "headless"/"acchan" = this one always. New tools: page_screenshot (PNG to
  DATA/shots), close_headless_browser.
- Settings > "Out of sight or on screen": terminal_view and browser_view selects.
- Router: fast paths "run X in the background" (shell bg-<program>, 5 s wait),
  "show me the terminal", "close all the background shells", "close the headless
  browser"; an address plus a reading word, or a message naming a tool, now
  offers that toolset (pages for reading pages).
- `acchan/coding_prompts.toml`: coding rules + command cheat sheet per tier.
- Docs/PDF: no new code needed; read_document/edit_file/write_file already work
  on disk out of sight, open_item is the visible way.

### Verified (real output)
- pytest 191 passed; tests/test_shells.py covers state carry-over, exit codes,
  timeout + ctrl+c, close_all, kill -9 of the parent (plain child and a `cmd &`
  job), typing through the window route, the window script exiting with its
  shell, a real headless Firefox opening/reading/screenshotting a page and gone
  after close_all. black + pyright 0 errors on touched files.
- Live acchan.service after restart: "run python3 -c print(6*7) in the
  background" -> exit code 0, 42; "show me the terminal" opened the window;
  "close all the background shells" -> closed 2. Settings dialog screenshot
  (headless Chrome) shows both selects.
- Live model run before the router fix: 4B never reached the page tools
  (fumbled with window tools, escalated to 9B). Router fixed after that; see
  below for the rerun.

### Context (2026-09-27, ejb-34): "tons of context for my AIs except the 0.8"
- Emerson's own Jan entries are untouched (they already carry jan-tune's winner:
  4B at 32 iGPU layers). Forge apps get copies: shared/forge_jan.long_entries()
  writes `<model>-long` folders (model.yml = the base's, ctx 131072, own name,
  same .gguf, no disk), rebuilt from the base at every Acchan start so jan-tune
  changes carry over. Acchan's small/medium/large list the -long copy first and
  fall back to the base while Jan does not list it.
- History budget follows the model's real window (forge_jan.context_size reads
  the router's preset): (window - 12000 tokens) * 2.8 chars. Live now: tiny 12000
  (fixed), 2B/4B/9B 36400 chars on today's 20000 windows, 333401 once the -long
  copies load. KV memory at q8_0: about 0.75 GB (2B) / 2 GB (4B, 9B) each at 131072.
- Verified: tests (195 passed): the copy, tuning carry-over, fallback, budget
  maths, preset reading. Live: the router re-reads nothing until Jan restarts
  (a reload of the 2B still came up at 20000), so the -long entries switch on
  at Jan's next start. Not restarted by me: Emerson uses Jan himself.
- Live model run after the router fix: the 2B was offered page_open but made up
  an address (secretword.com) for "read file:///tmp/... and tell me the secret
  word". Idea: a fast path "read <address>" -> page_open + page_read, then the
  model only answers.

### Not verified / next
- After Jan's next start: `pgrep -a llama-server | grep -- -long` shows
  --ctx-size 131072 once Acchan uses the 2B/4B/9B.
- Typing in the new shell window by hand on screen (the route and the script
  are tested separately).
- Eval each tier (tiny/small/medium/large) with coding_prompts.toml:
  `.venv/bin/python tests/eval_prompts.py` (Jan is shared; check it first).

## Voice (2026-09-27, S18): 🎤 and 🔈

Replies read aloud (🔈 beside Send, off by default; voice picked in
Settings > Voice) and a microphone that types what you say (🎤, click to
start and click to stop). acchan/voice.py uses what was already installed:
Kokoro (nyarch/forge_tts.py in NovelForge's venv), Piper as the fallback,
and whisper.cpp tiny.en built by the Nyarch flatpak. Verified: a real
Kokoro -> whisper round trip through /api/voice/speak and /api/voice/listen
(tests/test_voice.py). Not verified: a real microphone inside Forge (needs a
Forge restart; forge.py now allows the mic, never the camera). Improve next:
a hands-free mode (send when you stop talking), and speaking while the reply
streams instead of after it.

## Status (2026-09-25, S4 session): apps open again, fast "hey"

Asked: "none of the apps open except terminal when I ask the acchan thing";
"any model, and 4b with think, takes an ungodly time to respond to hey".

- **Apps not opening, cause:** `acchan.service` starts at login before GNOME
  gives the systemd user manager WAYLAND_DISPLAY/DISPLAY, so the backend had
  none. Dolphin (Qt) crashed, Firefox/Chrome said "no DISPLAY"; GTK apps and
  gnome-terminal (D-Bus activated) still opened. `desktop.adopt_session_env()`
  now fills them from `systemctl --user show-environment` at each desktop
  re-check (own values kept, adopted ones refreshed).
- `find_app`: a system app's exact name, then kind words ("browser" = Firefox,
  not Chrome), then fuzzy. Forge apps are entries too (`forge:<name>`, from
  every `forge_app.json`, listed as "Cosmos [Forge]"); launching one asks the
  running Forge over `shared/forge_open.py`'s socket, starts
  `forge.py --app <name>` when Forge is closed, and never starts a second
  Forge beside an old one without the socket (it focuses it and says so).
- **Slow "hey":** greetings (`router.is_small_talk`) get one light call
  (`Agent._small_talk`): the chat's model, no tools, thinking off, last 6 plain
  turns, 200 tokens, no summary call, no step up to a bigger model. A client
  that drops its stream now stops the run (`web_app._sse`, the /v1 stream).
  `/api/chat` takes `small_talk: false` to time the old path.

### Verified (real output)
- `tests/test_apps.py` 22 passed (real .desktop names on this laptop + Forge
  apps), `tests/test_small_talk.py` 19 passed, `~/Forge/tests/test_forge_open.py`
  5 passed, suite 159 passed; black; pyright 0 errors.
- Live, from the service's exact stripped environment: raw `dolphin` dumped
  core, raw `firefox` said "no DISPLAY"; `launch_app('file explorer')` opened
  Dolphin and it stayed up. acchan.service restarted twice, answers 200.

### Not verified
- "hey" not timed with a real model (no model runs this session). Command:
  `for st in true false; do curl -sN localhost:8451/api/chat -H 'Content-Type: application/json' -d "{\"text\":\"hey\",\"tier\":\"medium\",\"thinking\":true,\"small_talk\":$st,\"source\":\"timing\"}" | grep -o '"seconds": [0-9.]*' | sed "s/^/small_talk=$st /"; done`
- The forge.py socket needs Forge restarted once; then
  `python3 ~/Forge/forge.py --app cosmos` should switch the open Forge.


## New toolsets 2026-09-25: pages, blender, godot

`acchan/tools/pages.py` (Firefox via WebDriver BiDi + shared accounts),
`blender.py` (Blender bridge), `godot.py` (Godot bridge and CLI). All
verified live on screen, and the 110 core tests still pass. The router's
keyword lists for them are first guesses; the 0.8B eval has not been rerun
with them. Full story: ../../docs/DESKTOP-REACH.md.


## Status (2026-09-23, session 3)

Asked (verbatim, in order): "look ijast wnat aachan app in forge to work also i dotn relalyw nat it to always have the sound of cat makelave that the nyarch assitnat . btu i wnat it to be abel to do taool calles perfectly evena sa 0.8 b model andneiteh rthe 0.8 and 2 b can opena firfox tab or window anbtu both can see only the first 8 tabs open make it work esaecially make ti so good that the 0,8 works great liek almost perfect", then "i dotn wnat such a small responce that it always give", "also allow thinking with tiggels", "as welle as tlaking to istsle fo r multiple instacnes of it for difefrnt idea idk? or i can chat with multiple models at once?/??", "or of the same model", "i nwat more toodls and for it be able to acte evnwitout them and navigat and stuff".

Causes found in the real chat logs (~/.local/share/forge/acchan/conversations/): ~25 common tab/window phrasings missed the fast path, so the model called launch_app (only focuses the running Firefox) or said "Let me..." without calling anything. browser_tabs returned all 31 tabs but the model retyped only 6-8 and made some up.

What changed (backups: ~/Forge/backups/2026-09-23-acchan-tabs/):
- **Firefox fast path** (router.py `_browser`, `_tab_list`, `_sum`, `_text_doc`): new/another tab or window, "in firefox", "X in a new tab/window", "wikipeida tab" (fuzzy site names), "3 new tabs", private/incognito window, list/count tabs (also as a question), switch/close a named tab, arithmetic -> calculate, "new text doc" -> Text Editor. `open_web(private=True)` added.
- **Lists shown whole**: `@tool(show=True)` (registry.py) on browser_tabs, list_windows, list_dir, list_apps, recall. When the user asks to see a list, the tool's real output is the reply. browser_tabs is compact: "31 tabs open in 1 window", `#12 Title (site)`, 1.9 KB for 31 tabs.
- **No cat talk by default**: persona "plain" (no nya, no emojis); "Catgirl" is a choice in Settings -> Personality. Stored in acchan/settings.py (DATA/settings.json), shared by page, terminal, Nyarch (`GET/POST /api/settings`).
- **Longer replies**: rules no longer say "one short sentence"; chat gets a short paragraph or more, stories 150-300 words, REPLY_TOKENS raised.
- **Think toggle**: checkbox beside the model picker (saved in settings; `/api/chat` also takes `thinking: bool`). Jan's reasoning_content is captured (llm.Reply.reasoning) and shown as a collapsible "Thought it through" block; +2000 tokens budget when on.
- **0.8B sees 8 tools, not 10-20** (was 6; raised after the eval): router.rank_tools scores tools by name/description/example words (+SYNONYMS); schemas and examples narrowed to them (`only=`). Tools the model calls outside the list are added.
- **Said-but-didn't-do nudge** (agent.CLAIM): "Let me.../I've opened..." with no call -> "Nothing happened... call it now (probably X, Y)". Loop guard: same tool 3 times in a row is stopped.
- **Navigate toolset** (new tools/navigate.py): navigate (back/forward/reload/top/bottom/zoom/next tab... as an ACTIONS table), scroll, find_on_page. Fallback: apps always brings the ui toolset, and a rule says "no tool? work the app like a person: app_controls, press_control, press_keys".

### Verified (real output)
- tests: **111 passed** (tests written first: 35 phrasings -> exact fast calls, compound "window and tab", 31-tab list complete and under the 0.8B limit, list reaches user whole even when the model would summarise, persona, thinking toggle, settings endpoint, ranking, claim nudge, 3-in-a-row guard, navigate keys). black clean, pyright 0 errors on all touched files.
- Real session file: browser_tabs on Emerson's Firefox -> 31 tabs, 1894 chars.

### Not verified
- **Eval on the real 0.8B (finished, results saved in `tests/results/`)**: **33/43 first call correct, 780 s** (`2026-09-23-s3-eval-tiny.log` / `.json`; the session-2 run, 27/32, is `2026-09-22-s2-eval-tiny.json`). **Regression on the old 32 cases: 27 -> 24** (compared case by case). Fixed: remind me in 20 minutes, remember that... (fast paths). Worse: find my lecture notes, fix app.py, todo file, calculus limits, terminal in Forge + list files -- all files/code/course tasks, most likely because the 6-tool limit (router.TINY_TOOLS / rank_tools) drops the right tool. TINY_TOOLS was then raised from 6 to 8 at Emerson's request (tests pass); the eval has **not** been re-run with 8, so whether it undoes the regression is unknown. Next: re-run and compare the same way. All the new fast-path cases pass (tabs, windows, wikipeida, sums, text doc). The 10 misses:
  - pull up github in firefox -> browser_tabs; scroll down in firefox -> browser_tabs. **Bug:** the list was then shown as the reply because MORE_TO_DO (agent.py) lacks "pull up/scroll/check". Fix: only show a list when the user's words ask for one (list/show/what/which/how many), not whenever no action word is found.
  - find my lecture notes -> ask_document (wanted find_files); pdf question -> find_files first (then right).
  - fix app.py -> read_window_text, escalated to large, 315 s. Coding on the 0.8B needs files/shell ranked first.
  - todo file -> read_file first, and it wrote to "/home/ejb/~/notes" (a literal "~" folder: check write_file expands ~ in the middle of paths).
  - copy to clipboard -> get_clipboard, then claimed it copied (the claim nudge only fires when no tool ran at all).
  - close dolphin -> list_windows, close_window, then move_window (wandered on after success).
  - calculus limits -> asked which course (ask_course not called); terminal in Forge + list files -> refusal text.
- Page changes (Think checkbox, Personality select, thought block) have **no screenshot yet**.
- open_web new tab/window/private not run live this session (spawn args unit-tested only). Needs the running Acchan server restarted to pick up the code.

## Improve next (ranked)
1. Undo the 27->24 regression (the 6-tool limit, see Not verified), then the list-shown-by-mistake bug, then the other misses; then re-run `tests/eval_prompts.py tiny` and save it into tests/results/.
2. Headless screenshot of the page with the Think toggle and Settings dialog; restart Acchan and try "open a new firefox tab", "list my tabs", "open a private window" live.
3. **Open question for Emerson**: "talking to itself / multiple instances / chat with multiple models at once (or of the same model)" -- not started; ask which of: (a) several Acchans brainstorming in one chat, (b) one message to several models side by side, (c) several copies of the same model with different angles. The laptop runs one Jan request at a time (llm.LANE), so answers come one after another.
4. Run eval for small.

> Older sections moved verbatim to `WIP-archive.md` on 2026-10-07 (overhaul helper-5): from "Status (2026-09-23, session 2)" to "Improve next (ranked)".

## Avatar candidates (not installed: pick first)

- **Live2D official samples** (Free Material License, free download after
  accepting it at https://www.live2d.com/en/learn/sample/): no catgirl or
  catboy; closest are *Tororo & Hijiki* (two cats), male characters
  *Chitose* and *Ren Foster*, and girls *Hiyori*, *Mao*, *Haru*, *Epsilon*.
- **BOOTH** (free or cheap, each with its own terms; needs a BOOTH login to
  download, so Emerson has to fetch them):
  - "maid cat girl" by comte19: https://booth.pm/en/items/5047582
  - neutral cat-eared model (中性的な猫耳モデル) by MUI SHOP:
    https://booth.pm/ja/items/5235765
  - search pages: https://booth.pm/en/search/free%20live2d and
    https://booth.pm/en/search/cat%20ears?tags%5B%5D=virtual+youtuber

## Long files and honest replies (2026-09-27, Riku)
Emerson asked the 4B for an HTML platformer: fourteen write_file calls came
back with empty arguments, then Acchan said "I created a complete HTML5
platformer" and the folder was empty. Cause: REPLY_TOKENS (900 small, 1800
large) cannot hold a whole file, so the call was cut off inside its arguments.
Fixed in acchan/agent.py: a cut-off write is asked again once with
WRITE_TOKENS (6000) more room; still too long, the model is told to write it in
parts with the new append_file tool (acchan/tools/files.py); and a reply after
a turn where every write failed ends with "(No file was saved: ...)".
Verified: 4 new tests in tests/test_core.py, whole suite 199 passed. Not yet
tried live with the 4B through Jan (needs Acchan reopened).
Open: ~/Games/lost_city_simple.py was created (log says so) but is gone now;
nothing in Acchan deletes files, so something else removed it.
Same day, later: Emerson asked for the reply cap to be limitless. Settings
reply_limit (acchan/settings.py) defaults to 0 = no cap, so llm.stream sends no
max_tokens and the model stops by itself or at its context window; a number
caps replies again (agent.reply_budget). The system prompt gained FILES_FULL
(long files in parts with append_file, check a file saved, web game layout,
bash syntax) for every tier with the files/shell/terminal tools, and the short
FILES_TINY for the 0.8B (acchan/prompts.py). Tests: 202 passed.
