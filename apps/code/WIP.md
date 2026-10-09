# Code: WIP

## U1 sweep (2026-10-08, Relay task 74)
Worker Itsuki (relay-80-work), Relay task 80. `static/index.html` reaches
Forge on the next page reload; the `web_app.py` change only on the next
Forge restart. Nothing removed.

- **Backend down is not the editor failing.** The start screen used to show
  "The editor didn't start: Failed to fetch" with a Try again button when
  the wrapper itself was restarting. It now says "Waiting for Code's
  backend…", keeps its spinner, and asks again with a growing wait (1 s to
  30 s) until the backend is back, then opens the editor by itself.
- The start wait rests while Code is hidden (hub or browser), and the
  spinner pauses with it (`shared/forge_idle.js` now loaded).
- Try again is locked while its restart runs (a double click restarted the
  editor twice); one start at a time.
- A remembered folder that has been deleted opens the home folder instead
  of leaving the start screen up with an error toast.
- `/api/url` answers 400 for a path the OS cannot look up (a NUL byte in
  `path` or `root`); it was a 500 with a stack trace. New test.
- Short fade on the start card; reduced motion slows the spinner.

Verified: pytest 14 passed (1 new); black and pyright 0 errors on
`web_app.py` and `tests/test_code.py`. Headless Chrome against a scratch
wrapper on 8951 with a temp `CODE_DATA_DIR` (`/tmp/u1/G5/g5check.py`): 0
callbacks in 10 s visible, hub-hidden and document-hidden once the editor is
up; backend stopped during the start wait: 3 then 1 `/api/session` asks
(0-10 s, 10-30 s), 0 while hidden; the editor opened by itself 29.5 s after
the restart; Try again triple click sent one restart; a gone remembered
folder opened `/home/ejb`. Not verified inside the real Forge window.

Critic follow-up (same day): a gone remembered folder now opens home with a
calm note instead of a red "doesn't exist" toast; if the editor's address
cannot be had even then, the start screen says so with Try again instead of
spinning for good. Verified with the critic's repro (`/tmp/u1/G5/critfix.out`)
and the g5check re-run; pytest 14 passed.

## State (2026-09-27, Kiln / S11 ejb-54)
Emerson: "the vs code thing is broke and has issues, try and fix it", and on
Restricted Mode: "if you cant find a fix in 3 tries just build a thing that
will work". Fixed in web_app.py:
- **"Broke": the editor refused the page over and over** (data/server.log was
  full of "Unauthorized client refused: auth mismatch"). The wrapper made a
  new connection token and a new random port on every start, while the page
  keeps the token in a cookie, so a page open or reloaded across an editor
  restart held a stale token. Now `keep_token` and `keep_port` keep both in
  `data/` (token file 0600; the port changes only if something else took it).
  A kept port also keeps the editor's own settings and layout, which live in
  the browser per address and were being forgotten every start.
- **Restricted Mode: gone on the first try.** The server's
  `--disable-workspace-trust` flag (`server_command`); the setting could never
  do it in the web build, which reads it from the browser's settings first.
- **Missing-file errors**: git-base, github-authentication, emmet and
  merge-conflict name an in-browser half that OpenVSCode doesn't ship.
  `hide_missing_browser_entries` drops that entry on start so they run in the
  server's extension host, as in desktop VS Code (idempotent; re-applies after
  a server upgrade).

Verified: 12 pytest pass (4 new); `tests/check_ui.py` ALL PASS in headless
Chrome, including "no Restricted Mode prompt" and a new restart check (restart
the editor behind an open page, load it again with only the cookie: it reaches
the files and the log has no "auth mismatch"). Before the fix that check
failed ("a restart keeps the editor's address"). Not yet seen inside the Forge
window (needs the Code app, or Forge, restarted).

## Open
1. First run offers Microsoft's Python extension; Open VSX has `ms-python.python`
   (Pylance is not on Open VSX; basedpyright is the usual swap).
2. DONE (S17, 2026-09-27): the chat panel starts closed (`workbench.secondarySideBar.defaultVisibility: hidden`, checked against this build's own setting list; unit test). Not seen live: it applies when the editor next starts.

## Earlier state (2026-09-26, Tools / S9 ejb-ea)
Verified: 8 pytest pass (real editor started); `tests/check_ui.py` passes everything except
"no Restricted Mode prompt": the workbench, open-by-link, explorer, typing + Ctrl+S to disk,
syntax colouring and the dark Forge theme all PASS. Not yet seen inside the Forge window (needs a Forge
restart, Emerson's call).

