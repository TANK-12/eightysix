# helper-8: Claude panel, two-account login switching

Task 8 of crew panelforge. App: ~/Forge/apps/claude. Log kept resumable.

## Verified facts about the CLI (2.1.274, 2026-09-17)

- `claude auth status --json` prints loggedIn, authMethod, email, orgName,
  subscriptionType, configDirectory.
- `CLAUDE_CONFIG_DIR=<dir>` selects the config dir; an empty dir reports
  loggedIn false and gets only `.claude.json` + `backups/` created by status.
- `claude auth login` with stdin/stdout pipes (no tty): prints "Opening browser
  to sign in", the URL line "If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?...",
  then "Paste code here if prompted > " and waits for a line on stdin.
  `BROWSER=<script>` is honoured (script got the URL with a localhost
  callback). A bogus code: stderr "Login failed: Request failed with status
  code 400", exit 1, still not logged in.
- No `claude usage` command; help lists none.

## Plan

1. Before-state e2e on scratch port (real CLI, default profile).
2. runner.py: Profiles registry (profiles.json + profiles/<name>/), env per
   profile, login process relay, conversation meta["profile"], session
   transcript copy on profile change.
3. web_app.py: /api/profiles routes; settings accept profile.
4. static/: account picker in the sidebar, login box, header badge.
5. tests, black, pyright, screenshot, docs, crew done.

- Stream carries `rate_limit_event.rate_limit_info.unifiedWindows.{five_hour,seven_day}.{utilization,resetsAt}`: the usage display.
- Transcripts live at `<config>/projects/<cwd with non-word chars as ->/<session>.jsonl`; copying one to another config dir makes `--resume` find it (verified: without copy "No conversation found", with copy the session resumes and fails only on auth).
- A not-signed-in profile answers `-p` with a result `is_error` "Not logged in".

## Done

- joined board, took task 8, read app, CLI probes above.
- Before-state e2e on a scratch port with the real CLI: the first conversation
  took over 2 minutes before its init event (CLI-side, one-off; api time was
  3 s), the second 6 s to a streamed answer. Two turns spent.
- runner.py: Profiles (profiles.json + profiles/<name>), Login relay over pipes,
  Conversation.profile/move_to (transcript copy), usage capture, Registry wiring.
- web_app.py: /api/profiles routes, activate with conversation, settings.profile.
- tests/fake_claude.py: auth status/login faked; rate_limit_event per turn.
- tests: 5 new (incl. 2000-name sweep). `pytest -q tests`: 20 passed.
- black + pyright clean on runner.py, web_app.py.

- static/: account list under the conversations (dot = signed in, email,
  5-hour usage bar, sign in / remove), sign-in box (address, open in Browser,
  copy, code input, cancel; a running sign-in comes back after a reload),
  "on <account>" badge in the header, forge_account event drawn in the log,
  "still starting" status after 20 s without an event. node --check ok.
- After-state e2e, real CLI, scratch port 58045, data in scratch: turn 1
  "panel works" 4.3 s; usage recorded (five_hour used 0.85); add "work";
  activate work with the conversation -> moved "copied", transcript file
  present in the work profile; send on work -> 500 "The account 'work' is not
  signed in; sign in from the account picker or pick another"; activate
  default -> "copied"; turn 2 resumed the same session id and answered
  "panel works" in 4.1 s. Real `claude auth login` for "work" reached
  "waiting" with the real address (BROWSER=/bin/true). Cancelled with the
  server (lifespan stop_all); nothing left running.
- pytest 20 passed; black; pyright 0 errors (runner, web_app, tests); docs
  (WIP.md, README.md, MANIFEST.md, forge_app.json) updated.
- Scratch server stopped by PID; no claude children left.

## Stopped here (session ended by Emerson)

- **Not done: the screenshot.** Headless Chrome hung on the page three times
  (also with --user-data-dir private profile and --timeout). The UI is
  unverified visually. Next session: start on a scratch port
  (`FORGE_CLAUDE_DATA=<scratch> BROWSER=/bin/true ... uvicorn web_app:app
  --port <free>`), POST /api/profiles {"name":"work"} and
  POST /api/profiles/work/login so the box shows, screenshot at 1400x900,
  check contrast of .account rows, .meter and .signin, fix, re-shoot.
  Try `--dump-dom` first to see whether the long poll (wait=25) is what
  stalls Chrome; if so, take the shot before opening a conversation.
- Task 8 left **taken**, not done, because of that.
- Emerson: the real second sign-in (README "Accounts").
- Lesson: a kill loop over `pgrep -f "<pattern>"` in the same Bash call that
  also contains the real command line matched its own shell (exit 144);
  the bracket form does not help when the script itself spells the command.
