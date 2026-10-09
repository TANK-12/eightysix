# Study Companion: work in progress

## U1 sweep (2026-10-08, Relay task 74)

Done in Relay task 91 (group G17). Static changes reach Emerson's Forge on the
next page reload; the `web_app.py` changes only after his next Forge restart.

What changed:
- Backend (`web_app.py`): a malformed or wrongly typed body is a calm 422 with
  one readable line (RequestValidationError handler), not a 500. Course and
  source names are fenced to real folders and `.txt` stems under `data/`
  (`..` or a typed path is a 404 / skipped). Chat and quiz bodies are checked
  before Jan is called (messages must be role/content pairs, quiz count a whole
  number 1-10). Bank paging clamps limit 1-200 and offset >= 0; damaged bank
  lines (a list, a string, a row without a topic) are skipped instead of
  breaking the whole bank. `/api/status` now asks Jan's `/models` so a model
  chosen in settings no longer reads as "connected" while Jan is down.
- Page (`static/index.html`): the question bank no longer shows duplicated
  cards ("40 of 108" on first open: boot and course load both reset it at
  once); loads that a newer one replaced are dropped and Load more ignores
  clicks while one is in flight. Switching course resets the topic list.
  Course, source, topic and skill names are HTML-escaped (quotes too) and
  URL-encoded. If the server is not up yet the page says so calmly and retries
  by itself (2 s doubling to 30 s, only while on screen, via ForgeIdle.poll).
  One chat request at a time (Send disabled meanwhile); a failed question is
  taken back out of the history and put back in the box. Jan's status is
  re-checked before chat or quiz when it was offline, after a failure, and
  when the page comes back into view (at most every 10 s); the raw reason sits
  in the tooltip. Quiz count is clamped to 1-10 in the page too. The plot
  parser only accepts the names it documents (x, e, pi, sqrt, ln, log, exp,
  abs, sin, cos, tan), so `alert(1)` or `x.constructor` is refused instead of
  run; an empty domain is a calm "could not plot" note. Toasts use the shared
  ok/err kinds (good/bad/warn had no style). Thin scrollbars, a 180 ms fade-in
  for chat messages, plots shrink to fit at 760 px, Ctrl+Enter sends.

Verified:
- `tests/test_api.py`: 19 pass (`.venv/bin/python -m pytest -q tests`; pytest
  was installed into this venv). 14 of them failed on the old code.
- Headless Chrome on a scratch copy (port 9072, Jan pointed at a dead port):
  first open shows 20 cards "20 of 108"; two fast Load more clicks give 40;
  three fast topic switches and a course reload with a bank reset give 20;
  `alert(1)`, `constructor`, `x.constructor`, `this`, `sinx` refused,
  `sin(x)+x^2` and `ln(e)` evaluate; a double submit with Jan gone sends one
  question, shows one error, history back to 0, text back in the box; quiz
  count 99 becomes 10. Hidden 10 s: 0 fetches, 0 timers, 0 frames. Server
  stopped for 30 s: no requests (nothing polls); boot with the API failing
  6 s shows "Could not reach the Study Companion server: trying again by
  itself" and loads by itself 8 s later. Screenshots at 760/1100/1500/1920,
  no sideways scroll. No page errors.

Not verified:
- A real chat or quiz against Jan (tests stub Jan; the sweep never calls it).

**Critic follow-up** (same day): a bank row whose topic is a number gave a
filter that matched nothing; topics now compare as text. A topic with no
questions says "No questions for this topic." Tests: 20 pass; page checks
re-run on port 9072 (20 / 40 / 20 cards, plot names refused, no page errors).
