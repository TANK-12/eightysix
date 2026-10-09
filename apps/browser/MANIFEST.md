# Browser: manifest

The long form of the `manifest` block in `forge_app.json`.

## Summary

A tabbed web browser inside the Forge window. Pages are real WebKit views laid over the app by forge.py (forge_views.py), so any site works, unlike an iframe. Imports bookmarks, history and cookies from the user's Firefox profile, opens pages in real Firefox, and takes commands from other apps (the Claude panel) through a small queue.

## Features

| feature | detail |
|---|---|
| Tabs and navigation | Tabs restored next time, back/forward/reload, address bar that tells addresses from searches, zoom, new-window links open as tabs, downloads saved to ~/Downloads. |
| Bookmarks and history | Star, bookmarks bar, side panels with search, start page with most visited and bookmarks. Stored in ~/.local/share/forge/browser/browser.db. |
| Import from Firefox | Bookmarks, history and cookies from the profile Firefox opens by default, read from temporary copies; Firefox is never written. Cache and saved passwords cannot come across. |
| Open in Firefox | The fox button opens the current page in real Firefox; the menu opens Firefox itself. |
| Commands for other apps | POST /api/agent/do with {op: open | search | read | tabs | back | forward | reload | switch | close}; the page carries it out and answers. Needs X-Forge: 1. |

## Data

~/.local/share/forge/browser (records); ~/.local/share/forge/browser-profile (cookies, site storage, owned by forge.py); ~/.cache/forge/browser (page cache)

## Dependencies

- Required: fastapi, uvicorn, WebKit2GTK 4.1 and libsoup 3 (for forge.py)
- Optional: firefox

## Standalone

```sh
cd ~/Forge/apps/browser && FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8444
```

## Known gaps

- Pages only render inside the Forge window; standalone the page manages records only.
- Keyboard shortcuts on the Browser page do not fire while a web page has the keyboard focus.
- No per-site permission prompts, extensions or password manager.
- Container and partitioned Firefox cookies are not imported.

See README.md for how pages reach the screen and the command API, and WIP.md for what is verified.
