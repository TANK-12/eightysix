"""The Relay boss: a plain Python loop that keeps Claude working unattended.

It spends no tokens while it waits. Each tick (every 60 s, or at once when the
page pokes it) it:

1. reads everything from files (goals, tasks, runs, settings, state);
2. reads the usage meters (3-minute cache, through ~/.claude/tools/usage.py);
3. watches running sessions: a finished one is handed on, a silent one is
   stopped as stuck, one whose account passed 95 percent is asked to write
   its State and stop, then carried on under another account;
4. reads new mail and carries out what Emerson sent;
5. launches queued tasks, and a short planning session for any goal with
   nothing queued, while an account and the machine have room;
6. mails the daily digest, keeps the laptop awake while work is queued.

Run: `.venv/bin/python boss.py` (the relay-boss user service does this),
`boss.py --once` for a single tick. Sessions run in their own process groups
and survive a boss restart; the boss finds them again from runs/.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHARED = Path(os.environ.get("FORGE_SHARED_DIR") or ROOT.parent.parent / "shared")
for extra in (str(ROOT), str(SHARED)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

import actions  # noqa: E402
import bossline  # noqa: E402
import channels  # noqa: E402
import chat  # noqa: E402
import chatlog  # noqa: E402
import commands  # noqa: E402
import frontdesk  # noqa: E402
import localchat  # noqa: E402
import items  # noqa: E402
import machine  # noqa: E402
import meters  # noqa: E402
import picker  # noqa: E402
import prompts  # noqa: E402
import review  # noqa: E402
import runs  # noqa: E402
import store  # noqa: E402

TICK = 60
CREW = store.CREW
BOARD_NAME = "relay"
CHAT_STUCK = 60  # seconds a chat message may wait with no session starting
CHAT_RETRY = 30  # after a failed chat launch, the next try waits this long
CHAT_REST = 300  # after a chat session failed twice in a row, this long


class Boss:
    def __init__(self) -> None:
        store.ensure()
        self.settings = store.settings()
        self.state = store.state()
        self.desk = frontdesk.Desk()
        self.tidy = chatlog.Tidy()
        self.line = bossline.Line()

    # ---- helpers -----------------------------------------------------------

    def log(self, kind: str, text: str, **extra) -> None:
        store.event(kind, text, **extra)

    def board(self, text: str) -> None:
        """Tell the interactive sessions on the crew board."""
        if not CREW.is_file():
            return
        board = self.settings["board"]
        if not board:
            return
        try:
            if not self.state.get("board_joined"):
                subprocess.run(
                    [sys.executable, str(CREW), "join", board, BOARD_NAME]
                    + ["--role", "solo"],
                    capture_output=True,
                    timeout=20,
                )
                self.state["board_joined"] = True
            subprocess.run(
                [sys.executable, str(CREW), "post", board, BOARD_NAME, text],
                capture_output=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def mail(self, subject: str, body: str, item: dict | None = None) -> None:
        """Mail Emerson, in the item's thread when it has one."""
        ready = channels.ready(self.settings)
        if not ready:
            return
        thread = (item or {}).get("thread") or ""
        plain = subject
        if item is not None and thread:
            subject = "Re: " + (item.get("subject") or subject)
        for name, channel in ready.items():
            wants = getattr(channel, "wants", None)
            if wants and not wants(self.settings, plain, item):
                continue
            chat = getattr(channel, "TAGGED", False)  # no threads: keep "Done: ..."
            try:
                sent = channel.send(
                    self.settings,
                    plain if chat else subject,
                    body,
                    in_reply_to=thread,
                    **tag(channel, item),
                )
            except Exception as e:  # a mail failure must never stop the boss
                self.log("mail-error", f"{name}: {e}")
                continue
            if sent and item is not None:
                key = str(item.get("id") or item.get("slug"))
                self.state.setdefault("threads", {})[sent] = key
                if not thread:
                    item["thread"], item["subject"] = sent, subject
                    items.save(item)

    def folder_for(self, task: dict) -> str:
        goal = items.find_goal(task.get("goal") or "") or {}
        named = [v for v in (task.get("folder"), goal.get("folder")) if v]
        for value in named:
            if os.path.isdir(os.path.expanduser(value)):
                return os.path.expanduser(value)
        home = self.home_folder()
        if named:
            self.log(
                "error",
                f"task {task.get('id')}: folder {named[0]} is missing, "
                f"launching in {home}",
            )
        return home

    def home_folder(self) -> str:
        """default_folder, or the home folder when it is gone (logged once per
        missing path): a deleted default folder once kept the WhatsApp chat
        from launching for 20 minutes (Relay task 105)."""
        folder = os.path.expanduser(str(self.settings["default_folder"] or "~"))
        if os.path.isdir(folder):
            self.state.pop("missing_folder", None)
            return folder
        home = str(Path.home())
        if self.state.get("missing_folder") != folder:
            self.state["missing_folder"] = folder
            self.log("error", f"default folder {folder} is missing: using {home}")
        return home

    def meters(self) -> dict:
        data = meters.read()
        self.state["meters"] = data
        return data

    # ---- watching running sessions -------------------------------------------

    def watch(self, now: float) -> None:
        # with limit hits: one session hitting the limit moves the others
        # still running on that account too (critic, task 128)
        readings = self.readings(now)
        for run in runs.active():
            if runs.alive(run):
                info = runs.summary(run)
                silent = now - max(info["last_at"], run["started"])
                if silent > self.settings["stall_minutes"] * 60:
                    self.log(
                        "stall", f"run {run['id'][:8]} silent {silent // 60:.0f} min"
                    )
                    runs.stop(run)
                    self.finish(run, now, stalled=True)
                elif run["kind"] == "chat" and picker.over_context(
                    info["context_tokens"],
                    {
                        "hand_over_context_k": 2
                        * self.settings["whatsapp_chat_context_k"]
                    },
                ):
                    self.log("handover", f"chat run {run['id'][:8]} too big, ended")
                    runs.stop(run)
                    self.finish(run, now)
                elif run["kind"] == "review" and picker.over_context(
                    info["context_tokens"], self.settings
                ):
                    # a review is meant to be short: one this big is cut off
                    # and counts as a try that gave no verdict
                    self.log("review", f"review run {run['id'][:8]} too big, ended")
                    runs.stop(run)
                    self.finish(run, now)
                elif run["kind"] == "work" and picker.over_hand_over(
                    readings.get(run["account"]), self.settings, run["account"]
                ):
                    self.hand_over(run, now, f"{run['account']} is nearly out")
                elif (
                    run["kind"] == "work"
                    and not self.settings["paused"]  # it could not relaunch
                    and not picker.finishing(run, self.settings, now)
                    and (
                        to := picker.move_to(
                            self.readings(now),
                            self.settings,
                            run["account"],
                            self.state.get("last_launch") or {},
                            now,
                        )
                    )
                ):
                    self.hand_over(
                        run, now, f"{run['account']} is past its move line, on to {to}"
                    )
                elif run["kind"] == "work" and picker.over_context(
                    info["context_tokens"], self.settings
                ):
                    k = info["context_tokens"] // 1000
                    if picker.finishing(run, self.settings, now):
                        self.let_finish(run, k)
                    else:
                        late = (
                            ", finishing time ran out" if run.get("finishing") else ""
                        )
                        self.hand_over(
                            run, now, f"context at {k}k{late}, fresh session next"
                        )
                continue
            self.finish(run, now)
        self.heal_reviews()

    def heal_reviews(self) -> None:
        """A task left as reviewing with no review running (a stale save of
        its file won a race with the verdict) goes back to the queue rather
        than waiting for ever (critic, task 112)."""
        live = {r["id"] for r in runs.active()}
        for task in items.all_tasks():
            if task.get("status") == "reviewing" and task.get("review_run") not in live:
                task["status"] = "queued"
                items.save(task)
                self.log(
                    "review",
                    f"task {task['id']} was left reviewing with no review "
                    "running: queued again",
                )

    def hand_over(self, run: dict, now: float, why: str) -> None:
        """The account passed 95 percent, or the session's context grew past
        the cap: stop, have the same session write its State in one short turn
        (its cache is warm), then requeue for a fresh session."""
        runs.stop(run)
        task = items.find_task(run["task"])
        run.update(ended=now, outcome="handed over")
        runs.save(run)
        if not task:
            return
        self.log("handover", f"task {task['id']}: {why}")
        if self.limited(run["account"], now):
            # the account has hit its limit: a hand-over turn there would only
            # fail, so a fresh session carries on from the task file
            self.requeue(task, run, now, handed=True)
            return
        try:
            handoff = runs.start(
                task,
                "handoff",
                run["account"],
                picker.effort_for("", "handoff"),
                prompts.handoff(task, why),
                run["folder"],
                resume=run["session"],
            )
        except (OSError, RuntimeError) as e:
            self.log("error", f"hand-over session for task {task['id']}: {e}")
            self.requeue(task, run, now)
            return
        handoff["state_mark"] = items.state_mark(task.get("body", ""))
        runs.save(handoff)
        task.update(status="handing_over", last_run=handoff["id"])
        items.save(task)

    def finish(self, run: dict, now: float, stalled: bool = False) -> None:
        info = runs.summary(run)
        result = info["result"]
        run.update(ended=now, outcome="stalled" if stalled else "exited")
        if result:
            run["result"] = {k: result[k] for k in ("is_error", "subtype", "cost_usd")}
        runs.save(run)
        if run["kind"] == "plan":
            self.finish_plan(run, result)
            return
        task = items.find_task(run["task"])
        if not task or task.get("status") == "stopped":
            return
        if run["kind"] == "review":
            self.finish_review(task, run, result, now, stalled)
            return
        if chat.is_chat(task):
            self.finish_chat(task, run, info, result, now, stalled)
            return
        if run["kind"] == "handoff":
            # The hand-over turn may find the task finished: honour a done or
            # blocked it wrote then, not a stale one from before a retry
            # (task 105 ran a fourth session for nothing).
            task = items.find_task(run["task"]) or task
            body = task.get("body", "")
            wrote = items.state_mark(body) != run.get("state_mark")
            ok = result is not None and not result["is_error"] and not stalled
            if not (
                ok and wrote and items.state_status(body)[0] in ("done", "blocked")
            ):
                if ok and wrote:
                    task["fails"] = 0  # the session got somewhere
                self.requeue(task, run, now, handed=True)
                return
        text = (result or {}).get("text") or ""
        if stalled:
            self.failed(task, run, now, "it went silent and was stopped")
            return
        if result is None or result["is_error"]:
            err = text or runs.stderr_tail(run)
            if runs.hit_limit(err):
                self.state.setdefault("limited", {})[run["account"]] = now
                self.log("limit", f"{run['account']} hit its usage limit")
                self.requeue(task, run, now, handed=True)
            else:
                self.failed(task, run, now, err[-400:] or "it exited without a result")
            return
        # Re-read: the session edited the body while it ran.
        task = items.find_task(run["task"]) or task
        word, note = items.state_status(task.get("body", ""))
        task.update(last_account=run["account"], last_ended=round(now))
        if word == "blocked":
            task.update(status="blocked", note=note[:200])
            items.save(task)
            self.log("blocked", f"task {task['id']} needs Emerson: {note}")
            self.board(f"Relay task {task['id']} blocked: {task.get('title')}")
            self.mail(
                f"Task {task['id']} needs you: {task.get('title')}",
                f"Blocked: {note}\n\n{text}\n\nReply 'retry' in this thread once it "
                "is sorted, or write what to do instead.",
                task,
            )
            return
        if word == "continue":
            # a big session starts fresh from its State rather than reloading it all
            fresh = not picker.resume_cheap(info["context_tokens"], self.settings)
            # failures park only in a row: with no session cap, two stray
            # errors in a long working task must not stop it (critic, task 112)
            task["fails"] = 0
            self.requeue(task, run, now, handed=fresh)
            return
        task.update(status="done", finished=round(now), note="")
        items.save(task)
        self.log("done", f"task {task['id']} done: {task.get('title')}")
        self.board(f"Relay task {task['id']} done: {task.get('title')}")
        cost = (result or {}).get("cost_usd")
        tail = f"\n\n(Relay task {task['id']}, account {run['account']}, effort {run['effort']}"
        tail += f", about ${cost:.2f} of usage)" if cost else ")"
        self.mail(f"Done: {task.get('title')}", (text or "Finished.") + tail, task)
        if task.get("goal") and task["goal"] != "inbox":
            self.check_goal(task["goal"], now)

    def finish_chat(
        self,
        task: dict,
        run: dict,
        info: dict,
        result: dict | None,
        now: float,
        stalled: bool = False,
    ) -> None:
        """A chat session ended: idle until the next message (never done or
        parked). It is resumed next time while its context is small."""
        task = items.find_task(task["id"]) or task
        text = (result or {}).get("text") or ""
        error = stalled or result is None or bool(result.get("is_error"))
        small = info["context_tokens"] < self.settings["whatsapp_chat_context_k"] * 1000
        task.update(
            last_account=run["account"],
            last_ended=round(now),
            resume_ok="yes" if run["kind"] == "chat" and small and not error else "",
        )
        if error:
            why = "it went silent" if stalled else (text or runs.stderr_tail(run))
            if runs.hit_limit(why):
                self.state.setdefault("limited", {})[run["account"]] = now
            chat.mark_unread(task, run.get("messages") or [])
            task = items.find_task(task["id"]) or task
            task["fails"] = int(items.num(task, "fails")) + 1
            self.log("failed", f"chat task {task['id']}: {why[-200:]}")
            if task["fails"] >= self.settings["max_fails"]:
                task.update(fails=0)
                items.save(task)
                # what he wrote still gets an answer: the boss line takes it,
                # and so does the next while the chat rests (no two failed
                # sessions per message, task 105)
                self.chat_failed(
                    task, "the chat session failed twice in a row", now, CHAT_REST
                )
                return
            task["status"] = "queued"
            items.save(task)
            return
        task["fails"] = 0
        self.chat_ok()
        if (
            run["kind"] == "chat"
            and text.strip()
            and chat.last_reply_at() < run["started"]
        ):
            chat.reply(text)  # it forgot relay reply: its last words go instead
        task["status"] = "queued" if chat.has_new(task) else chat.IDLE
        items.save(task)

    def requeue(self, task: dict, run: dict, now: float, handed: bool = False) -> None:
        """More to do: queued again. Never parked for its number of sessions
        (Emerson, 2026-10-08): launch() gives a long task a review instead."""
        task.update(
            status="queued",
            last_account=run["account"],
            last_ended=round(now),
            resume_ok="yes" if not handed else "",
        )
        items.save(task)
        self.log(
            "requeue",
            f"task {task['id']} queued again ({'hand-over' if handed else 'more to do'})",
        )

    def failed(self, task: dict, run: dict, now: float, why: str) -> None:
        task["fails"] = int(items.num(task, "fails")) + 1
        task.update(
            status="queued",
            last_account=run["account"],
            last_ended=round(now),
            resume_ok="",
        )
        self.log("failed", f"task {task['id']}: {why[:200]}")
        park = picker.should_park(task, self.settings)
        if park:
            self.park(task, park, why)
        else:
            items.save(task)

    def park(self, task: dict, why: str, detail: str = "", body: str = "") -> None:
        task.update(status="parked", note=why[:200])
        items.save(task)
        self.log("parked", f"task {task['id']} parked: {why}")
        self.board(f"Relay task {task['id']} parked: {task.get('title')}")
        self.mail(
            f"Parked: {task.get('title')}",
            body
            or f"Task {task['id']} stopped being retried: {why}.\n\n{detail[-1500:]}"
            f"\n\nIts file: {task['path']}\nReply 'retry' in this thread to run it again.",
            task,
        )

    # ---- the review of a long task (Emerson, 2026-10-08) --------------------------

    def start_review(self, task: dict, account: str, now: float) -> None:
        """A long task's review (picker.review_due): a short fresh session
        reads what its sessions did and says continue or park. The task waits
        as reviewing; its own session stays resumable (last_run untouched)."""
        folder = self.folder_for(task)
        rounds = int(items.num(task, "attempts"))
        try:
            notes = review.evidence(task, folder, now)
        except Exception as e:  # the reviewer still has the task file
            notes = f"(Relay could not gather its notes: {e})"
        # a Stop or a note may have come while the notes were gathered
        task = items.find_task(task["id"]) or task
        if task.get("status") not in items.WAITING:
            return
        every = picker.review_every(self.settings)
        run = runs.start(
            task,
            "review",
            account,
            picker.effort_for("", "review", self.settings["review_effort"]),
            prompts.review(task, notes, rounds, folder, rounds + every if every else 0),
            folder,
            self.settings["review_model"],
        )
        task.update(status="reviewing", review_run=run["id"])
        items.save(task)
        self.log(
            "review",
            f"task {task['id']} has run {rounds} sessions: review started on {account}",
        )

    def finish_review(
        self, task: dict, run: dict, result: dict | None, now: float, stalled: bool
    ) -> None:
        """Continue: queued again, the next review review_every_rounds
        sessions on. Park: his phone gets the one-line reason. No verdict:
        another try; after max_fails tries the task carries on to the next
        review (a wrong park costs more than a few sessions: critic, task
        112). A usage limit just waits."""
        task = items.find_task(run["task"]) or task
        rounds = int(items.num(task, "attempts"))
        text = (result or {}).get("text") or ""
        error = stalled or result is None or bool(result.get("is_error"))
        word, why = ("", "") if error else review.verdict(text)
        if not word:
            problem = (
                "it went silent"
                if stalled
                else (
                    (text or runs.stderr_tail(run))[-300:]
                    or "it exited without a result"
                    if error
                    else "it gave no verdict line"
                )
            )
            if error and runs.hit_limit(problem):
                self.state.setdefault("limited", {})[run["account"]] = now
                self.log("limit", f"{run['account']} hit its usage limit")
                task["status"] = "queued"
                items.save(task)
                return
            tries = int(items.num(task, "review_fails")) + 1
            self.log("failed", f"task {task['id']} review: {problem[-200:]}")
            if tries < self.settings["max_fails"]:
                task.update(status="queued", review_fails=tries)
                items.save(task)
                return
            short = " ".join(problem.split())[-120:]
            task.update(
                status="queued",
                reviewed_at=rounds,
                review_fails=0,
                review_note=f"no verdict in {tries} tries ({short}), carried on"[:200],
            )
            items.save(task)
            self.log("review", f"task {task['id']}: no verdict, it carries on")
            self.board(
                f"Relay task {task['id']}: its review after {rounds} sessions gave "
                f"no verdict in {tries} tries ({short}); it carries on"
            )
            return
        why = why or (
            "it is doing real work" if word == "continue" else "no real progress"
        )
        task.update(
            reviewed_at=rounds, review_fails=0, review_note=f"{word}: {why}"[:200]
        )
        if word == "park":
            self.park(
                task,
                f"review after {rounds} sessions: {why}",
                body=f"Task {task['id']} parked after {rounds} sessions: {why}\n"
                f"Say retry {task['id']} to run it again.",
            )
            return
        task["status"] = "queued"
        items.save(task)
        self.log(
            "review", f"task {task['id']} carries on after {rounds} sessions: {why}"
        )

    def let_finish(self, run: dict, k: int) -> None:
        """Past the context line, but the session said it is close to
        finishing (relay finishing): it carries on. Logged once."""
        if run.get("finishing_seen"):
            return
        run["finishing_seen"] = True
        runs.save(run)
        self.log(
            "finishing",
            f"task {run['task']}: context at {k}k but it is finishing, no hand-over yet",
        )

    # ---- goals -----------------------------------------------------------------

    def run_check(self, goal: dict) -> tuple[bool, str]:
        folder = os.path.expanduser(
            goal.get("folder") or self.settings["default_folder"]
        )
        try:
            done = subprocess.run(
                goal["check"],
                shell=True,
                cwd=folder if os.path.isdir(folder) else None,
                capture_output=True,
                text=True,
                timeout=self.settings["check_timeout"],
            )
        except subprocess.TimeoutExpired:
            return False, "the check timed out"
        except OSError as e:
            return False, str(e)
        output = (done.stdout + done.stderr)[-3000:]
        return done.returncode == 0, f"exit {done.returncode}\n{output}"

    def check_goal(self, slug: str, now: float) -> None:
        goal = items.find_goal(slug)
        if not goal or not goal.get("check") or goal.get("status") != "active":
            return
        passed, output = self.run_check(goal)
        goal["last_check"] = "pass" if passed else "fail"
        self.state.setdefault("check_output", {})[slug] = output
        items.log_goal(
            goal,
            f"check {'passed' if passed else 'failed'}: {output.splitlines()[0] if output else ''}",
        )
        if passed:
            goal.update(status="done", finished=round(now))
            items.save(goal)
            self.log("goal-done", f"goal {slug} done: its check passed")
            self.mail(
                f"Goal done: {goal.get('title')}",
                f"The check `{goal['check']}` passed.\n\n{output[-1000:]}",
                goal,
            )

    def finish_plan(self, run: dict, result: dict | None) -> None:
        goal = items.find_goal(run["goal"])
        if not goal:
            return
        adopted = items.adopt_new(goal["slug"])
        text = (result or {}).get("text") or ""
        if adopted:
            goal["empty_plans"] = 0
            items.log_goal(
                goal,
                "planned: " + "; ".join(f"{t['id']} {t['title']}" for t in adopted),
            )
            self.log("planned", f"goal {goal['slug']}: {len(adopted)} new tasks")
            return
        if text.strip().upper().startswith("GOAL DONE") and not goal.get("check"):
            goal.update(status="done", finished=round(time.time()))
            items.log_goal(goal, "the planner found the goal met")
            self.mail(f"Goal done: {goal.get('title')}", text, goal)
            return
        goal["empty_plans"] = int(items.num(goal, "empty_plans")) + 1
        if goal["empty_plans"] >= 2:
            goal["status"] = "stuck"
            items.log_goal(
                goal, "two planning sessions wrote no tasks; waiting on Emerson"
            )
            self.mail(
                f"Goal stuck: {goal.get('title')}",
                f"Planning wrote no tasks twice.\n\n{text[-1500:]}",
                goal,
            )
        else:
            items.save(goal)

    def goals_to_plan(self) -> list[dict]:
        tasks = items.all_tasks()
        planning = {r.get("goal") for r in runs.active() if r["kind"] == "plan"}
        out = []
        for goal in items.all_goals():
            slug = goal["slug"]
            if goal.get("status") != "active" or slug in planning:
                continue
            mine = [t for t in tasks if t.get("goal") == slug]
            if any(
                t.get("status") in (*items.WAITING, *items.ACTIVE, "blocked", "parked")
                for t in mine
            ):
                continue
            out.append(goal)
        return out

    # ---- mail in -----------------------------------------------------------------

    def read_mail(self, now: float, fast_only: bool = False) -> int:
        """Polls each channel that is due; how many messages it handled. Fast
        channels (WhatsApp) say their own gap in seconds, given how long ago
        Emerson last wrote there (it shrinks for a while after a message)."""
        handled = 0
        for name, channel in channels.ready(self.settings).items():
            fast = getattr(channel, "poll_seconds", None)
            if fast_only and not fast:
                continue
            key = f"last_poll_{name}" if fast else "last_poll"
            heard = self.state.get(f"last_heard_{name}")
            quiet = now - heard if heard else None
            gap = (
                fast(self.settings, quiet)
                if fast
                else self.settings["poll_minutes"] * 60
            )
            if now - self.state.get(key, 0) < gap:
                continue
            self.state[key] = now
            cursor = self.state.setdefault("cursors", {}).setdefault(name, {})
            try:
                incoming = channel.poll(self.settings, cursor)
            except Exception as e:
                # a dead page fails every look; in the fast window log it at
                # the normal pace only, not every 2 s
                last = self.state.get(f"last_error_{name}", 0)
                if not fast or now - last >= fast(self.settings, None):
                    self.state[f"last_error_{name}"] = now
                    self.log("mail-error", f"{name} poll: {e}")
                continue
            if incoming:
                self.state[f"last_heard_{name}"] = now
            for msg in incoming:
                self.handle(msg, channel)
                handled += 1
        return handled

    def flush_outbox(self, now: float = 0) -> int:
        """Send what sessions queued with relay reply / send-file / unsend."""
        if not chat.pending():
            return 0
        channel = channels.ready(self.settings).get("whatsapp")
        if channel is None or not hasattr(channel, "deliver"):
            return 0
        return chat.flush(lambda entry: channel.deliver(self.settings, entry))

    def quick(self) -> bool:
        """Between ticks: send the outbox and poll the fast channels only.
        True when a message came in, so the next tick (and any launch)
        happens straight away."""
        if not any(
            hasattr(c, "poll_seconds")
            for c in channels.ready(store.settings()).values()
        ):
            return False
        self.settings = store.settings()
        self.state = store.state()
        self.flush_outbox()
        handled = self.read_mail(time.time(), fast_only=True)
        if handled:
            self.chat_now(time.time())  # no wait for the tick (Relay task 105)
        self.front_desk()
        self.boss_line()
        self.flush_outbox()
        store.save_state(self.state)
        return handled > 0

    def front_desk(self, now: float = 0) -> None:
        """Jan answers WhatsApp first (frontdesk.py); this applies a finished
        answer and starts the next."""
        done = self.desk.step(self.settings, self.state)
        if done:
            self.log("chat", done)

    def boss_line(self, now: float = 0) -> None:
        """Answers a WhatsApp "boss ..." question (bossline.py) in a thread."""
        try:
            done = self.line.step(self.settings, lambda: self.readings(time.time()))
        except Exception:  # never let it stop the outbox and the poll after it
            done = f"boss line error: {traceback.format_exc()[-400:]}"
        if done:
            self.log("boss", done)

    def chat_log(self, now: float) -> None:
        """Every whatsapp_log_minutes: the visible chat into its running log
        (chatlog.py); then, when due or asked for, one old stretch is
        summarised in a thread and, once done, posted and deleted."""
        channel = channels.ready(self.settings).get("whatsapp")
        if channel is None or not hasattr(channel, "messages"):
            return
        done = self.tidy.step()
        if done:
            self.apply_tidy(done)
        asked = chatlog.requested()
        minutes = self.settings["whatsapp_log_minutes"]
        due = now - self.state.get("last_chatlog", 0) >= minutes * 60
        if not (due or asked) or self.tidy.busy():
            return
        self.state["last_chatlog"] = now
        name = self.settings["whatsapp_chat"]
        found = channel.messages(self.settings)
        added = chatlog.record(name, found, now)
        if added:
            self.log("chatlog", f"{added} messages added to the chat log")
        gap = self.settings["whatsapp_tidy_minutes"] * 60
        if not asked and not (
            self.settings["whatsapp_tidy"]
            and now - self.state.get("last_tidy", 0) >= gap
        ):
            return
        chatlog.clear_request()
        picked = chatlog.stretch(
            found,
            chatlog.logged(name),
            self.settings["whatsapp_tidy_keep"],
            1 if asked else self.settings["whatsapp_tidy_least"],
            chatlog.summarised(name),
        )
        if not picked:
            if asked:
                chat.reply(
                    "Nothing to tidy yet: the chat has no older messages above "
                    f"the last {self.settings['whatsapp_tidy_keep']}."
                )
            return
        self.state["last_tidy"] = now
        self.log("chatlog", f"summarising {len(picked)} older messages")
        self.tidy.start(picked, self.settings)

    def apply_tidy(self, done: dict) -> None:
        """A finished summary: post it, then delete what it summarised (only
        ids the log holds), a few at a time through the outbox."""
        if not done.get("text"):
            self.log("chatlog", f"no summary: {done.get('error')}")
            return
        chat.reply(done["text"])
        name = self.settings["whatsapp_chat"]
        ids = [i for i in done.get("ids") or [] if i in chatlog.logged(name)]
        chatlog.mark_summarised(name, done.get("ids") or [])
        if self.settings["whatsapp_tidy_delete"]:
            for at in range(0, len(ids), 8):
                chat.queue_out("delete_ids", ids=ids[at : at + 8])
        notes = f" ({'; '.join(done['notes'])})" if done.get("notes") else ""
        self.log(
            "chatlog",
            f"summary of {len(ids)} messages by {done.get('by')}{notes}"
            + ("" if self.settings["whatsapp_tidy_delete"] else ", nothing deleted"),
        )

    def handle(self, msg: channels.Incoming, channel) -> None:
        if not msg.trusted:
            self.log("ignored", f"mail from {msg.sender} ignored: {msg.reason}")
            return
        threads = self.state.setdefault("threads", {})
        thread_key = next(
            (
                threads[r]
                for r in [msg.in_reply_to, *reversed(msg.references)]
                if r in threads
            ),
            "",
        )
        thread_task = thread_key if thread_key.isdigit() else ""
        if re.fullmatch(r"#\d+", msg.in_reply_to or ""):
            thread_task = msg.in_reply_to[1:]
        slugs = tuple(g["slug"] for g in items.all_goals())
        source = msg.channel if msg.channel in commands.REMOTE else "mail"
        cmd = commands.parse(msg.subject, msg.text, slugs, source=source)
        self.log("mail", f"from {msg.sender}: {cmd.kind} {cmd.title[:80]}".strip())
        subject = commands.bare_subject(msg.subject) or cmd.title or "Relay"
        reply, made = actions.apply(
            cmd, source, thread_task=thread_task, thread=msg.message_id, subject=subject
        )
        if made is not None and msg.message_id:
            threads[msg.message_id] = str(made.get("id") or made.get("slug"))
        if not reply:
            return  # the chat session answers by itself
        try:
            sent = channel.send(
                self.settings,
                "Re: " + subject,
                reply,
                in_reply_to=msg.message_id,
                references=" ".join(msg.references),
                **tag(channel, made),
            )
            if sent and made is not None:
                threads[sent] = str(made.get("id") or made.get("slug"))
        except Exception as e:
            self.log("mail-error", f"reply: {e}")

    # ---- launching -----------------------------------------------------------------

    def limited(self, account: str, now: float) -> bool:
        """A usage-limit hit counts as full for 30 minutes whatever the meter says."""
        at = (self.state.get("limited") or {}).get(account)
        return bool(at) and now - at < 1800

    def readings(self, now: float) -> dict:
        readings = self.meters()
        for name in list(readings):
            if self.limited(name, now):
                readings = {**readings, name: {**readings[name], "five": 100}}
        return readings

    def launch_chat(self, now: float) -> None:
        """The WhatsApp chat starts as soon as a message waits: it is light,
        so it skips pause, session slots, the launch gap and the render
        check, but never an account that is out of room."""
        task = chat.chat_task(create=False)
        if not task:
            return
        if self.state.get("chat_wait") and task.get("status") != "queued":
            # the local chat stands in; say so once Claude has room again
            if self.chat_account(task, now)[0]:
                self.state["chat_wait"] = ""
                self.state["chat_wait_told"] = ""
                if localchat.fallback_on(self.settings) and (
                    localchat.mode(self.settings) == "claude"
                ):
                    chat.queue_out("text", text=localchat.BACK_TEXT)
                self.log("chat", "Claude has usage again")
            return
        if task.get("status") != "queued":
            return
        if any(str(r.get("task")) == str(task["id"]) for r in runs.active()):
            return
        account, why = self.chat_account(task, now)
        if not account:
            self.state["chat_wait"] = why
            if localchat.fallback_on(self.settings):
                # the local model answers until Claude has usage (localchat.py)
                task["status"] = chat.DESK
                items.save(task)
                if self.state.get("chat_wait_told") != "local":
                    self.state["chat_wait_told"] = "local"
                    chat.queue_out(
                        "text",
                        text=localchat.fallback_text(reset_note(self.readings(now))),
                    )
                self.log("chat", f"no usage for the Claude chat ({why}): local model")
                return
            if self.state.get("chat_wait_told") != task.get("last_run", "") + "?":
                # once per wait: say so, instead of going silent for hours
                self.state["chat_wait_told"] = task.get("last_run", "") + "?"
                chat.queue_out("text", text=waiting_text(self.readings(now)))
            return
        self.state["chat_wait"] = ""
        self.state["chat_wait_told"] = ""
        failed = self.state.get("chat_fail") or {}
        if failed and now - failed.get("at", 0) < failed.get("wait", CHAT_RETRY):
            # it failed a moment ago: the boss line answers meanwhile
            self.chat_to_boss(task, failed.get("why", ""), now)
            return
        try:
            self.start_chat(task, account, why, now)
        except Exception as e:  # any failure: he hears it and gets answered
            text = str(e) if isinstance(e, (OSError, RuntimeError)) else repr(e)
            if any(str(r.get("task")) == str(task["id"]) for r in runs.active()):
                # the session runs and has his messages: no outage to report
                self.log("error", f"chat started, but then: {text}")
                return
            self.chat_failed(task, text, now)
            return
        self.state.pop("chat_queued_at", None)

    def start_chat(self, task: dict, account: str, why: str, now: float) -> None:
        model, effort = chat.chat_model(self.settings)
        messages = chat.new_messages(task)
        resume = ""
        last = task.get("last_run")
        if (
            task.get("resume_ok") == "yes"
            and task.get("chat_model") == model
            and why.startswith("same account")
            and last
        ):
            resume = (store.read_json(runs.run_dir(last) / "run.json") or {}).get(
                "session", ""
            )
        prompt = (
            prompts.chat_resume(task, messages)
            if resume
            else prompts.chat(task, messages)
        )
        folder = self.home_folder()
        run = runs.start(task, "chat", account, effort, prompt, folder, model, resume)
        run["messages"] = messages
        runs.save(run)
        chat.take_new(task)
        task = items.find_task(task["id"]) or task
        task.update(
            status="running",
            attempts=int(items.num(task, "attempts")) + 1,
            ran_on=account,
            chat_model=model,
            last_run=run["id"],
            started=round(now),
        )
        items.save(task)
        self.log(
            "start",
            f"chat {task['id']} on {account}, {model} {effort}"
            + (" (resumed)" if resume else " (fresh)"),
        )

    def chat_failed(
        self, task: dict, why: str, now: float, wait: float = CHAT_RETRY
    ) -> None:
        """The chat could not start (or failed twice): the boss line takes
        his messages until a try after `wait` seconds works."""
        fail: dict = self.state.get("chat_fail") or {"since": now}
        fail.update(why=why[:300], at=now, wait=wait)
        self.state["chat_fail"] = fail
        self.log("error", f"chat failed: {why}")
        self.chat_to_boss(task, why, now)

    def chat_ok(self) -> None:
        """A chat session answered: the outage is over; say so once."""
        if self.state.pop("chat_fail", None):
            self.log("chat", "the chat answers again")
        if self.state.pop("chat_down_told", None):
            chat.queue_out("text", text=BACK_TEXT)

    def chat_to_boss(self, task: dict, why: str, now: float) -> None:
        """The Claude chat cannot answer: what he wrote goes to the boss line
        (one lean turn: no folder, no session) and he hears why, once per
        outage. Never a silent chat again (Relay task 105)."""
        new = chat.take_new(task)
        task = items.find_task(task["id"]) or task
        task["status"] = chat.IDLE
        items.save(task)
        self.state.pop("chat_queued_at", None)
        if not self.state.get("chat_down_told"):
            self.state["chat_down_told"] = now
            chat.queue_out("text", text=down_text(why))
        for entry in new:
            bossline.ask_later(chat.message_text(entry))
        self.log("chat", f"{len(new)} chat message(s) to the boss line: {why[:120]}")

    def chat_guard(self, now: float) -> None:
        """A chat message waiting over a minute with no session starting (and
        not knowingly waiting for usage) goes to the boss line, and he hears
        why. Catches what launch_chat cannot see itself."""
        task = chat.chat_task(create=False)
        if not task or task.get("status") != "queued" or not chat.has_new(task):
            self.state.pop("chat_queued_at", None)
            return
        if any(str(r.get("task")) == str(task["id"]) for r in runs.active()):
            return
        since = self.state.setdefault("chat_queued_at", now)
        if now - since < CHAT_STUCK or self.state.get("chat_wait"):
            return
        why = (self.state.get("chat_fail") or {}).get("why") or (
            "no chat session started within a minute"
        )
        self.state.pop("chat_queued_at", None)
        self.log("error", f"chat stuck: {why}")
        self.chat_to_boss(task, why, now)

    def chat_now(self, now: float) -> None:
        """Launch the chat (and check it is not stuck); never raises."""
        for step in (self.launch_chat, self.chat_guard):
            try:
                step(now)
            except Exception:
                self.log("error", f"chat: {traceback.format_exc()[-400:]}")

    def chat_account(self, task: dict, now: float) -> tuple[str | None, str]:
        relaxed = {**self.settings, "launch_gap_minutes": 0, "slow_gap_minutes": 0}
        return picker.pick_account(
            self.readings(now),
            {},
            now,
            relaxed,
            prefer=task.get("last_account", ""),
            prefer_ended=items.num(task, "last_ended"),
        )

    def launch(self, now: float) -> None:
        self.state["wait_reason"] = ""
        self.chat_now(now)
        if self.settings["paused"]:
            self.state["wait_reason"] = "paused"
            return
        for goal in items.all_goals():
            items.adopt_new(goal["slug"])
        queued = sorted(
            (
                t
                for t in items.all_tasks()
                if t.get("status") in items.WAITING and not chat.is_chat(t)
            ),
            key=lambda t: (t.get("priority") != "important", int(t["id"])),
        )
        plans = self.goals_to_plan()
        if not queued and not plans:
            return
        busy_runs = [r for r in runs.active() if r["kind"] != "chat"]
        slots = self.settings["max_sessions"] - len(busy_runs)
        if slots <= 0:
            self.state["wait_reason"] = (
                f"all {self.settings['max_sessions']} session slots busy"
            )
            return
        busy = machine.busy(self.settings)
        if busy:
            self.state["wait_reason"] = busy
            return
        readings = self.readings(now)
        launched = self.state.setdefault("last_launch", {})
        work = [
            ("review" if picker.review_due(t, self.settings) else "work", t)
            for t in queued
        ] + [("plan", g) for g in plans]
        started, pinned = 0, []
        for kind, item in work:
            if started >= slots:
                break
            account, why = picker.pick_account(
                readings,
                launched,
                now,
                self.settings,
                prefer=item.get("last_account", ""),
                prefer_ended=items.num(item, "last_ended"),
                forced=item.get("account", "") if kind != "plan" else "",
            )
            if not account:
                if kind != "plan" and item.get("account"):
                    # pinned to one account: it waits, the rest may still go
                    # (and for its fallback when that is out too)
                    also = picker.out_of_usage(
                        readings.get(item["account"]), self.settings, item["account"]
                    ) and picker.fallbacks(self.settings, item["account"])
                    pinned.append(
                        f"task {item['id']} waits for {item['account']}"
                        + (f" or {' / '.join(also)}" if also else "")
                    )
                    continue
                self.state["wait_reason"] = why
                return
            try:
                self.start(kind, item, account, why, now)
            except (OSError, RuntimeError) as e:
                self.log("error", f"launch failed: {e}")
                return
            launched[account] = now
            started += 1
        if pinned and not started:
            self.state["wait_reason"] = "; ".join(pinned) + " (asked for by name)"

    def start(self, kind: str, item: dict, account: str, why: str, now: float) -> None:
        if kind == "plan":
            effort = picker.effort_for(item.get("priority", ""), "plan")
            check_out = (self.state.get("check_output") or {}).get(item["slug"], "")
            folder = os.path.expanduser(item.get("folder") or "")
            if not item.get("folder") or not os.path.isdir(folder):
                folder = self.home_folder()
            runs.start(
                item,
                "plan",
                account,
                effort,
                prompts.plan(item, check_out),
                folder,
                self.settings["model"],
            )
            item["plans"] = int(items.num(item, "plans")) + 1
            items.save(item)
            self.log("plan", f"planning goal {item['slug']} on {account}")
            return
        if kind == "review":
            self.start_review(item, account, now)
            return
        effort = picker.effort_for(
            item.get("priority", ""), "work", item.get("effort", "")
        )
        folder = self.folder_for(item)
        resume = ""
        last = item.get("last_run")
        if item.get("resume_ok") == "yes" and why.startswith("same account") and last:
            resume = (store.read_json(runs.run_dir(last) / "run.json") or {}).get(
                "session", ""
            )
        prompt = (
            prompts.resume(item)
            if resume
            else prompts.work(item, item.get("source") or "the Relay page", folder)
        )
        first = not items.num(item, "attempts")
        run = runs.start(
            item,
            "work",
            account,
            effort,
            prompt,
            folder,
            item.get("model") or self.settings["model"],
            resume=resume,
        )
        # whether State moves from one session to the next, for the review
        run["state_before"] = items.state_mark(item.get("body", ""))
        runs.save(run)
        item.update(
            status="running",
            attempts=int(items.num(item, "attempts")) + 1,
            ran_on=account,
            effort_used=effort,
            last_run=run["id"],
            started=round(now),
        )
        items.save(item)
        self.log("start", f"task {item['id']} started on {account} at {effort} ({why})")
        if first:  # a hand-over or retry is not news on the board (task 105)
            self.board(
                f"Relay task {item['id']} started ({account}, {effort}) in {folder}: "
                f"{item.get('title')}"
            )
        if self.settings["mail_on_start"]:
            self.mail(
                f"Started: {item.get('title')}",
                f"Task {item['id']} started on {account} at {effort} effort.",
                item,
            )

    # ---- digest and keeping awake ------------------------------------------------------

    def digest(self, now: float) -> None:
        hh, _, mm = str(self.settings["digest_time"]).partition(":")
        try:
            due = time.localtime(now)
            target = time.mktime(
                (
                    due.tm_year,
                    due.tm_mon,
                    due.tm_mday,
                    int(hh),
                    int(mm or 0),
                    0,
                    0,
                    0,
                    -1,
                )
            )
        except (ValueError, OverflowError):
            return
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        if now < target or self.state.get("digest_day") == today:
            return
        self.state["digest_day"] = today
        since = self.state.get("digest_at") or now - 86400
        self.state["digest_at"] = now
        if channels.ready(self.settings):
            self.mail(f"Relay digest {today}", actions.digest_text(since))

    def keep_awake(self) -> None:
        needed = bool(runs.active()) or (
            not self.settings["paused"]
            and any(t.get("status") in items.WAITING for t in items.all_tasks())
        )
        held = self.state.get("inhibit") or {}
        alive = bool(held) and runs.alive(held)
        if needed and not alive:
            proc = subprocess.Popen(
                [
                    "systemd-inhibit",
                    "--what=sleep:idle",
                    "--who=Relay",
                    "--why=Relay has work queued or running",
                    "sleep",
                    "infinity",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.state["inhibit"] = {
                "pid": proc.pid,
                "proc_start": runs.proc_start(proc.pid),
            }
        elif not needed and alive:
            runs.stop(held)
            self.state["inhibit"] = {}

    # ---- the tick ----------------------------------------------------------------------

    def tick(self) -> None:
        now = time.time()
        self.settings = store.settings()
        self.state = store.state()
        self.state["heartbeat"] = now
        runs.reap()
        steps = (
            self.flush_outbox,
            self.watch,
            self.read_mail,
            self.front_desk,
            self.boss_line,
            self.chat_log,
            self.launch,
        )
        for step in (*steps, self.digest):
            try:
                step(now)
            except Exception:
                self.log("error", f"{step.__name__}: {traceback.format_exc()[-600:]}")
        try:
            self.keep_awake()
        except (OSError, subprocess.SubprocessError) as e:
            self.log("error", f"keep awake: {e}")
        store.save_state(self.state)


def reset_note(readings: dict) -> str:
    """ " (usage comes back about 14:23)", or "" with no reset time."""
    soonest = None
    for m in readings.values():
        week_full = (m.get("week") or 0) >= 95
        when = m.get("week_resets") if week_full else m.get("resets")
        try:
            at = datetime.fromisoformat(str(when)).timestamp()
        except ValueError:
            continue
        soonest = at if soonest is None else min(soonest, at)
    if not soonest:
        return ""
    fmt = "%H:%M" if soonest - time.time() < 20 * 3600 else "%a %H:%M"
    return f" (usage comes back about {time.strftime(fmt, time.localtime(soonest))})"


BACK_TEXT = "The Claude chat is back: your messages go to it again."


def down_text(why: str) -> str:
    """The one WhatsApp line for a chat outage (Relay task 105)."""
    return (
        f"The Claude chat can't answer right now ({why.strip()[:160]}). The "
        "boss line answers your messages until it is back: it can check and "
        "steer Relay but not do work itself. I'll say when the chat is back."
    )


def waiting_text(readings: dict) -> str:
    """The WhatsApp line for a Claude hand-off that has no usage to start
    (with the local stand-in off)."""
    reset = reset_note(readings)
    return (
        f"Got it. Claude is out of usage right now{reset}; your message waits "
        "and Claude picks it up as soon as it can. You can keep chatting with "
        "Jan meanwhile."
    )


def tag(channel, item: dict | None) -> dict:
    """The "#12" a chat channel puts on a message about task 12."""
    if getattr(channel, "TAGGED", False) and item and item.get("id"):
        return {"tag": f"#{item['id']}"}
    return {}


def wait(seconds: float, between=None) -> None:
    """Sleep until the next tick, waking early when the page pokes or
    `between()` (the fast channel poll) says a message came in."""
    poke = store.path("poke")
    try:
        seen = poke.stat().st_mtime
    except OSError:
        seen = 0.0
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(2)
        try:
            if between is not None and between():
                return
        except Exception:
            pass  # a fast-poll failure waits for the tick, which logs it
        try:
            if poke.stat().st_mtime != seen:
                return
        except OSError:
            continue


def main() -> int:
    boss = Boss()
    if "--once" in sys.argv:
        boss.tick()
        return 0
    boss.log("boss", f"boss started (pid {os.getpid()})")
    while True:
        boss.tick()
        wait(TICK, boss.quick)


if __name__ == "__main__":
    sys.exit(main())
