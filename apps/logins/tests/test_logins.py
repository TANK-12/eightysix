"""Logins backend: account list, the X-Forge guard, sign-in and cookies.
forge_accounts itself is tested in Forge/tests/test_forge_accounts.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import web_app  # noqa: E402

client = TestClient(web_app.app)
FORGE = {"X-Forge": "1"}


def test_lists_the_shipped_accounts_without_secrets(monkeypatch):
    r = client.get("/api/accounts")
    assert r.status_code == 200
    rows = r.json()["accounts"]
    assert {a["id"] for a in rows} >= {
        "claude-a",
        "claude-b",
        "gemini-a",
        "gmail-1",
        "gmail-2",
    }
    assert set(rows[0]) == {"id", "label", "kind", "url", "open"}


@pytest.mark.parametrize(
    "method, path",
    [
        ("post", "/api/accounts/claude-a/signin"),
        ("get", "/api/accounts/claude-a/cookies"),
    ],
)
def test_signin_and_cookies_need_the_forge_header(method, path):
    assert getattr(client, method)(path).status_code == 403


def test_cookies_come_from_forge_accounts(monkeypatch):
    rows = [
        {"name": "sid", "value": "v", "host": ".claude.ai", "path": "/", "expiry": 0}
    ]
    monkeypatch.setattr(
        web_app.forge_accounts,
        "read_cookies",
        lambda aid: rows if aid == "claude-a" else [],
    )
    assert client.get("/api/accounts/claude-a/cookies", headers=FORGE).json() == {
        "cookies": rows
    }


def test_unknown_account_is_a_plain_400():
    r = client.post("/api/accounts/nobody/signin", headers=FORGE)
    assert r.status_code == 400 and "No account called 'nobody'" in r.json()["detail"]


def test_signin_opens_the_account(monkeypatch):
    seen = []
    monkeypatch.setattr(
        web_app.forge_accounts,
        "open_account",
        lambda aid: seen.append(aid) or "Opened.",
    )
    assert client.post("/api/accounts/gemini-a/signin", headers=FORGE).json() == {
        "message": "Opened."
    }
    assert seen == ["gemini-a"]


def test_page_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "Bring login in" in r.text
