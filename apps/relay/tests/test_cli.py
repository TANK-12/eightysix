import io
import sys

import cli
import items


def task_(number) -> dict:
    found = items.find_task(number)
    assert found is not None
    return found


def goal_(slug) -> dict:
    found = items.find_goal(slug)
    assert found is not None
    return found


def test_cli_request_and_status(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    cli.main(["important", "fix", "the", "thing"])
    assert "task 1 queued" in capsys.readouterr().out
    task = task_(1)
    assert task["title"] == "important fix the thing"
    cli.main(["status"])
    out = capsys.readouterr().out
    assert "Queued (1)" in out and "boss has not ticked" in out


def test_cli_long_request_from_stdin(capsys, monkeypatch):
    monkeypatch.setattr(
        sys, "stdin", io.StringIO("important\nfolder: /tmp\n\nA long job.\nWith lines.")
    )
    cli.main([])
    task = task_(1)
    assert task["priority"] == "important" and task["folder"] == "/tmp"
    assert "With lines." in task["body"]


def test_cli_goal_may_set_check(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    cli.main(["goal: Docs tidy\ncheck: true\nall of them"])
    goal = items.all_goals()[0]
    assert goal["check"] == "true" and goal["title"] == "Docs tidy"


def test_tell_posts_a_note_to_the_running_session(monkeypatch):
    import actions
    import items

    task = actions.add_task(commands_parse("make the fog nicer"), "cli", "", "")
    posted = []
    monkeypatch.setattr(actions, "_crew", lambda *args: posted.append(args) or True)
    reply = actions.tell_task(task["id"], "keep the old sky")
    assert "not running" in reply and not posted
    task["status"] = "running"
    items.save(task)
    reply = actions.tell_task(task["id"], "keep the old sky")
    assert posted and posted[0][-1] == f"relay-{task['id']}-work"
    assert "keep the old sky" in posted[0][-3]
    assert f"task {task['id']}" in reply
    assert "no task" in actions.tell_task(999, "hi").lower()


def commands_parse(text):
    from commands import parse

    return parse("", text, source="cli")


def test_cli_help_flag_prints_usage_not_a_task(capsys):
    for flag in ("--help", "-h"):
        assert cli.main([flag]) == 0
        out = capsys.readouterr().out
        assert "relay status" in out and "relay reply" in out
    assert items.find_task(1) is None
