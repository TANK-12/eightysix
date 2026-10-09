"""The Relay mailbox: a spare Gmail account, read over IMAP, sent from over SMTP.

Stdlib only (imaplib, smtplib, email). Emerson writes to it from his own
addresses (his Outlook one on his phone); Relay answers him there.

The lock on the door: a mail is only acted on when

1. its From address is one of `allowed_senders`, and
2. the receiving server's own Authentication-Results header (the top one,
   whose server id is `trusted_authserv`, "mx.google.com" for Gmail) shows
   `dmarc=pass` for the From domain, or `dkim=pass` signed by that domain.

Everything else is ignored and never answered. A forged From: line fails
step 2 because the forger cannot sign as outlook.com. The app password lives
in the Relay data folder's secrets/ (mode 600) and is never logged.
"""

from __future__ import annotations

import email
import email.policy
import email.utils
import imaplib
import re
import smtplib
import ssl
from email.message import EmailMessage

import store
from channels import Incoming
from commands import html_to_text

NAME = "gmail"
SECRET = "mail_password"
TIMEOUT = 30


def configured(settings: dict) -> bool:
    return bool(
        settings.get("mail_enabled")
        and settings.get("mail_address")
        and settings.get("allowed_senders")
        and store.secret(SECRET)
    )


def report_address(settings: dict) -> str:
    return settings.get("report_to") or (settings.get("allowed_senders") or [""])[0]


# ---- trust ---------------------------------------------------------------


def _domain(address: str) -> str:
    return address.rpartition("@")[2].lower().strip()


def _aligned(signer: str, domain: str) -> bool:
    signer = signer.lower().lstrip("@").rpartition("@")[2]
    return (
        signer == domain
        or signer.endswith("." + domain)
        or domain.endswith("." + signer)
    )


def trust(msg, settings: dict) -> tuple[bool, str]:
    """(trusted, reason) for a parsed message."""
    _, sender = email.utils.parseaddr(str(msg.get("From", "")))
    sender = sender.lower()
    allowed = [a.lower() for a in settings.get("allowed_senders") or []]
    if not sender or sender not in allowed:
        return False, f"sender {sender or '(none)'} is not allowed"
    headers = msg.get_all("Authentication-Results") or []
    if not headers:
        return False, "no Authentication-Results header"
    top = " ".join(str(headers[0]).split())
    server = top.split(";", 1)[0].strip().lower()
    if server != settings.get("trusted_authserv", "mx.google.com").lower():
        return False, f"top Authentication-Results is from {server}, not the mailbox"
    domain = _domain(sender)
    for part in top.split(";")[1:]:
        part = part.strip()
        dmarc = re.match(r"dmarc=(\w+).*?header\.from=([\w.-]+)", part, re.I)
        if dmarc and dmarc.group(1).lower() == "pass":
            if dmarc.group(2).lower() == domain:
                return True, "dmarc=pass"
        dkim = re.match(r"dkim=(\w+).*?header\.(?:i|d)=@?([\w.@-]+)", part, re.I)
        if dkim and dkim.group(1).lower() == "pass" and _aligned(dkim.group(2), domain):
            return True, "dkim=pass"
    return False, "no dmarc=pass or aligned dkim=pass for the sender's domain"


# ---- reading ---------------------------------------------------------------


def body_text(msg) -> str:
    plain = msg.get_body(preferencelist=("plain",))
    if plain is not None:
        return plain.get_content()
    html = msg.get_body(preferencelist=("html",))
    if html is not None:
        return html_to_text(html.get_content())
    return ""


def to_incoming(raw: bytes, settings: dict) -> Incoming:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    trusted, reason = trust(msg, settings)
    _, sender = email.utils.parseaddr(str(msg.get("From", "")))
    try:
        text = body_text(msg) if trusted else ""
    except (KeyError, LookupError, ValueError):
        text = ""
    return Incoming(
        channel=NAME,
        sender=sender.lower(),
        subject=str(msg.get("Subject", "")),
        text=text,
        message_id=str(msg.get("Message-ID", "")).strip(),
        in_reply_to=str(msg.get("In-Reply-To", "")).strip(),
        references=str(msg.get("References", "")).split(),
        trusted=trusted,
        reason=reason,
    )


def _imap(settings: dict) -> imaplib.IMAP4_SSL:
    box = imaplib.IMAP4_SSL(
        settings["imap_host"],
        int(settings["imap_port"]),
        ssl_context=ssl.create_default_context(),
        timeout=TIMEOUT,
    )
    box.login(settings["mail_address"], store.secret(SECRET))
    return box


def poll(settings: dict, state: dict) -> list[Incoming]:
    """New mail since the last poll. The first poll only sets the cursor, so
    old mail in the box is never replayed as commands."""
    box = _imap(settings)
    try:
        box.select("INBOX")
        validity = (box.response("UIDVALIDITY")[1] or [b""])[0]
        validity = (validity or b"").decode() if isinstance(validity, bytes) else ""
        _, data = box.uid("search", "ALL")
        uids = [int(u) for u in (data[0] or b"").split()]
        last = int(state.get("mail_last_uid") or 0)
        if state.get("mail_uidvalidity") != validity or not last:
            state.update(mail_uidvalidity=validity, mail_last_uid=max(uids, default=0))
            return []
        found = []
        for uid in [u for u in uids if u > last]:
            _, parts = box.uid("fetch", str(uid), "(BODY.PEEK[])")
            raw = next(
                (p[1] for p in parts or [] if isinstance(p, tuple) and len(p) > 1),
                None,
            )
            state["mail_last_uid"] = uid
            if isinstance(raw, bytes):
                found.append(to_incoming(raw, settings))
        return found
    finally:
        try:
            box.logout()
        except (OSError, imaplib.IMAP4.error):
            pass


# ---- sending ---------------------------------------------------------------


def build(
    settings: dict,
    subject: str,
    body: str,
    in_reply_to: str = "",
    references: str = "",
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = email.utils.formataddr(("Relay", settings["mail_address"]))
    msg["To"] = report_address(settings)
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(
        domain=_domain(settings["mail_address"]) or "relay.local"
    )
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = " ".join(p for p in (references, in_reply_to) if p)
    msg.set_content(body)
    return msg


def send(
    settings: dict,
    subject: str,
    body: str,
    in_reply_to: str = "",
    references: str = "",
) -> str:
    msg = build(settings, subject, body, in_reply_to, references)
    port = int(settings["smtp_port"])
    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(
            settings["smtp_host"], port, context=context, timeout=TIMEOUT
        )
    else:
        server = smtplib.SMTP(settings["smtp_host"], port, timeout=TIMEOUT)
        server.starttls(context=context)
    with server:
        server.login(settings["mail_address"], store.secret(SECRET))
        server.send_message(msg)
    return str(msg["Message-ID"])


def test(settings: dict) -> str:
    """Log in to both servers and send one test mail."""
    box = _imap(settings)
    box.logout()
    send(
        settings,
        "Relay test mail",
        "Relay can send from this mailbox. Reply with the word status to see what "
        "it is doing, or write any request and a session will work on it.",
    )
    return f"Logged in and sent a test mail to {report_address(settings)}"
