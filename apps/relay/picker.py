"""Which account and effort a launch gets. Pure functions, no files, no clock.

Emerson's rules (memories usage-pacing-rule, stop-at-95-percent-of-usage-limit,
switch-to-second-subscription-when-out):

- never on an account at or over 95 percent of its 5-hour window or 99 of
  its weekly one; from 92 percent no new launches on it;
- from 70 percent at most one launch per account every 15 minutes, and
  always at least launch_gap_minutes between two launches on one account;
- an account can have its own lines (setting account_limits, Emerson
  2026-10-07: hey has no 15-minute spacing, new launches up to 95 percent,
  hand over at 98);
- past an account's move_at (account_limits; hey 80, Emerson 2026-10-08:
  hey is the Pro plan, default the 20x one) it steps aside while another
  account has room: no new launches there, even for a task pinned to it, and
  its running work hands over (move_to); with no other room it carries on;
- an account that runs out (5-hour or weekly line, or a usage-limit hit) hands
  its work to its fallback (setting account_fallback, Emerson 2026-10-09:
  hey -> default): a task pinned to it launches there instead of waiting,
  and moves and hand-overs prefer the fallback over the most headroom;
- a resumed task prefers the account it last ran on while that account is
  still allowed and the task ended under an hour ago (warm prompt cache);
- otherwise the account with the most headroom;
- one full account is normal (two subscriptions): has_room() says which can
  take work, and "no account has room" is said only when none can;
- important work runs at max effort, the rest at high (Emerson, 2026-10-07:
  "make all tasks high effort"; the WhatsApp chat keeps its own setting);
- a task is never parked for its number of sessions: after
  review_after_rounds sessions without finishing, then every
  review_every_rounds, a short review session decides (review_due; Emerson
  2026-10-08: 25, 35, 45..., no hard cap). Only failures park by themselves.

A meter reading is {"five": percent or None, "week": percent or None}. An
account with no reading is skipped: launching blind could run it dry.
"""

from __future__ import annotations

import math

import store

EFFORTS = ("low", "medium", "high", "xhigh", "max")


def effort_for(priority: str, kind: str = "work", override: str = "") -> str:
    if override in EFFORTS:
        return override
    if kind == "handoff":
        return "low"
    if kind in ("plan", "review"):
        return "medium"
    return "max" if priority == "important" else "high"


def limits(settings: dict, account: str) -> dict:
    """The settings with this account's own lines (account_limits) on top."""
    own = (settings.get("account_limits") or {}).get(account) or {}
    return {**settings, **own}


def usage_reason(reading: dict | None, settings: dict) -> str:
    """Why this account's meters allow no new launch; "" when it has room.
    Launch spacing aside: an account that only waits for its gap has room."""
    if not reading or reading.get("five") is None:
        return "no usage reading"
    five = float(reading["five"])
    week = float(reading.get("week") or 0)
    if week >= settings["weekly_stop_at"]:
        return f"weekly meter at {week:.0f}%"
    if five >= min(settings["no_new_at"], settings["hand_over_at"]):
        return f"5-hour meter at {five:.0f}%"
    return ""


def blocked_reason(
    reading: dict | None, last_launch: float, now: float, settings: dict
) -> str:
    """Why this account may not take a launch now; "" when it may."""
    why = usage_reason(reading, settings)
    if why or not reading:
        return why
    five = float(reading["five"])
    if five >= settings["slow_at"]:
        gap = settings["slow_gap_minutes"] * 60
        if now - last_launch < gap:
            wait = int((gap - (now - last_launch)) // 60) + 1
            return f"5-hour meter at {five:.0f}%, next launch in {wait} min"
    gap = settings["launch_gap_minutes"] * 60
    if now - last_launch < gap:
        wait = int((gap - (now - last_launch)) // 60) + 1
        return f"launched here just now, next launch in {wait} min"
    return ""


def has_room(meters: dict, settings: dict) -> list[str]:
    """The accounts whose meters allow a launch (spacing aside). Emerson has
    two subscriptions (2026-10-07): one full account is normal, and only an
    empty list is worth a warning."""
    return sorted(
        name
        for name, reading in meters.items()
        if not usage_reason(reading, limits(settings, name))
    )


def headroom(reading: dict) -> float:
    five = 100 - float(reading.get("five") or 0)
    week = 100 - float(reading.get("week") or 0)
    return min(five, week * 2)


def moving(reading: dict | None, settings: dict, account: str) -> bool:
    """Past this account's move_at line (account_limits; off when unset)."""
    if not reading or reading.get("five") is None:
        return False
    line = float(limits(settings, account).get("move_at") or 101)
    return float(reading["five"]) >= line


def fallbacks(settings: dict, account: str) -> list[str]:
    """The accounts this one's work falls back to, nearest first (setting
    account_fallback: a name or a list per account, chains followed, so
    hey -> default -> second). Loops, itself and junk are skipped: the file
    can be hand-edited."""
    table = settings.get("account_fallback")
    if not isinstance(table, dict):
        return []
    chain: list[str] = []
    seen, todo = {account}, [account]
    while todo:
        got = table.get(todo.pop(0))
        for name in (
            [got] if isinstance(got, str) else got if isinstance(got, list) else []
        ):
            name = name.strip() if isinstance(name, str) else ""
            if name and name not in seen:
                seen.add(name)
                chain.append(name)
                todo.append(name)
    return chain


def out_of_usage(reading: dict | None, settings: dict, account: str) -> bool:
    """This account can take no work for its meters: past its no-new or
    weekly line, a usage-limit hit (reads as 100), or no reading at all.
    Launch spacing is not out: that clears in minutes."""
    return bool(usage_reason(reading, limits(settings, account)))


def fallback_in(settings: dict, account: str, pool) -> str:
    """The nearest fallback of `account` that is in `pool`, "" for none."""
    return next((n for n in fallbacks(settings, account) if n in pool), "")


def move_to(
    meters: dict,
    settings: dict,
    account: str,
    last_launch: dict,
    now: float,
) -> str:
    """The account work on `account` should move to now, "" to stay: only
    past its move_at, and only to an account that may take a launch right
    now (blocked_reason: room and spacing) and is not past its own. The
    relaunch goes through pick_account with the same checks, so it lands
    there and not back here (a loop the task-105 critic found)."""
    if not moving(meters.get(account), settings, account):
        return ""
    others = [
        n
        for n, reading in meters.items()
        if n != account
        and not moving(reading, settings, n)
        and not blocked_reason(reading, last_launch.get(n, 0), now, limits(settings, n))
    ]
    if not others:
        return ""
    return fallback_in(settings, account, others) or max(
        others, key=lambda n: headroom(meters[n])
    )


def pick_account(
    meters: dict,
    last_launch: dict,
    now: float,
    settings: dict,
    prefer: str = "",
    prefer_ended: float = 0,
    forced: str = "",
) -> tuple[str | None, str]:
    """(account, why). account is None when nothing may launch."""
    allowed = {
        name: reading
        for name, reading in meters.items()
        if not blocked_reason(
            reading, last_launch.get(name, 0), now, limits(settings, name)
        )
    }
    every = allowed
    staying = {n: r for n, r in allowed.items() if not moving(r, settings, n)}
    if forced and forced in allowed and forced not in staying and staying:
        best = fallback_in(settings, forced, staying) or max(
            staying, key=lambda n: headroom(staying[n])
        )
        return best, f"{forced} is past its move line, so {best}"
    if staying:
        allowed = staying
    if forced:
        if forced in allowed:
            return forced, "asked for by name"
        why = blocked_reason(
            meters.get(forced),
            last_launch.get(forced, 0),
            now,
            limits(settings, forced),
        )
        if out_of_usage(meters.get(forced), settings, forced):
            # the nearest fallback whose meters have room, one not past its
            # own move line first; one that only waits for spacing is waited
            # for, not skipped (critic, task 128)
            roomy = [
                n
                for n in fallbacks(settings, forced)
                if n in meters and not out_of_usage(meters[n], settings, n)
            ]
            if roomy:
                alt = next(
                    (n for n in roomy if not moving(meters[n], settings, n)), roomy[0]
                )
                if alt in every:
                    return alt, f"{forced} is out ({why}), so its fallback {alt}"
                spaced = blocked_reason(
                    meters[alt], last_launch.get(alt, 0), now, limits(settings, alt)
                )
                return None, f"{forced}: {why}; its fallback {alt}: {spaced}"
        return None, f"{forced}: {why or 'unknown account'}"
    if not allowed:
        roomy = has_room(meters, settings)
        names = roomy or list(meters)
        reasons = "; ".join(
            f"{n}: {blocked_reason(meters[n], last_launch.get(n, 0), now, limits(settings, n))}"
            for n in names
        )
        if roomy:  # only spacing holds it: a full other account is not news
            return None, f"spacing launches ({reasons})"
        return None, (
            f"no account has room ({reasons})" if reasons else "no accounts found"
        )
    if prefer and out_of_usage(meters.get(prefer), settings, prefer):
        alt = fallback_in(settings, prefer, allowed)
        if alt:
            return alt, f"{prefer} is out, so its fallback {alt}"
    warm = settings["warm_minutes"] * 60
    if prefer in allowed and prefer_ended and now - prefer_ended < warm:
        return prefer, "same account, prompt cache still warm"
    best = max(allowed, key=lambda n: (headroom(allowed[n]), n == prefer))
    return best, "most headroom"


def over_hand_over(reading: dict | None, settings: dict, account: str = "") -> bool:
    """A running session on this account should stop and hand over."""
    if not reading or reading.get("five") is None:
        return False
    settings = limits(settings, account)
    return (
        float(reading["five"]) >= settings["hand_over_at"]
        or float(reading.get("week") or 0) >= settings["weekly_stop_at"]
    )


def over_context(context_tokens: int, settings: dict) -> bool:
    """A running session has grown so big each turn costs too much: hand over."""
    return context_tokens >= settings["hand_over_context_k"] * 1000


def resume_cheap(context_tokens: int, settings: dict) -> bool:
    """Resuming a session reloads its whole context; only worth it while small."""
    return context_tokens < settings["resume_max_context_k"] * 1000


def should_park(task: dict, settings: dict) -> str:
    """Why a task should stop being retried; "" to keep going. Only failures
    park by themselves; a long task gets a review instead (review_due)."""
    fails = _whole(task.get("fails"), 0)
    if fails >= settings["max_fails"]:
        return f"failed or stalled {fails} times"
    return ""


def review_due(task: dict, settings: dict) -> bool:
    """The task has run enough sessions without finishing that a review
    must decide whether it carries on: first after review_after_rounds
    sessions, then every review_every_rounds (25, 35, 45...). No hard cap."""
    first = _setting(settings, "review_after_rounds")
    if first <= 0:
        return False
    rounds = _whole(task.get("attempts"), 0)
    seen = _whole(task.get("reviewed_at"), 0)
    if seen > rounds:  # from before a retry started the count again
        seen = 0
    if not seen:
        return rounds >= first
    every = review_every(settings)
    return every > 0 and rounds >= seen + every


def review_every(settings: dict) -> int:
    """Sessions between one review and the next; 0: only the first."""
    return _setting(settings, "review_every_rounds")


def finishing_minutes(settings: dict) -> float:
    return _number(
        settings.get("finishing_minutes"), store.DEFAULTS["finishing_minutes"]
    )


def finishing(run: dict, settings: dict, now: float) -> bool:
    """The session said it is close to finishing (`relay finishing`): no
    hand-over for its context size, nor for its account's move line, until
    finishing_minutes have passed. The usage hand-over still applies."""
    since = _number(run.get("finishing"), 0)
    return bool(since) and now - since < finishing_minutes(settings) * 60


def _number(value, fallback: float) -> float:
    """A number from a task field or setting, `fallback` when it is none: a
    hand-edited file must not stop every launch (critic, task 112)."""
    try:
        got = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return got if math.isfinite(got) else float(fallback)


def _whole(value, fallback: int) -> int:
    return int(_number(value, fallback))


def _setting(settings: dict, key: str) -> int:
    return _whole(settings.get(key), store.DEFAULTS[key])
