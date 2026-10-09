# Session record — 2026-09-12 — autostart and "hey nyarch"

Follow-up to the 2026-09-10 initial setup. Closed the two remaining gaps that
did not need Jan or a live person to finish: the wake word had no "nyarch"
phrase, and there was no way for the assistant to start on its own.

## What the user asked for, verbatim

> "i want nyarch to be opena nd listening at start upa dn set up in such a way
> where i cna jjst say hey nysrahc and it cna navigate my compter and answer
> questions"

Mid-session, unprompted:

> "only using the 0.8b or 2b model for the startup"

## What was found before changing anything

- The primary/startup model (`llm-settings.openai.model`) was already
  `qwen35-0_8b-spectralquant-calib360-q4_k_m` — the small model the user asked
  for. No change was needed there; the secondary/vision 4B was left untouched
  since it only handles screenshots and documents, not ordinary chat.
- `wakeword-on`, `secondary-stt-on`, and `wakeword-mode=secondary-stt` were
  already set from the 2026-09-10 session, so the mic-listening side was
  already armed by settings — the only real gaps were the phrase and the
  autostart entry.
- No `~/.config/autostart/` entries existed at all, for any app.
- Checked whether this machine's Hyprland session actually honors XDG
  autostart `.desktop` files before writing one: `systemctl --user
  list-unit-files` showed `xdg-desktop-autostart.target` loaded and several
  `app-*@autostart.service` units already generated for other apps (NetworkManager
  applet, gnome-keyring agents, etc.), confirming the standard mechanism works
  here without touching `hyprland.conf`.

## What was done

1. Added `"hey nyarch"` and `"nyarch"` to the `wakeword` gsettings key,
   keeping every existing phrase ("hey arch", "hey acchan", "acchan", "arch
   chan", "hey computer") so nothing that worked before stops working.
2. Wrote `~/.config/autostart/moe.nyarchlinux.assistant.desktop`, copied from
   the Flatpak's real exported launcher entry
   (`/var/lib/flatpak/exports/share/applications/moe.nyarchlinux.assistant.desktop`),
   trimmed to one language and marked `X-GNOME-Autostart-enabled=true`. Opens
   the full window, not the `--mini` variant, matching "open ... at startup."
   Validated with `desktop-file-validate`.
3. Launched the Flatpak manually to confirm the new settings don't break
   startup: the window came up, the Live2D avatar loaded, the local web UI
   served all its assets with 200s. Two pre-existing background-thread
   exceptions appeared (`get_models() takes ... but 3 were given`, in both
   `NyarchApiHandler` and `LlamaCPPHandler`) — these are non-fatal (the app
   kept running) and look like a bug in the assistant's own code unrelated to
   anything changed this session; not investigated further since they weren't
   asked about and didn't block anything.

## What is still unverified

- **The wake word firing on real speech.** Settings are correct and the app
  is running; only the user can say "hey nyarch" and confirm it fires. Ask
  them to test with the app focused.
- **Autostart actually firing on the next login.** Can't be tested mid-session
  without logging out. Confirm after the user's next login that the window
  came up on its own.

## Mistakes avoided this time

Last session's notes flagged driving the user's desktop (alt-tabbing through
their windows) as a mistake. This session's manual launch was left alone once
the process was confirmed stable — no clicking through the running window.

## Part 2, same session — "hey nyarch doesn't work" and "open stuff"

### Wake word diagnosis

User reported the wake word "seems like it hears me but nothing gets typed."
Read `utility/wakeword_detector.py` and `window.py` inside the Flatpak
(`.../nyarchassistant/nyarchassistant/`) rather than guessing. Root cause
found in code: `on_wakeword_detected()` in `window.py` only types text into
the chat box if there's a command *after* the wake phrase in the same speech
segment — if you just say "hey nyarch" alone, it correctly detects it but
only shows a small, easy-to-miss toast ("Wakeword detected, no command") and
types nothing. That's very likely what happened, not a sensitivity problem.

Made it more forgiving anyway:
- `stt-settings.whispercpp.prompt` and `stt-secondary-settings.whispercpp.prompt`
  both set to `"Hey Nyarch. Hey Arch."` — primes Whisper `tiny.en` toward that
  spelling instead of mishearing it, for both the quick wake-check pass and
  the full-utterance transcription.
- `wakeword-silence-duration` 1.0 → 1.5, so a brief pause between the wake
  phrase and the command doesn't cut the recording off early.
- Restarted the app (`pkill -x nyarchassistant` — exact match, not `-f`, per
  the standing gotcha about killing your own shell) so the new settings
  actually loaded; gsettings changes don't reach an already-running detector
  thread. Confirmed via unbuffered log output
  (`PYTHONUNBUFFERED=1`) that the detector restarted with the new phrase list
  and threshold — first launch's log had been silently buffered and showed
  nothing despite the app clearly running, which is worth remembering.

**Told the user:** say the wake word and the question together, no pause —
"hey nyarch, what's on my screen?" in one breath — and report back.

### "Navigate files and browser, scroll, open stuff"

Checked what the app already exposes as LLM tools before adding anything.
Found, already enabled (`extensions-settings` already listed them from
2026-09-10, `default_on=True` in their `Tool()` definitions):
- **Files:** `read_file`, `write_file`, `edit`, `glob`, `list_directory`,
  `grep_search` — the `file_editing` extension. `file-permissions` already
  allows read/write everywhere.
- **Terminal:** `execute_command` (one-shot or persistent PTY session) — the
  `default_tools` extension.
- **Web:** `website` (read a page's text/links), `websearch` (search) — no
  dedicated click-through browser-automation tool exists in this app; "open a
  page" has to go through `execute_command` opening a real browser.
- **Screen:** `see_screen` / `scroll_screen` — our own `screenview` extension
  from 2026-09-10.

**The actual gap:** `execute_command` checks a `virtualization` gsetting
(`integrations/default_tools.py`, `_host_prefix()`). When `virtualization` is
**true** (it was), commands run *inside the Flatpak's own sandbox* — no
`xdg-open`, no `firefox`, no real desktop, so "open the browser" / "launch X"
could never have worked, even though the tool itself was enabled. Only
`false` routes commands through `flatpak-spawn --host`, the same mechanism
`screenview.py`/`forge_tts.py` already use.

This is a real increase in blast radius — a voice-triggered command runs
directly on the host with the user's own permissions, and `default-risk-level`
is already `allow` (only a short blocklist like `rm -rf`, `mkfs`, `dd` forces
a confirmation). Asked the user explicitly before changing it; they chose to
turn it on. **Set `virtualization = false`**, restarted the app, confirmed a
single clean instance is running afterward (`pgrep`; a second PID appeared and
died within seconds on its own — looked like normal GApplication D-Bus
activation, not a real duplicate instance, but worth knowing that happens).

**Not yet verified:** that the LLM actually calls `execute_command` to open
something real end-to-end. Only the sandbox setting and process health were
confirmed; the tool call itself needs a real conversation with the user
present.

### Jan

User asked, separately, to make Jan autostart and to start it right now.
Jan (`ai.jan.Jan`, Flathub Flatpak) was **not running** at the time — this
was a cold start, not a restart of something in use, so the standing "Jan is
shared, don't interfere" rule from `MANIFEST.md` didn't block it.

- Added `~/.config/autostart/ai.jan.Jan.desktop`, same pattern as the
  assistant's own autostart entry, validated with `desktop-file-validate`.
- Launched it now: it came up and auto-loaded `Qwen3_5-4B-IQ4_XS` on the
  Vulkan backend (`--n-gpu-layers 40`, matching the known-good split from
  2026-09-10 — not something set this session). Confirmed serving at
  `http://localhost:1337/v1/models`, listing both the fast 0.8b model and the
  4B vision model Nyarch depends on.

## Still needs the user

1. Say "hey nyarch, <a real question>" in one breath, report what happens.
2. Confirm autostart fires after an actual login (both Nyarch and Jan).
3. Try something that needs `execute_command` to touch the real host — e.g.
   "open a terminal" or "open firefox" — to confirm host command execution
   actually works end to end, now that the sandbox is off.
