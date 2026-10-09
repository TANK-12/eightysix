"""Goal and task files: markdown with a small `key: value` front matter.

The boss owns the front matter (status, account, attempts...). A session owns
the body: it reads the request and keeps the State section current, ending it
with one status line the boss reads when the session exits:

    - status: done
    - status: continue
    - status: blocked: <what Emerson has to do>

A task file a planning session drops into tasks/<goal>/ without a number
(any name not starting with four digits) is adopted on the next tick: it gets
the next id, a front matter and a proper name.
"""

from __future__ import annotations

import re
import time
import zlib
from pathlib import Path

import store

TASK_NAME = re.compile(r"^(\d{4})-[\w-]*\.md$")
STATUS_LINE = re.compile(
    r"^[ \t]*[-*]?[ \t]*status:[ \t]*(done|continue|blocked)\b:?[ \t]*(.*)$",
    re.I | re.M,
)
# Statuses the boss may launch, and ones that mean "a session holds it".
WAITING = ("queued",)
ACTIVE = ("running", "handing_over", "reviewing")
PRIORITIES = ("normal", "important")


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug[:limit].strip("-") or "task"


def parse(text: str) -> tuple[dict, str]:
    meta: dict = {}
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                key, sep, value = line.partition(":")
                if sep and key.strip():
                    meta[key.strip()] = value.strip()
            text = text[end + 4 :].lstrip("\n")
    return meta, text


def dump(meta: dict, body: str) -> str:
    lines = ["---"]
    for key, value in meta.items():
        value = "" if value is None else str(value)
        lines.append(f"{key}: {' '.join(value.split())}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body.strip() + "\n"


def _load(file: Path) -> dict:
    meta, body = parse(file.read_text(encoding="utf-8"))
    return {**meta, "body": body, "path": str(file)}


def save(item: dict) -> None:
    meta = {k: v for k, v in item.items() if k not in ("body", "path")}
    store.write_text(Path(item["path"]), dump(meta, item.get("body", "")))


def num(item: dict, key: str, default: float = 0) -> float:
    try:
        return float(item.get(key) or default)
    except ValueError:
        return default


# ---- tasks -------------------------------------------------------------


def task_files() -> list[Path]:
    return sorted(store.path("tasks").glob("*/*.md"))


def all_tasks() -> list[dict]:
    tasks = []
    for file in task_files():
        if TASK_NAME.match(file.name):
            try:
                tasks.append(_load(file))
            except OSError:
                continue
    tasks.sort(key=lambda t: int(t.get("id") or 0))
    return tasks


def find_task(task_id) -> dict | None:
    wanted = str(task_id).lstrip("#").lstrip("0") or "0"
    for task in all_tasks():
        if (str(task.get("id") or "").lstrip("0") or "0") == wanted:
            return task
    return None


def next_id() -> int:
    ids = [int(m.group(1)) for f in task_files() if (m := TASK_NAME.match(f.name))]
    return max(ids, default=0) + 1


def task_body(title: str, request: str, done_when: str = "") -> str:
    return (
        f"# {title}\n\n## Request\n\n{request.strip()}\n\n"
        f"## Done when\n\n{done_when.strip() or 'The request is carried out and checked.'}\n\n"
        "## State\n\n- status: not started\n"
    )


def new_task(
    title: str,
    request: str,
    goal: str = "inbox",
    priority: str = "normal",
    folder: str = "",
    done_when: str = "",
    **extra,
) -> dict:
    store.ensure()
    title = " ".join(str(title).split())[:120] or "Task"
    tid = next_id()
    file = store.path("tasks", goal, f"{tid:04d}-{slugify(title)}.md")
    task = {
        "id": tid,
        "title": title,
        "goal": goal,
        "priority": priority if priority in PRIORITIES else "normal",
        "folder": folder,
        "status": "queued",
        "created": round(time.time()),
        "attempts": 0,
        "fails": 0,
        **{k: v for k, v in extra.items() if v not in (None, "")},
        "body": task_body(title, request, done_when),
        "path": str(file),
    }
    save(task)
    return task


def state_status(body: str) -> tuple[str | None, str]:
    """The last status line of the State section: (done|continue|blocked, note)."""
    _, sep, state = body.partition("## State")
    found = STATUS_LINE.findall(state if sep else body)
    if not found:
        return None, ""
    word, note = found[-1]
    return word.lower(), note.strip()


def state_mark(body: str) -> int:
    """A fingerprint of the State section, to tell whether a session wrote to it."""
    return zlib.crc32(body.partition("## State")[2].encode())


def adopt_new(goal: str) -> list[dict]:
    """Number the task files a planning session wrote for `goal`."""
    adopted = []
    folder = store.path("tasks", goal)
    for file in sorted(folder.glob("*.md")):
        if TASK_NAME.match(file.name):
            continue
        meta, body = parse(file.read_text(encoding="utf-8"))
        heading = re.search(r"^#\s+(.+)$", body, re.M)
        title = meta.get("title") or (heading.group(1) if heading else file.stem)
        tid = next_id()
        task = {
            "id": tid,
            "title": " ".join(title.split())[:120],
            "goal": goal,
            "priority": meta.get("priority", ""),
            "folder": meta.get("folder", ""),
            "status": "queued",
            "created": round(time.time()),
            "attempts": 0,
            "fails": 0,
            "body": (
                body
                if "## State" in body
                else body + "\n\n## State\n\n- status: not started\n"
            ),
            "path": str(folder / f"{tid:04d}-{slugify(title)}.md"),
        }
        save(task)
        file.unlink()
        adopted.append(task)
    return adopted


# ---- goals -------------------------------------------------------------


def all_goals() -> list[dict]:
    goals = []
    for file in sorted(store.path("goals").glob("*.md")):
        try:
            goals.append(_load(file))
        except OSError:
            continue
    return goals


def find_goal(slug: str) -> dict | None:
    file = store.path("goals", f"{slug}.md")
    return _load(file) if file.is_file() else None


def new_goal(
    title: str,
    text: str = "",
    priority: str = "normal",
    folder: str = "",
    check: str = "",
) -> dict:
    store.ensure()
    title = " ".join(str(title).split())[:120] or "Goal"
    slug = base = slugify(title, 30)
    n = 2
    while store.path("goals", f"{slug}.md").exists() or slug == "inbox":
        slug, n = f"{base}-{n}", n + 1
    goal = {
        "slug": slug,
        "title": title,
        "priority": priority if priority in PRIORITIES else "normal",
        "folder": folder,
        "check": check,
        "status": "active",
        "created": round(time.time()),
        "plans": 0,
        "body": f"# {title}\n\n{text.strip()}\n\n## Log\n",
        "path": str(store.path("goals", f"{slug}.md")),
    }
    save(goal)
    store.path("tasks", slug).mkdir(parents=True, exist_ok=True)
    return goal


def log_goal(goal: dict, line: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M")
    goal["body"] = goal.get("body", "").rstrip() + f"\n- {stamp} {line}\n"
    save(goal)
