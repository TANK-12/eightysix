# Browser

A tabbed web browser inside the Forge window (port 8444, role `browser`).
Pages are **real WebKit views** that `forge.py` lays over this app's page area,
so every site works; an iframe cannot do that because most sites refuse to be
framed. This app draws the tabs, address bar, bookmarks and history and drives
the views by message.

## Layout

| file | what it is |
|---|---|
| `web_app.py` | FastAPI: records, Firefox import, open-in-Firefox, the command queue. |
| `store.py` | SQLite records in `~/.local/share/forge/browser/browser.db`; the address-bar resolver and the `ENGINES` table. |
| `firefox.py` | Finds the Firefox profile and reads bookmarks, history and cookies from temporary copies. |
| `agent.py` | The command queue other apps use to drive the browser. |
| `static/` | The page. `app.js` owns tabs and talks to the views. |
| `../../forge_views.py` | The native views (owned by `forge.py`, not this app). |

## How a page gets on screen

```
static/app.js --postMessage {forge:"view", op:"create", id, url, rect}--> hub
hub           adds owner "browser", moves rect into window pixels   --> forge.py
forge.py      ViewHost.handle(...) lays a WebKit view over that rect
forge.py      --forgeViewEvent({event:"state", title, url, ...})    --> hub --> static/app.js
```

The hub shows only the open app's views, shrinks them out of the way of the
revealed top bar and the peeking dock, and never lets an app set those itself.
The WebKit profile (`~/.local/share/forge/browser-profile`) is only created the
first time a view is asked for.

What the address bar takes: a web address, a host (`example.com`), a path on
this computer (`/x`, `~/x`, `~`) or a `file:///` address, which open the file,
else a search. Only the app's own requests may open a file; a page's own
new-window links stay web only. A file tab is kept with the saved tabs but
never in history or bookmarks.

Shortcuts (`SHORTCUTS` in `static/app.js`, one row each) also work while a
page has the keyboard: each view is made with that list (`keys_first` rows
before the page sees them, `keys` only when the page leaves them alone);
forge.py gives the keyboard to the hub and sends a `key` event; the app runs
the row and hands the keyboard back to the page (`focus`). A page whose
process dies has its address loaded again once (never a form sent again), with
a note; a second death within a minute is left for Reload. A local file
WebKit cannot show gets a note instead of a copy in Downloads.

Every response carries `Cache-Control: no-cache`: without it the hub's WebKit
kept an old `app.js` for hours after an update.

## Firefox

- **Import from Firefox** (menu): bookmarks, history and cookies from the
  profile Firefox opens by default (`~/.config/mozilla/firefox/...`). Firefox is
  never written. Its page cache and saved passwords cannot come across.
- **🦊** opens the current page in real Firefox; the menu opens Firefox itself.

## Commands from other apps

`POST /api/agent/do` with header `X-Forge: 1`:

```json
{"op": "open", "url": "https://example.com", "new_tab": false}
{"op": "search", "query": "tide tables"}
{"op": "read", "tab": 0, "max_chars": 40000}
{"op": "tabs"}   {"op": "back"}   {"op": "forward"}   {"op": "reload"}
{"op": "switch", "tab": 1}   {"op": "close", "tab": 1}
```

The Browser page long-polls `/api/agent/next`, carries the command out and
posts the answer, so commands only work while the Browser is open in Forge.

## Run and test

```sh
cd ~/Forge/apps/browser
FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8444
.venv/bin/python -m pytest tests -q                         # 49
/usr/bin/python3 ../../tests/test_views.py                  # native views, off screen
/usr/bin/python3 ../../tests/smoke_browser_window.py out.png  # whole path, off screen, needs 8444 up
# real sites in a shown window, the way forge.py builds it (private headless GNOME):
cd ~/Forge && GNOME_RIG=/tmp/rig tests/browser/headless_gnome.sh start
GNOME_RIG=/tmp/rig tests/browser/headless_gnome.sh run /usr/bin/python3 \
    apps/browser/tests/check_real_sites.py --port 8923 --out /tmp/rig-out   # --sites none: offline only
GNOME_RIG=/tmp/rig tests/browser/headless_gnome.sh stop
```
