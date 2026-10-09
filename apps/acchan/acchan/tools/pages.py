"""Web pages in the real, visible Firefox: read, click, fill, run scripts, and
open the logins in shared/accounts.json (claude.ai x2, Gemini, Gmail x2).

Uses Firefox's built-in remote protocol (WebDriver BiDi) through
shared/forge_bidi.py, which only exists in a Firefox started with
--remote-debugging-port: an account opened with open_account(control=true),
or your main Firefox if you start it that way yourself. Never sign in to
Google in such a window: it is flagged as automated and refused.
With no account named, the tools use Acchan's own headless Firefox
(acchan/headless_browser.py) unless the browser_view setting is "visible";
account "main" is always your main Firefox.
The `browser` toolset (session-file tabs, typing into the address bar) still
works when remote control is off.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Annotated

from .. import conversation, headless_browser, settings
from ..registry import ToolError, tool
from ..sysutil import clip

sys.path.insert(
    0, os.environ.get("FORGE_SHARED_DIR", str(Path.home() / "Forge" / "shared"))
)
import forge_accounts  # noqa: E402
import forge_bidi  # noqa: E402

TOOLSET = "pages"
TOOLSET_SUMMARY = (
    "read, screenshot, click and fill in web pages in Acchan's own headless"
    " browser (or your Firefox), and open the saved logins: claude.ai 1/2,"
    " Gemini, Gmail 1/2 (each its own window)"
)
TOOLSET_KEYWORDS = (
    "click",
    "fill",
    "form",
    "button",
    "page",
    "gmail",
    "email",
    "inbox",
    "gemini",
    "claude.ai",
    "account",
    "login",
    "javascript",
    "website",
    "webpage",
    "web page",
    "headless",
    "screenshot",
)
TOOLSET_EXAMPLES = [
    ("open my second gmail", "open_account", {"account": "gmail-2"}),
    ("what does this page say", "page_read", {}),
    ("click the sign in button", "page_click", {"target": "Sign in"}),
]

ACCOUNT_HELP = "Empty = Acchan's own headless browser; 'main' = your main Firefox; or an account id from list_accounts (claude-a, gmail-1...)"
HEADLESS_NAMES = ("headless", "acchan")


def _headless(account: str) -> bool:
    name = account.strip().lower()
    return name in HEADLESS_NAMES or (
        not name and settings.load()["browser_view"] != "visible"
    )


def _port(account: str) -> int:
    if _headless(account):
        try:
            return headless_browser.port()
        except RuntimeError as exc:
            raise ToolError(str(exc)) from exc
    name = account.strip()
    try:
        return forge_accounts.port_for("" if name.lower() == "main" else name)
    except forge_accounts.AccountError as exc:
        raise ToolError(str(exc)) from exc


def _session(account: str) -> forge_bidi.Session:
    port = _port(account)
    if not forge_bidi.port_open(port):
        if account.strip() and account.strip().lower() != "main":
            raise ToolError(
                f"{account} is not open with remote control. Use"
                " open_account with control=true (after the user has signed in)."
            )
        raise ToolError(
            "Your main Firefox has no remote control on. Use an account window"
            " (open_account with control=true), or start Firefox with"
            f" --remote-debugging-port {port}."
        )
    return forge_bidi.Session(port)


def _pick(session: forge_bidi.Session, tab: str) -> dict:
    """The tab to act on: a number from page_tabs, words from its title or
    address, or (empty) the one on screen."""
    tabs = session.tabs()
    if not tabs:
        raise ToolError("Firefox has no tabs open.")
    wanted = tab.strip()
    if not wanted:
        for key in ("focused", "visible"):
            for row in tabs:
                if row[key]:
                    return row
        return tabs[-1]
    if wanted.isdigit() and 1 <= int(wanted) <= len(tabs):
        return tabs[int(wanted) - 1]
    lower = wanted.lower()
    for row in tabs:
        if lower in row["title"].lower() or lower in row["url"].lower():
            return row
    raise ToolError(f"No tab matches '{tab}'. Use page_tabs to see them.")


def _run(account: str, tab: str, expression: str):
    try:
        with _session(account) as session:
            row = _pick(session, tab)
            return row, session.evaluate(row["context"], expression)
    except forge_bidi.BidiError as exc:
        raise ToolError(str(exc)) from exc


@tool(TOOLSET, show=True, voice="ok")
def list_accounts() -> str:
    """List the saved web logins (claude.ai, Gemini, Gmail...) and which are open."""
    try:
        rows = forge_accounts.describe()
    except (OSError, ValueError, forge_accounts.AccountError) as exc:
        raise ToolError(f"accounts.json: {exc}") from exc
    return "\n".join(
        f"{r['id']}: {r['label']} ({'open' if r['open'] else 'closed'})" for r in rows
    )


@tool(TOOLSET, example={"account": "gmail-1"}, voice="ok")
def open_account(
    account: Annotated[str, "Account id from list_accounts, like claude-b or gmail-2"],
    control: Annotated[
        bool,
        "true only when you need to read or click in it yourself; false when the user wants to sign in or use it (Google refuses sign-in under remote control)",
    ] = False,
) -> str:
    """Open a saved login (claude.ai, Gemini, Gmail) in its own Firefox window."""
    try:
        return forge_accounts.open_account(account.strip(), control=bool(control))
    except (forge_accounts.AccountError, forge_bidi.BidiError) as exc:
        raise ToolError(str(exc)) from exc


@tool(TOOLSET, show=True, voice="ok")
def page_tabs(account: Annotated[str, ACCOUNT_HELP] = "") -> str:
    """List the tabs in Firefox with number, title and address; * marks the one on screen."""
    try:
        with _session(account) as session:
            tabs = session.tabs()
    except forge_bidi.BidiError as exc:
        raise ToolError(str(exc)) from exc
    return "\n".join(
        f"{i}. {'*' if t['focused'] or t['visible'] else ' '} {t['title'] or '(no title)'} - {t['url']}"
        for i, t in enumerate(tabs, 1)
    )


@tool(TOOLSET, example={"url": "https://example.com"}, voice="ok")
def page_open(
    url: Annotated[str, "Web address to open in a new tab"],
    account: Annotated[str, ACCOUNT_HELP] = "",
) -> str:
    """Open a web address in a new tab (Acchan's headless browser unless an account or 'main' is named)."""
    address = url.strip()
    if "://" not in address:
        address = "https://" + address
    try:
        with _session(account) as session:
            session.open_tab(address)
    except forge_bidi.BidiError as exc:
        raise ToolError(str(exc)) from exc
    return f"Opened {address}."


@tool(TOOLSET, show=True, voice="ok")
def page_read(
    tab: Annotated[
        str, "Tab number or words from its title; empty = the one on screen"
    ] = "",
    account: Annotated[str, ACCOUNT_HELP] = "",
) -> str:
    """Read the text of a page open in Firefox, including logged-in pages like Gmail."""
    row, text = _run(account, tab, "document.body ? document.body.innerText : ''")
    return f"{row['title']} - {row['url']}\n\n" + clip(str(text or ""), 12000)


FIND_JS = """
(() => {
  const want = %s;
  let el = null;
  try { el = document.querySelector(want); } catch (e) {}
  if (!el) {
    const lower = want.toLowerCase();
    const pool = document.querySelectorAll('a,button,input,textarea,select,summary,label,[role],[onclick],[contenteditable="true"],[tabindex]');
    for (const c of pool) {
      const t = (c.innerText || c.value || c.getAttribute('aria-label') || c.getAttribute('placeholder') || c.title || '').trim().toLowerCase();
      if (t && t === lower) { el = c; break; }
      if (!el && t.includes(lower)) el = c;
    }
  }
  return el;
})()
"""


@tool(TOOLSET, example={"target": "Sign in"})
def page_click(
    target: Annotated[
        str, "Visible text or label of the thing to click, or a CSS selector"
    ],
    tab: Annotated[
        str, "Tab number or words from its title; empty = the one on screen"
    ] = "",
    account: Annotated[str, ACCOUNT_HELP] = "",
) -> str:
    """Click a button, link or field on a web page in Firefox by its text or a CSS selector."""
    expression = (
        "(() => { const el = " + FIND_JS % json.dumps(target) + ";"
        " if (!el) return null; el.scrollIntoView({block: 'center'});"
        " el.focus && el.focus(); el.click();"
        " return (el.innerText || el.value || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 80); })()"
    )
    _row, clicked = _run(account, tab, expression)
    if clicked is None:
        raise ToolError(f"Nothing on the page matches '{target}'. Read the page first.")
    return f"Clicked '{clicked}'."


@tool(TOOLSET, example={"target": "Search", "text": "mech kits"})
def page_fill(
    target: Annotated[str, "Label, placeholder or CSS selector of the field"],
    text: Annotated[str, "What to type into it (replaces what is there)"],
    tab: Annotated[
        str, "Tab number or words from its title; empty = the one on screen"
    ] = "",
    account: Annotated[str, ACCOUNT_HELP] = "",
) -> str:
    """Type text into a field or message box on a web page in Firefox (search boxes, forms, chat inputs)."""
    expression = (
        "(() => { const el = " + FIND_JS % json.dumps(target) + ";"
        " if (!el) return null; el.scrollIntoView({block: 'center'}); el.focus();"
        f" const text = {json.dumps(text)};"
        " if (el.isContentEditable) {"
        "   document.execCommand('selectAll'); document.execCommand('insertText', false, text);"
        " } else {"
        "   const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;"
        "   Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, text);"
        "   el.dispatchEvent(new Event('input', {bubbles: true}));"
        "   el.dispatchEvent(new Event('change', {bubbles: true}));"
        " }"
        " return el.getAttribute('aria-label') || el.placeholder || el.name || el.tagName; })()"
    )
    _row, filled = _run(account, tab, expression)
    if filled is None:
        raise ToolError(f"No field on the page matches '{target}'.")
    return f"Typed into '{filled}'."


@tool(TOOLSET, risky=True, example={"code": "document.title"})
def page_run_js(
    code: Annotated[str, "A JavaScript expression; its value is returned"],
    tab: Annotated[
        str, "Tab number or words from its title; empty = the one on screen"
    ] = "",
    account: Annotated[str, ACCOUNT_HELP] = "",
) -> str:
    """Run JavaScript in a page open in Firefox and return the result."""
    _row, value = _run(account, tab, code)
    return clip(json.dumps(value, ensure_ascii=False, indent=1), 8000)


@tool(TOOLSET, example={"tab": ""}, voice="ok")
def page_screenshot(
    tab: Annotated[str, "Tab number or words from its title; empty = current"] = "",
    account: Annotated[str, ACCOUNT_HELP] = "",
) -> str:
    """Save a picture of a web page (also in the headless browser) and say where it is."""
    try:
        with _session(account) as session:
            row = _pick(session, tab)
            shot = session.call(
                "browsingContext.captureScreenshot", {"context": row["context"]}
            )
    except forge_bidi.BidiError as exc:
        raise ToolError(str(exc)) from exc
    folder = conversation.DATA / "shots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"page-{time.strftime('%Y%m%d-%H%M%S')}.png"
    path.write_bytes(base64.b64decode(shot["data"]))
    return f"Saved a picture of '{row['title'] or row['url']}' to {path}"


@tool(TOOLSET)
def close_headless_browser() -> str:
    """Close Acchan's headless browser (it starts again on the next page tool)."""
    if headless_browser.close():
        return "Closed the headless browser."
    return "The headless browser was not running."
