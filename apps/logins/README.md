# Logins

Every web login in `shared/accounts.json` as a tab inside Forge (port 8454,
role `logins`). Each tab is a real WebKit view (`forge_views.py`) created with
`session=<account id>`, so each account has its own cookie store and all of
them stay signed in together.

Signing in happens in the account's own **plain** Firefox window: Google
refuses a Firefox under remote control. After signing in there, **Bring login
in** reads that profile's cookies (a temporary copy) and hands them to
forge.py for that session only.

| file | what it is |
|---|---|
| `web_app.py` | `/api/accounts`, `/api/accounts/{id}/signin`, `/api/accounts/{id}/cookies` (X-Forge: 1) |
| `static/` | Tabs, toolbar, the view messages |
| `tests/test_logins.py` | Backend tests |
| `../../shared/forge_accounts.py` | Registry, Firefox profiles, cookie reading |

Run standalone: `cd ~/Forge/apps/logins && FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8454`
Test: `.venv/bin/python -m pytest -q tests`

Background and what is verified: `../../docs/DESKTOP-REACH.md`.
