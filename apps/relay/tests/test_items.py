import items
import store


def task_(number) -> dict:
    found = items.find_task(number)
    assert found is not None
    return found


def goal_(slug) -> dict:
    found = items.find_goal(slug)
    assert found is not None
    return found


def test_task_round_trip():
    task = items.new_task(
        "Fix the orbit bug", "Planets drift.\nMake them stop.", priority="important"
    )
    again = task_(task["id"])
    assert again["title"] == "Fix the orbit bug"
    assert again["priority"] == "important"
    assert again["status"] == "queued"
    assert "Planets drift." in again["body"] and "## State" in again["body"]
    assert again["path"].endswith("/tasks/inbox/0001-fix-the-orbit-bug.md")
    again["status"] = "running"
    items.save(again)
    assert task_("1")["status"] == "running"
    assert task_("#0001")["id"] == "1"


def test_ids_keep_counting():
    a = items.new_task("one", "x")
    b = items.new_task("two", "y", goal="other")
    assert (a["id"], b["id"]) == (1, 2)


def test_state_status_reads_last_line():
    body = items.task_body("t", "r")
    assert items.state_status(body) == (None, "")
    body += "- did a thing\n- status: continue\n"
    assert items.state_status(body)[0] == "continue"
    body += "- status: blocked: needs the Gmail password\n"
    assert items.state_status(body) == ("blocked", "needs the Gmail password")
    body += "- Status: DONE\n"
    assert items.state_status(body)[0] == "done"


def test_request_status_words_do_not_count():
    body = items.task_body("t", "write status: done into a file")
    assert items.state_status(body) == (None, "")


def test_goal_round_trip_and_log():
    goal = items.new_goal("Emberfield boots", "It should boot.", check="true")
    found = goal_(goal["slug"])
    assert found["check"] == "true" and found["status"] == "active"
    items.log_goal(found, "check passed")
    assert "check passed" in goal_(goal["slug"])["body"]
    assert items.new_goal("Emberfield boots")["slug"] == "emberfield-boots-2"


def test_adopt_planner_files():
    goal = items.new_goal("Big job")
    folder = store.path("tasks", goal["slug"])
    (folder / "new-first-step.md").write_text(
        "---\npriority: important\n---\n# First step\n\n## Request\n\nDo it.\n"
    )
    adopted = items.adopt_new(goal["slug"])
    assert len(adopted) == 1
    task = task_(adopted[0]["id"])
    assert task["title"] == "First step" and task["priority"] == "important"
    assert task["goal"] == goal["slug"] and "## State" in task["body"]
    assert not (folder / "new-first-step.md").exists()
