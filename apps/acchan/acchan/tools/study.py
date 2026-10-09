"""Emerson's course material, the same files Study Companion teaches from.

Courses are discovered the way Study Companion discovers them: every folder
under its data/ holding .txt sources is a course (MATH1014 today). Questions
are answered from the best-matching passages across all of a course's files,
so "how do limits at infinity work in my calculus class?" needs no path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from ..registry import ToolError, tool
from .docs import best_passages

TOOLSET = "study"
TOOLSET_SUMMARY = "Emerson's university courses (Study Companion's material): list topics, answer questions from the course notes"

TOOLSET_KEYWORDS = (
    "course",
    "class",
    "unit",
    "uni",
    "university",
    "lecture",
    "revision",
    "exam",
    "study",
    "topic",
    "math1014",
    "calculus",
    "maths class",
    "math class",
    "limits",
    "derivative",
    "differentiation",
    "trig",
    "logarithm",
    "homework",
)
TOOLSET_EXAMPLES = [
    (
        "in my calculus class, how do limits at infinity work?",
        "ask_course",
        {"question": "limits at infinity", "course": ""},
    ),
    ("what topics are in my maths course?", "course_topics", {"course": ""}),
]

DATA = Path.home() / "Forge" / "apps" / "study-companion" / "data"


def courses() -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    if DATA.is_dir():
        for folder in sorted(DATA.iterdir()):
            files = sorted(folder.glob("*.txt")) if folder.is_dir() else []
            if files:
                found[folder.name] = files
    return found


def _pick(course: str) -> tuple[str, list[Path]]:
    known = courses()
    if not known:
        raise ToolError(
            "No course material found (Study Companion's data folder is empty)."
        )
    if not course:
        name = next(iter(known))
        return name, known[name]
    for name, files in known.items():
        if (
            course.lower().replace(" ", "") in name.lower()
            or name.lower() in course.lower()
        ):
            return name, files
    if len(known) == 1:  # "my calculus class" when the only course is MATH1014
        name = next(iter(known))
        return name, known[name]
    raise ToolError(f"No course called {course!r}. Courses: {', '.join(known)}.")


@tool(TOOLSET, example={"course": ""}, voice="ok")
def course_topics(
    course: Annotated[str, "Course code or name; empty for the main course"] = "",
) -> str:
    """List Emerson's courses and the topic files of one course."""
    name, files = _pick(course)
    others = [c for c in courses() if c != name]
    topics = "\n".join(f"- {f.stem}" for f in files)
    more = f"\nOther courses: {', '.join(others)}" if others else ""
    return f"{name} topics:\n{topics}{more}"


@tool(TOOLSET, example={"question": "chain rule", "course": ""}, voice="ok")
def ask_course(
    question: Annotated[str, "What to find in the course notes"],
    course: Annotated[str, "Course code or name; empty for the main course"] = "",
) -> str:
    """Find the passages of Emerson's course notes that answer a question. Answer from them and say which topic they came from."""
    name, files = _pick(course)
    corpus = "\n\n".join(
        f"[topic {file.stem}]\n\n" + file.read_text(encoding="utf-8", errors="replace")
        for file in files
    )
    hits = best_passages(corpus, question, k=4, size=1100)
    return f"From the {name} notes:\n\n" + "\n\n---\n\n".join(hits)
