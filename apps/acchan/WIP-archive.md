# acchan WIP archive

Sections moved verbatim from `WIP.md` on 2026-10-07 (overhaul helper-5) to keep the live WIP short. Nothing was rewritten or deleted; original order kept. The full pre-move file is in `~/Forge/backups/2026-10-07-overhaul/wip/acchan-WIP.md`.

## Status (2026-09-23, session 2)

Emerson's chat log showed: a made-up model name ("Qwen3-52B"), labels jumping
between tiny and small, "open a new firfox window" doing nothing, the 0.8B
printing raw `<tool_call><function=...>` text, and a story repeated word for
word. He asked (verbatim): "make is betetwr add more tools amke it better at
naturla language make it betetwr with models and stuff", then "i wnat th e0.8
to work almot perfectly in tools and high context and remebring and symursii
its mery for the chat so it dont forget and also able to ocde and use terminl
and then if th 0.8 can handle it then make it so that it cna handle the higher
models even beter and better", then "also fix th efullscrene makign the
backgroun balck" ("nah just the background": the app works, the wallpaper
behind it goes black). Asked "how should it pick a model?" he chose **"One
model, stays loaded"**.

What changed (backups in `~/Forge/backups/2026-09-23-acchan-tools/`):
- **One model per chat** (agent.py, llm.py, conversation.py): starts on the
  0.8B with tools, steps up after two failures and stays up (`conv.tier`).
  Menu: "Auto (one model)", "Switch per message" (old ladder), or a fixed size.
  Reply labels now show the size of the model that answered (0.8B/2B/...).
- **0.8B gets tools**: own short rules (`RULES_TINY`), up to 2 toolsets, 6
  steps; Qwen XML tool calls parsed even when no tools were offered; leftover
  tags never shown; the "Let me do that" hand-off removed.
- **Plain language**: `spelling.py` typo fixer; stories/jokes/plain questions
  go to chat without tools; "this" no longer means the screen; "what model"
  answered from settings; fast paths for "new firefox window" and "X and tab".
- **Memory**: rolling chat summary when the history outgrows the budget
  (tiny 12000 chars; the 0.8B's Jan ctx is 20000 tokens), long-term facts via
  remember/recall/forget, newest 15 in every prompt. Repeated replies retried once.
- **New tools**: what_time, set_brightness, lock_screen, wifi, bluetooth,
  weather (wttr.in), remember, recall, forget (70 tools total).
- **Fullscreen background (hub-wide fix)**: inside the hub, the Full screen
  button no longer takes WebKit element fullscreen (it lifted the app over a
  black backdrop, hiding the wallpaper). `shared/forge_chrome.js` asks the
  hub, and the hub asks `forge.py` (`{"window": bool}` on the `forge`
  message channel) to fullscreen the window. Esc/F11 from the window resets
  the app's button (`chrome-state` message). **Needs a Forge restart**
  for the forge.py half; until then the button only hides the sidebar.

### Verified (real output)
- `tests/`: 58 passed (20 new, written first: the log's messages, XML calls,
  sticky tier across turns and after a step up, switch mode, repeat retry,
  summary folding, memory tools, new tools). black clean, pyright 0 errors.
- Hub: `tests/browser/run.sh` ALL PASS, incl. new `forge_chrome_embedded`
  (no element fullscreen, window asked for, chrome-state reset). Hub script
  tests (`python3 tests/test_*.py`) all ok. forge.py pyright: same 4 gi
  import errors as before.
- Live, scratch server: "what model is this?" -> "I'm running on
  qwen35-0_8b-spectralquant-calib360-q4_k_m, the 0.8B model..." (0.14 s);
  "open a new firfox window" -> open_web new_window, Firefox window opened
  (0.01 s). Real tool calls: wifi "Connected to meloncherry (77%)",
  bluetooth "on; connected: nothing", weather Perth, set_brightness 17 (its
  current level). Screenshot: `~/Forge/outputs/shots/acchan-model.png`.
- Eval on the real 0.8B (`tests/eval_prompts.py tiny`, 32 cases): see the
  **27/32 first call correct, 647 s total (about 20 s a request)**. Before
  this session the 0.8B had no tools, so it scored 0 on every tool case
  (reasoned from the code, not measured). Misses: PDF question -> find_files
  first (then ask_document); "remind me in 20 minutes" -> notify (wrong: no
  timer); clipboard copy -> get_clipboard then set_clipboard; close dolphin ->
  list_windows then close_window (fine in practice); "remember that my exam..."
  -> no tool call at all (the memory toolset was offered; needs a fast path or
  example). Only the remind_me and remember misses are real failures.

### Not verified
- The fullscreen fix inside the real Forge window (needs a restart of Forge;
  only the browser harness ran). Check: open Acchan, press Full screen, the
  wallpaper should stay; Esc should bring the sidebar back.
- Summary folding with a real model (only the scripted test).
- lock_screen (not run: it would lock Emerson's screen).

## Improve next (ranked)
1. The two real eval misses now have fast paths ("remember that ..." ->
   remember, "remind me in N minutes to X" -> remind_me; unit-tested, 60
   passed; the eval was not re-run). Re-run `tests/eval_prompts.py tiny`
   to confirm (expect 29/32). Also, the 0.8B loops on ask_document (called 3x
   for "find my notes") -- a loop guard for the same tool 3 times in a row
   would stop that.
2. Run the eval for small and medium to confirm nothing regressed there.
3. Restart Forge and check the fullscreen fix live.
4. Streaming reply text token by token.

## Status (2026-09-22, session 1: built overnight, unattended)

Emerson asked for "a perfect AI assistant that can run locally using the
smaller models in my Jan server, in the terminal so I can code with it, and
also interact with computer, files, tabs, documents, videos", with a system
prompt good enough for weak models; Nyarch to work through it; the Claude
Code app and Study Companion inside it; Qobuz "at the very least" but every
app; more catgirl/catboy avatars for Nyarch; Jan settings changed as needed
but only for this app and Nyarch, never his own; everything at once, full
auto, no helpers (sequential), escalate models when stuck; persona Acchan;
full-screen terminal UI. README.md has the architecture.

**Discovered:** the laptop was running **GNOME**, not Hyprland, so every
desktop action goes through `acchan/desktop.py`, which picks Hyprland
(hyprctl/wtype/grim) or GNOME (AT-SPI/ydotool/portal screenshots) at runtime.
QBZ (`com.blitzfc.qbz`) is the installed Qobuz client.

### Verified (real output)

- **Tools on the live GNOME desktop:** `list_windows` (AT-SPI) listed
  Terminal, Jan and Calculator with the active one marked; `whats_on_screen`
  took a portal screenshot and OCR'd the terminal; `browser_tabs` read
  Firefox's session file (17 real tabs); `find_app` resolves file explorer ->
  Dolphin, terminal -> GNOME Terminal, qobuz -> QBZ, steam, spotify.
- **Real end to end, through the OpenAI endpoint Nyarch uses:** "open the
  calculator" opened GNOME Calculator (fast path, 0.28 s); "close the
  calculator window" went through the 2B -> `close_window` -> Alt+Esc focus
  cycle -> Alt+F4 and the window closed (6.5 s).
- **Nyarch compatibility:** Nyarch's own `openai` library inside its Flatpak
  streamed "42 nya." from Acchan for "what is 6 times 7?" (via `calculate`).
  Nyarch's settings now point at Acchan (see `~/Forge/nyarch/MANIFEST.md`).
- **Terminal:** `acchan "what is 1234 * 5678"` -> `calculate` -> 7006652
  (correct). The full-screen app is covered by `tests/test_tui.py` (Textual
  pilot: send, tool card turns into a check, reply, model-size cycling).
- **MCP:** initialize, tools/list (59 tools at the time), tools/call
  `calculate` and `list_windows` over stdio.
- **Page:** headless-Chrome screenshots of the landing view (tabs, status,
  chips) and an open conversation (tool card with a check, reply). The
  composer was then given 44 px clearance for Forge's Close/Full screen
  buttons and re-screenshotted (clear). The terminal app was rendered to a
  picture through Textual's own screenshot, which caught tool cards showing
  their result in place of their title (fixed, re-rendered).
- **Claude app** works end to end (see apps/claude/WIP.md top section).
- **Tests:** `tests/test_core.py` + `tests/test_tui.py`, 39 passed.
  black clean; `pyright --pythonpath ./.venv/bin/python acchan web_app.py
  mcp_server.py tests` 0 errors.
- **Prompt eval** (`tests/eval_prompts.py`, stubbed tools, real models;
  score = the first tool call is a right one):
  - 2B run 1: 16/20. The worst finding was not the score: after
    `whats_on_screen` found a PDF, the 2B *invented* what page 3 said. Fixed
    by making `whats_on_screen` return the page text itself, plus a rule
    against guessing page content.
  - 2B run 2: 18/20 (misses: "find my notes" -> `list_dir`, "open a terminal
    in my Forge folder" -> three `list_dir`s). Since fixed: companion tools
    (`find_files` with docs), sharper list_dir/find_files descriptions,
    loose folder names resolve ("my Forge folder" -> ~/Forge), and a fast
    path for "open a terminal in X". Re-run below (run 3).
  - 4B IQ4_XS: 6/6 correct before it was stopped, but 50-90 s per request.
  - **2B run 3 (after the fixes, 22 cases): 20/22**; both "misses" were
    valid (media_control play instead of clicking QBZ's Play button;
    launch_app(terminal, ~/Forge) which hands over to open_terminal), so the
    eval now accepts them.
  - **4B Q4_K_M (new model, 22 cases): 21/22, average 30 s per request**
    (was 50-90 s). Its miss answered "list the files" with `run_command ls`.
- **Vision:** `look_at_screen` on the whole screen, through the new 4B and
  the portal screenshot, described Jan's chat window correctly (48 s).
- **Study:** `ask_course` answers from Study Companion's MATH1014 notes and
  tags passages with their topic (e.g. "limits at infinity" -> t5_limits).
- **Claude Code MCP:** registered at user scope (`claude mcp list` shows
  `acchan ... Connected`). Claude Code defers MCP tools, so sessions carry
  only the names; remove with `claude mcp remove acchan -s user`.
- **forge_jan unload fixed** (affects every Forge app): Jan's router wants its
  own LLAMA_API_KEY for /models/unload; `forge_jan.router_key()` reads it from
  the router's environment. Live: the idle 4B unloaded. Test added.
- **forge.py adopts a running backend** (`tests/test_adopt_running.py` passes
  on the new code and fails on the old). All hub script tests pass.
- Note: after Jan restarts, Jan's own app loads **Qwen3_5-4B-IQ4_XS** by
  itself (probably the model selected in its chat window) and re-loads it if
  released. That is Emerson's Jan setup, left alone; switching Jan's chat to
  another model would save about 3 GB of RAM.

### Not verified

- Nyarch used by voice/typing in its own window after the switch (would
  have spoken aloud overnight). Ask Emerson to say or type "open firefox".
- Qobuz control on QBZ itself: `media_control` uses MPRIS; nothing was
  playing overnight, so no player was listed. `press_control` on QBZ's
  buttons depends on QBZ exposing AT-SPI (not checked).
- Firefox tab switching/closing (keystroke route through the address bar's
  "%" search): Firefox was not running.
- Transcripts via Whisper (first use downloads the ~150 MB `base` model into
  MediaForge's cache); YouTube subtitle route not run live either.
- `video_frame` (vision on a video frame; look_at_screen itself works).
- The Forge window itself with Acchan in its sidebar (Forge was not open).
  `forge.discover_backends()` does list acchan on 8451, and the adoption
  path is unit-tested.

### Speed (measured 2026-09-22, i5-1245U, DDR4-3200, same real prompt)

Jan's own llama-server (Vulkan build) on a scratch port, one Acchan request
(system prompt + 9 file tools + one question = 1,760 prompt tokens):

| model / setting | prompt read | generate |
|---|---|---|
| 4B IQ4_XS, 40 layers on iGPU (Emerson's setting) | 41 tok/s | 6.2 tok/s |
| 4B IQ4_XS, CPU, 4 threads | 43 | 8.1 |
| 4B IQ4_XS, CPU, 8 threads | 44 | 9.1 |
| 4B IQ4_XS, all layers on iGPU | 41 | 6.2 |
| 2B Q4_K_M, CPU, 4 threads | 198 | 21.6 |
| 2B Q4_K_M, CPU, 8 threads | 205 | 24.0 |
| 2B Q4_K_M, all layers on iGPU | 210 | 14.3 |
| **4B Q4_K_M (new, via Jan, CPU, 4 threads)** | **81** | **8.2** |

Conclusions: the iGPU never helps generation here (memory is shared, so
bandwidth is the same, and it adds overhead); the IQ4_XS quant was the 4B's
bottleneck (as slow to read a prompt as a 9B would be). Emerson asked to
"download model that will work", so `unsloth/Qwen3.5-4B-GGUF`
`Qwen3.5-4B-Q4_K_M.gguf` (2.74 GB) was downloaded into Acchan's own Jan entry
`models/acchan-4b-q4km/` (reusing the IQ4_XS folder's mmproj, CPU only).
Emerson's own entries are untouched; the IQ4_XS file could be deleted to win
back 2.5 GB, which is his call. Jan was restarted once to register the entry.

**Update 2026-09-24:** Emerson asked for one copy. The Q4_K_M file was moved
into the `Qwen3_5-4B-IQ4_XS` entry (id kept, since Dossier, NovelForge,
PanelForge, PixelForge and nyarch ask for it by name), the IQ4_XS file and the
`acchan-4b-q4km` entry were removed, and `n_gpu_layers` set to 16 of 32 (half
iGPU, half CPU, his request). That split has not been benchmarked; the table
above says the iGPU slowed generation, so measure before keeping it. Jan was
restarted the same day (nothing was using it): disk went from 36G to 39G free and
the 4B now loads with `--n-gpu-layers 16`.

With the prompt cache, a follow-up in the same chat costs only its new tokens
(measured: 19 new tokens), and since the working folder moved out of the
system prompt, a new chat with the same toolsets reuses the cached prefix too.
Not tried: Q4_0 (llama.cpp repacks it for AVX2, likely faster still) and
threads 8 per model (Jan's global preset says 4, which is Emerson's setting;
model.yml `threads` is not passed through by this Jan build).

## Improve next (ranked)

1. **Re-run the eval** (`tests/eval_prompts.py small`) to confirm the fixes
   above, then extend the cases whenever Emerson reports a miss. The eval is
   the tool for tuning prompts: change, run, compare.
2. **Nyarch live check with Emerson** (voice + "open firefox").
3. **Avatars:** Emerson picks from the candidates below; install with
   `python3 ~/Forge/nyarch/add_avatar.py <zip> [Name]`.
4. **GNOME window focus** uses Alt+Esc cycling; the "Window Calls" GNOME
   extension would make focus/close exact. It is an extension, so it needs
   Emerson's review before installing.
5. Streaming reply text token by token (currently each reply arrives whole).

