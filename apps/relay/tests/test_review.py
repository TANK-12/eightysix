"""Relay task 112: no session cap. Task 102 was parked at 13 sessions while it
made real progress every session. Now (Emerson, 2026-10-08) a short fresh
review decides after 25 sessions, then every 10 (35, 45, 55...), and a
session close to finishing may run past the context hand-over."""

import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest

import actions
import boss as boss_mod
import chat
import commands
import items
import picker
import prompts
import review
import runs
import store
from test_boss import settle, task_, world  # noqa: F401  (a fixture)

S = store.DEFAULTS


def long_task(request: str, attempts: int, **extra) -> dict:
    task = items.new_task("Long job", request, source="mail")
    task.update(attempts=attempts, **extra)
    items.save(task)
    return task


def run_file(run_id: str) -> dict:
    found = store.read_json(runs.run_dir(run_id) / "run.json")
    assert isinstance(found, dict)
    return found


def wait_runs(timeout: float = 5) -> None:
    end = time.time() + timeout
    while any(runs.alive(r) for r in runs.active()) and time.time() < end:
        runs.reap()
        time.sleep(0.05)


# ---- when a review is due (pure) ------------------------------------------------


@pytest.mark.parametrize(
    "attempts, reviewed, due",
    [
        (0, 0, False),
        (24, 0, False),
        (25, 0, True),  # the first review: after 25 sessions
        (31, 0, True),  # one that was missed is still due
        (25, 25, False),
        (34, 25, False),
        (35, 25, True),  # then every 10
        (44, 35, False),
        (45, 35, True),
        (55, 45, True),
        (505, 495, True),  # no hard cap: far past 50 it is still only a review
        (504, 495, False),
        (3, 25, False),  # reviewed before a retry started the count again
    ],
)
def test_review_points(attempts, reviewed, due):
    task = {"attempts": attempts, "reviewed_at": reviewed}
    assert picker.review_due(task, S) is due


def test_review_points_are_settings():
    assert S["review_after_rounds"] == 25 and S["review_every_rounds"] == 10
    assert "max_rounds" not in S  # the old park-at-N rule is gone
    s = {**S, "review_after_rounds": 3, "review_every_rounds": 2}
    assert picker.review_due({"attempts": 3}, s)
    assert not picker.review_due({"attempts": 4, "reviewed_at": 3}, s)
    assert picker.review_due({"attempts": 5, "reviewed_at": 3}, s)
    off = {**S, "review_after_rounds": 0}
    assert not picker.review_due({"attempts": 1000}, off)
    once = {**S, "review_every_rounds": 0}
    assert picker.review_due({"attempts": 25}, once)
    assert not picker.review_due({"attempts": 1000, "reviewed_at": 25}, once)


@pytest.mark.parametrize(
    "task, settings, due",
    [
        ({"attempts": 25, "reviewed_at": "n/a"}, {}, True),
        ({"attempts": "lots"}, {}, False),
        ({"attempts": "1e400"}, {}, False),  # not a finite number
        ({"attempts": 25}, {"review_after_rounds": None}, True),  # the default
        ({"attempts": 25}, {"review_after_rounds": ""}, True),
        ({"attempts": 35, "reviewed_at": 25}, {"review_every_rounds": "ten"}, True),
    ],
)
def test_hand_edited_values_do_not_stop_launches(task, settings, due):
    """A bad value in a task file or settings.json falls back to the
    default instead of raising in every launch (critic, task 112)."""
    assert picker.review_due(task, {**S, **settings}) is due


def test_hand_edited_values_elsewhere():
    assert picker.should_park({"fails": "n/a"}, S) == ""
    assert picker.finishing_minutes({**S, "finishing_minutes": "soon"}) == 45
    assert not picker.finishing({"finishing": "nan"}, S, 1000)


def test_only_failures_park_by_themselves():
    assert picker.should_park({"attempts": 13}, S) == ""
    assert picker.should_park({"attempts": 1000, "fails": 1}, S) == ""
    assert "2 times" in picker.should_park({"fails": 2}, S)


# ---- the reviewer's answer --------------------------------------------------------


@pytest.mark.parametrize(
    "text, want",
    [
        (
            "verdict: continue - lands commits every session",
            ("continue", "lands commits every session"),
        ),
        (
            "Looked.\n**Verdict:** park — the same step five times",
            ("park", "the same step five times"),
        ),
        ("VERDICT: Parked: waits on a password", ("park", "waits on a password")),
        ("verdict: continuing, real progress", ("continue", "real progress")),
        ("verdict: park - x\nmore\nverdict: continue - y", ("continue", "y")),
        ("verdict: continue", ("continue", "")),
        ("no verdict line, though I would continue", ("", "")),
        ("my verdict: park it", ("", "")),  # the word must end or a separator follow
        ("**Final verdict:** park — the same step", ("park", "the same step")),
        ("Verdict for task 102: continue - real work", ("continue", "real work")),
        # prose around the words is no verdict rather than the wrong one
        ("parking it would be wrong; continue", ("", "")),
        ("continued sessions add nothing - park", ("", "")),
        ("Answer with verdict: park or continue", ("", "")),
        ("verdict: continue/park", ("", "")),
        ("no verdict: continue", ("", "")),
        # the prompt's own template read back is no answer
        ("verdict: continue - <why>\nor\nverdict: park - <why>", ("", "")),
        ("verdict: continue - real\nverdict: park - <why>", ("continue", "real")),
        # the second critic's replies: no false park
        (
            "verdict: continue - real work\n\nNext verdict: park if nothing lands",
            ("continue", "real work"),
        ),
        ("(Next review's verdict: park if it is still on the parser.)", ("", "")),
        ("Verdict: park is not warranted - continue", ("", "")),
        ("**Verdict:** Park would be premature: State moved", ("", "")),
        (
            "A tempting verdict: park - 25 is a lot.\nmore\n"
            "Verdict for Relay task 102: continue - steady",
            ("continue", "steady"),
        ),
        # only the end of the reply counts: an early park does not win
        ("My verdict: park - stale\na\nb\nc\nd\ne\nVerdict -> go on", ("", "")),
        # and real verdicts in other words are read
        (
            "verdict: park - <the same test for ten sessions>",
            ("park", "<the same test for ten sessions>"),
        ),
        ("**Verdict (Relay task 102):** park", ("park", "")),
        ("My verdict is: continue", ("continue", "")),
        ("Reviewer’s verdict: continue - x", ("continue", "x")),
        (
            "3. Verdict: park (no progress in 10 sessions)",
            ("park", "(no progress in 10 sessions)"),
        ),
        ("", ("", "")),
    ],
)
def test_verdict(text, want):
    assert review.verdict(text) == want


# ---- what the reviewer reads ------------------------------------------------------


def git(repo: Path, *args: str, at: float | None = None) -> None:
    env = {**os.environ}
    if at is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"@{int(at)} +0000"
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
        env=env,
    )


def fake_run(task: dict, started: float, ended: float, words: str, **extra) -> dict:
    run = {
        "id": str(uuid.uuid4()),
        "task": task["id"],
        "kind": "work",
        "account": "a",
        "started": started,
        "ended": ended,
        "outcome": "exited",
        **extra,
    }
    run.setdefault("session", run["id"])
    home = runs.run_dir(run["id"])
    home.mkdir(parents=True)
    (home / "output.jsonl").write_text(
        f'{{"type": "result", "is_error": false, "result": "{words}"}}\n'
    )
    runs.save(run)
    return run


def test_evidence_counts_state_moves_and_tagged_commits(tmp_path):
    now = time.time()
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    task = long_task("FAKE:continue", 2, created=round(now - 1000), folder=str(repo))
    marks = items.state_mark(task["body"])
    first = fake_run(
        task,
        now - 900,
        now - 600,
        "Built the parser",
        folder=str(repo),
        state_before=marks + 1,
    )
    second = fake_run(
        task,
        now - 500,
        now - 100,
        "Fixed the tests",
        folder=str(repo),
        state_before=marks,
    )
    # a hand-over turn of the second session
    fake_run(
        task,
        now - 99,
        now - 98,
        "Stopped after the tests",
        kind="handoff",
        session=second["session"],
    )
    for name, message, at in (
        ("a", "Parser (Relay task %s)" % task["id"], now - 800),
        ("b", "Unrelated (Relay task %s0)" % task["id"], now - 700),
        ("c", "Tests (Relay task %s)" % task["id"], now - 300),
        ("d", "Someone else's work", now - 200),
    ):
        (repo / name).write_text(name)
        git(repo, "add", name)
        git(repo, "commit", "-q", "-m", message, at=at)
    text = review.evidence(task, str(repo), now)
    lines = text.splitlines()
    one = next(line for line in lines if line.startswith("1. "))
    two = next(line for line in lines if line.startswith("2. "))
    # the first session changed State (its mark differs from the second's start)
    assert "State moved: yes; commits: 1" in one
    # the second ends where State is now: nothing moved since it started
    assert "State moved: no; commits: 1" in two
    assert "last words: Built the parser" in text
    assert "hand-over note: Stopped after the tests" in text
    assert "Parser (Relay task" in text and "Tests (Relay task" in text
    assert "Unrelated" not in text  # task 10 is not task 1
    assert f"Other commits in {repo} in that time: 2" in text
    assert first["id"] not in text  # no run ids, only what a reader needs


def test_commit_tags_name_the_task_exactly(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    now = time.time()
    messages = [
        "Parser (Relay task 7)",
        "Tests (Relay task #7)",
        "relay task 7: lower case",
        "Subtask 7 done",
        "Step: task 7 of 9",
        "Other (Relay task 70)",
        "Other (Relay task 17)",
    ]
    for i, message in enumerate(messages):
        (repo / str(i)).write_text(message)
        git(repo, "add", str(i))
        git(repo, "commit", "-q", "-m", message, at=now - 100 + i)
    found = [c["subject"] for c in review.commits(str(repo), 7, now - 1000)]
    assert found == messages[:3]


def test_evidence_finds_commits_in_another_tasks_repo(tmp_path):
    """A session in a plain folder may commit in a repo other Relay tasks run
    in (one started in the home folder commits in ~/Forge)."""
    now = time.time()
    plain, repo = tmp_path / "plain", tmp_path / "forge"
    plain.mkdir()
    repo.mkdir()
    git(repo, "init", "-q")
    other = items.new_task("Elsewhere", "FAKE:done")
    other["folder"] = str(repo)
    items.save(other)
    task = long_task("FAKE:continue", 3, created=round(now - 1000), folder=str(plain))
    (repo / "x").write_text("x")
    git(repo, "add", "x")
    git(repo, "commit", "-q", "-m", f"Work (Relay task {task['id']})", at=now - 500)
    text = review.evidence(task, str(plain), now)
    assert "its folder is not in a git repo" in text
    assert f"Work (Relay task {task['id']})" in text and f"[in {repo}]" in text


def test_evidence_names_the_last_review_only_since_a_retry(tmp_path):
    after_retry = long_task("FAKE:continue", 3, reviewed_at="0")
    assert "Last review" not in review.evidence(after_retry, str(tmp_path))
    task = long_task("FAKE:continue", 30, reviewed_at=25, review_note="continue: ok")
    text = review.evidence(task, str(tmp_path))
    assert "Last review, after 25 sessions: continue: ok" in text


def test_evidence_copes_without_git_or_runs(tmp_path):
    task = long_task("FAKE:continue", 25)
    text = review.evidence(task, str(tmp_path))
    assert "Sessions counted: 25" in text
    assert "- none recorded" in text and "not in a git repo" in text


# ---- the boss runs the review -----------------------------------------------------


def test_review_runs_before_session_26_and_continue_carries_on(world):
    task = long_task("FAKE:continue REVIEW:continue", 25)
    world.boss.tick()
    assert task_(task["id"])["status"] == "reviewing"
    active = runs.active()
    assert [r["kind"] for r in active] == ["review"]
    assert active[0]["effort"] == "medium"
    prompt = world.calls(1)[0]["prompt"]
    assert "Relay's reviewer for task" in prompt and "Sessions counted: 25" in prompt
    assert "next review comes after 35 sessions" in prompt
    wait_runs()
    world.boss.tick()  # the verdict, then the next work session in the same tick
    after = task_(task["id"])
    assert after["reviewed_at"] in (25, "25")
    assert after["review_note"] == "continue: fake reason for continue"
    assert after["status"] == "running" and after["attempts"] in (26, "26")
    assert [r["kind"] for r in runs.active()] == ["work"]
    assert not world.mail.sent  # carrying on is not news for his phone


def test_review_park_sends_his_phone_one_line(world):
    task = long_task("FAKE:continue REVIEW:park", 25)
    world.boss.tick()
    wait_runs()
    world.boss.tick()
    after = task_(task["id"])
    assert after["status"] == "parked"
    assert after["note"] == "review after 25 sessions: fake reason for park"
    sent = world.mail.sent[-1]
    assert sent["subject"].endswith("Parked: Long job")
    assert sent["body"] == (
        f"Task {task['id']} parked after 25 sessions: fake reason for park\n"
        f"Say retry {task['id']} to run it again."
    )
    assert len(world.calls()) == 1  # no work session after the park
    # and the hint in that message works from WhatsApp
    cmd = commands.parse("", f"retry {task['id']}", source="whatsapp")
    assert cmd.kind == "retry" and cmd.number == int(task["id"])


@pytest.mark.parametrize("answer", ["error", "none"])
def test_review_that_fails_tries_again_then_carries_on(world, answer):
    """No verdict twice does not park the task: a wrong park costs more than
    a few sessions (critic, task 112). The next review comes 10 later."""
    task = long_task(f"FAKE:continue REVIEW:{answer}", 25)
    world.boss.tick()
    wait_runs()
    world.boss.tick()  # first failure: queued and the review starts again
    again = task_(task["id"])
    assert again["review_fails"] in (1, "1") and again["status"] == "reviewing"
    wait_runs()
    world.boss.tick()  # second failure: it carries on with a work session
    after = task_(task["id"])
    assert after["status"] == "running" and after["reviewed_at"] in (25, "25")
    assert after["review_fails"] in (0, "0")
    assert after["review_note"].startswith("no verdict in 2 tries")
    assert [r["kind"] for r in runs.active()] == ["work"]
    assert not any("Parked" in m["subject"] for m in world.mail.sent)
    prompts_sent = [c["prompt"] for c in world.calls(3)]
    assert all("Relay's reviewer" in p for p in prompts_sent[:2])
    assert "Relay's reviewer" not in prompts_sent[2]


def test_review_that_grows_too_big_is_cut_off(world):
    store.save_settings({"hand_over_context_k": 10})  # the fake reads 20k
    task = long_task("FAKE:continue REVIEW:sleep", 25)
    world.boss.tick()
    first = runs.active()[0]
    assert first["kind"] == "review"
    end = time.time() + 5
    while not runs.summary(first)["context_tokens"] and time.time() < end:
        time.sleep(0.05)
    world.boss.tick()  # cut off: a try without a verdict, then the review again
    after = task_(task["id"])
    assert after["review_fails"] in (1, "1") and after["status"] == "reviewing"
    assert any("too big, ended" in e["text"] for e in store.events())
    left = runs.active()
    assert [r["kind"] for r in left] == ["review"] and left[0]["id"] != first["id"]
    for run in left:
        runs.stop(run)


def test_note_during_a_review_goes_into_the_request(world):
    task = long_task("FAKE:continue REVIEW:continue", 25)
    world.boss.tick()
    assert task_(task["id"])["status"] == "reviewing"
    said = actions.tell_task(task["id"], "use the second key")
    assert "being reviewed right now" in said
    during = task_(task["id"])
    assert during["status"] == "reviewing" and "use the second key" in during["body"]
    wait_runs()
    world.boss.tick()  # the verdict keeps the note; the next session reads it
    after = task_(task["id"])
    assert after["reviewed_at"] in (25, "25") and "use the second key" in after["body"]


def test_a_task_left_reviewing_goes_back_to_the_queue(world):
    """A stale save of its file won a race with the verdict: no review runs,
    yet it says reviewing. The boss puts it back in the queue."""
    task = long_task("FAKE:continue", 25, reviewed_at=25)
    task.update(status="reviewing", review_run="gone")
    items.save(task)
    world.boss.tick()
    assert task_(task["id"])["status"] in ("queued", "running")
    assert any("left reviewing" in e["text"] for e in store.events())
    wait_runs()


def test_stop_while_its_notes_are_gathered(world, monkeypatch):
    task = long_task("FAKE:continue REVIEW:continue", 25)

    def notes(*args, **kwargs):
        actions.stop_task(task["id"])
        return "notes"

    monkeypatch.setattr(review, "evidence", notes)
    world.boss.tick()
    assert task_(task["id"])["status"] == "stopped"
    assert runs.active() == []


def test_a_note_never_saves_a_stale_copy():
    task = long_task("FAKE:continue", 25)
    stale = dict(task_(task["id"]), status="reviewing")
    fresh = task_(task["id"])
    fresh.update(status="queued", reviewed_at=25, review_note="continue: fine")
    items.save(fresh)  # the verdict lands after the caller read the task
    chat.add_to_task(stale, "one more thing", queue=False)
    after = task_(task["id"])
    assert after["status"] == "queued" and after["reviewed_at"] in (25, "25")
    assert "one more thing" in after["body"]


def test_his_answer_to_a_blocked_task_counts_as_a_review():
    task = long_task("FAKE:continue", 30, status="blocked", fails=1)
    chat.add_to_task(task, "the key is in the vault")
    after = task_(task["id"])
    assert after["status"] == "queued" and after["reviewed_at"] in (30, "30")
    assert not picker.review_due(after, S)


def test_a_clean_session_resets_failures(world):
    """Failures park only in a row: with no session cap, two stray errors in
    a long working task must not stop it (critic, task 112)."""
    task = long_task("FAKE:continue", 40, reviewed_at=35, fails=1)
    world.boss.tick()
    wait_runs()
    path = Path(task_(task["id"])["path"])
    path.write_text(path.read_text().replace("FAKE:continue", "FAKE:error"))
    world.boss.tick()  # the clean session resets fails; the next one errs
    assert task_(task["id"])["fails"] in (0, "0")
    wait_runs()
    world.boss.tick()
    after = task_(task["id"])
    assert after["status"] != "parked" and after["fails"] in (1, "1")
    for run in runs.active():
        runs.stop(run)


def test_review_on_a_usage_limit_just_waits(world):
    task = long_task("FAKE:continue REVIEW:limit", 25)
    world.boss.tick()
    wait_runs()
    world.boss.tick()
    after = task_(task["id"])
    assert after["status"] in ("queued", "reviewing")  # b may take it at once
    assert after.get("review_fails") in (None, "", 0, "0")
    assert world.boss.state["limited"]


def test_no_cap_past_fifty(world):
    task = long_task("FAKE:continue", 60, reviewed_at=55)
    world.boss.tick()
    assert [r["kind"] for r in runs.active()] == ["work"]
    wait_runs()
    world.boss.tick()
    after = task_(task["id"])
    assert after["status"] != "parked" and int(after["attempts"]) >= 61


def test_the_whatsapp_chat_is_never_reviewed(world, monkeypatch):
    """The chat task counts a session per answer (the live one is past 90):
    it never gets a review, whatever its count, even while it waits because
    its own launcher could not start it yet."""
    task = chat.chat_task()
    assert task is not None
    task.update(attempts=90, status="queued")
    items.save(task)
    monkeypatch.setattr(boss_mod.Boss, "chat_now", lambda self, now: None)
    world.boss.tick()
    assert task_(task["id"])["status"] != "reviewing"
    assert "review" not in [r["kind"] for r in runs.all_runs()]


def test_continue_at_13_sessions_is_not_parked(world):
    """What happened to task 102: parked at its 13th session while working."""
    task = long_task("FAKE:continue", 12)
    world.boss.tick()
    wait_runs()
    world.boss.tick()
    assert task_(task["id"])["status"] != "parked"
    assert not any("Parked" in m["subject"] for m in world.mail.sent)


def test_retry_starts_the_count_again(world):
    task = long_task("FAKE:continue", 25, reviewed_at=25, review_fails=1)
    task.update(status="parked", review_note="park: no progress")
    items.save(task)
    actions.retry_task(task["id"])
    after = task_(task["id"])
    assert after["attempts"] in (0, "0") and after["reviewed_at"] in (0, "0")
    assert after["review_fails"] in (0, "0") and after["review_note"] == ""
    assert not picker.review_due(after, store.settings())


def test_work_runs_record_state_and_their_id(world):
    task = items.new_task("Short", "FAKE:done")
    world.boss.tick()
    run = [r for r in runs.all_runs() if r["kind"] == "work"][0]
    assert run["state_before"] == items.state_mark(task["body"])
    assert world.calls(1)[0]["run_id"] == run["id"]


# ---- a session close to finishing (relay finishing) -------------------------------


def test_finishing_grace_is_a_setting():
    s = {**S, "finishing_minutes": 45}
    assert not picker.finishing({}, s, 1000)
    assert picker.finishing({"finishing": 1000}, s, 1000 + 44 * 60)
    assert not picker.finishing({"finishing": 1000}, s, 1000 + 45 * 60)


def test_no_finishing_time_when_it_is_zero():
    store.save_settings({"finishing_minutes": 0})
    task = items.new_task("Short", "FAKE:done")
    work = fake_run(task, time.time(), 0, "x")
    work.pop("ended")
    runs.save(work)
    assert actions.finishing(work["id"]).startswith("Relay gives no finishing time")
    assert "finishing" not in run_file(work["id"])
    assert not picker.finishing({"finishing": 1000}, store.settings(), 1000)


def test_finishing_session_stays_past_the_move_line(world):
    store.save_settings({"account_limits": {"a": {"move_at": 80}}})
    task = items.new_task("Nearly done", "FAKE:sleep")
    world.boss.tick()
    run = runs.active()[0]
    assert run["account"] == "a"
    assert actions.finishing(run["id"]).startswith("Noted")
    world.readings["a"]["five"] = 82
    world.boss.tick()
    assert task_(task["id"])["status"] == "running"
    assert [r["id"] for r in runs.active()] == [run["id"]]
    world.readings["a"]["five"] = 96  # the usage hand-over still applies
    world.boss.tick()
    assert task_(task["id"])["status"] == "handing_over"
    task_file = Path(task_(task["id"])["path"])
    task_file.write_text(task_file.read_text().replace("FAKE:sleep", "FAKE:done"))
    settle(world)


def test_finishing_command_only_for_running_work(world):
    assert actions.finishing("").startswith("Only a running Relay work session")
    assert actions.finishing("../../etc").startswith("Only")
    task = items.new_task("Short", "FAKE:done")
    review_run = fake_run(task, time.time(), 0, "x", kind="review")
    review_run.pop("ended")
    runs.save(review_run)
    assert actions.finishing(review_run["id"]).startswith("Only")
    work = fake_run(task, time.time(), 0, "x")
    work.pop("ended")
    runs.save(work)
    assert actions.finishing(work["id"]).startswith("Noted")
    first = run_file(work["id"])["finishing"]
    actions.finishing(work["id"])  # a second call does not move the clock
    assert run_file(work["id"])["finishing"] == first


def test_finishing_session_is_not_handed_over_for_context(world):
    store.save_settings({"hand_over_context_k": 10})  # the fake runs at 20k
    task = items.new_task("Nearly done", "FAKE:sleep")
    world.boss.tick()
    run = runs.active()[0]
    end = time.time() + 5
    while not runs.summary(run)["context_tokens"] and time.time() < end:
        time.sleep(0.05)
    assert actions.finishing(run["id"]).startswith("Noted")
    world.boss.tick()
    assert task_(task["id"])["status"] == "running"  # left alone
    assert any(e["kind"] == "finishing" for e in store.events())
    # once its finishing time is up, the usual hand-over follows
    run = run_file(run["id"])
    assert run["finishing_seen"] is True
    run["finishing"] = time.time() - 46 * 60
    runs.save(run)
    world.boss.tick()
    assert task_(task["id"])["status"] == "handing_over"
    assert any("finishing time ran out" in e["text"] for e in store.events())
    task_file = Path(task_(task["id"])["path"])  # the next session ends at once
    task_file.write_text(task_file.read_text().replace("FAKE:sleep", "FAKE:done"))
    settle(world, ticks=1)


def test_session_rules_tell_about_finishing_and_commit_tags():
    assert "relay finishing" in prompts.RULES
    assert "(Relay task <your task number>)" in prompts.RULES
