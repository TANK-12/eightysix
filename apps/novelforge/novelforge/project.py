"""
On-disk model for a single book (Project) and for a Series that groups books.

    ~/NovelMakerData/projects/<name>/
        bible.json      story bible + outline + series linkage
        state.json      generation progress, per-chapter summaries & word counts
        codex.json      the World Codex
        chapters/chapter_001.txt ...
        manuscript.md   compiled, rewritten after every chapter (human-readable)

    ~/NovelMakerData/series/<name>/
        series.json     ordered list of book project names + a rolling series bible
"""

import difflib
import glob
import json
import os
import re
import shutil
import time

from .config import PROJECTS_DIR, SERIES_DIR, TRASH_DIR
from .codex import default_codex


def slugify(name):
    s = re.sub(r"[^\w\-. ]+", "", (name or "").strip()).strip()
    s = re.sub(r"\s+", "_", s)
    # No leading dot: "." and ".." would name the folder itself or its parent.
    s = s.lstrip(".")
    return s or "untitled"


BIBLE_DEFAULTS = {
    "title": "",
    "genre": "",
    "protagonist": "",
    "plot": "",
    "pinned_facts": "",
    "inspiration_notes": "",
    "style_directives": "",  # free text the user wants obeyed every chapter
    "world_doc": "",  # the full rich Free-Rein worldbuilding prose
    "outline": "",
    "chapter_list": [],
    "chapter_roles": [],  # each chapter's job from the genre preset
    "preset": "",  # genre preset id; blank = guess from genre
    # scope
    "story_scope": "series",  # "oneshot" | "series"
    "planned_books": 1,
    "arc_synopsis": "",  # overarching multi-book arc (series only)
    "series": "",  # series slug this book belongs to (optional)
    "book_index": 1,
    "series_context": "",  # canon carried in from earlier books
    # continuity
    "open_threads": [],  # unresolved plot threads to honour / pay off
}

STATE_DEFAULTS = {
    "current_chapter": 0,
    "target_chapters": 30,
    "target_words_per_chapter": 3500,
    "recent_full_chapters": 2,
    "chapter_summaries": {},
    "chapter_words": {},
    "chapter_beats": {},
    "running_synopsis": "",  # evolving "story so far", refreshed each chapter
    "last_model": "",
}


# What each reset part clears. Title, scope and series links always stay.
RESET_PARTS = ("bible", "outline", "world_doc", "codex", "chapters", "memory")
BIBLE_TEXT_FIELDS = (
    "genre",
    "protagonist",
    "plot",
    "pinned_facts",
    "inspiration_notes",
    "style_directives",
    "preset",
)


def move_to_trash(path, label):
    """Move a file or folder into TRASH_DIR under a unique name; returns
    where it went, or "" when there was nothing to move."""
    if not os.path.exists(path):
        return ""
    os.makedirs(TRASH_DIR, exist_ok=True)
    dest = os.path.join(TRASH_DIR, f"{slugify(label)}-{time.strftime('%Y%m%d-%H%M%S')}")
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = f"{dest.rsplit('~', 1)[0]}~{n}"
    shutil.move(path, dest)
    return dest


def tidy_field(key, text):
    """Drop a pasted label that repeats the field's own name ('Pinned facts:
    ...' typed into Pinned facts, even misspelt), so it is not fed to the
    model on every call. Only the very start of the text is touched."""
    text = text or ""
    m = re.match(r"\s*([A-Za-z][A-Za-z ]{1,30}):[ \t]*", text)
    if not m:
        return text
    label = key.replace("_", " ").lower()
    if difflib.SequenceMatcher(None, m.group(1).strip().lower(), label).ratio() >= 0.8:
        return text[m.end() :]
    return text


class Project:
    @staticmethod
    def exists(name):
        return os.path.isdir(os.path.join(PROJECTS_DIR, slugify(name)))

    def __init__(self, name):
        self.name = slugify(name)
        self.dir = os.path.join(PROJECTS_DIR, self.name)
        self.chapters_dir = os.path.join(self.dir, "chapters")
        os.makedirs(self.chapters_dir, exist_ok=True)
        self.bible_path = os.path.join(self.dir, "bible.json")
        self.state_path = os.path.join(self.dir, "state.json")
        self.codex_path = os.path.join(self.dir, "codex.json")
        self.manuscript_path = os.path.join(self.dir, "manuscript.md")

        self.bible = dict(BIBLE_DEFAULTS)
        self.state = json.loads(json.dumps(STATE_DEFAULTS))  # deep copy
        self.codex = default_codex()
        self.load()

    # ---------------- persistence ----------------
    def load(self):
        if os.path.exists(self.bible_path):
            try:
                with open(self.bible_path, encoding="utf-8") as f:
                    self.bible.update(json.load(f))
            except Exception:
                pass
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, encoding="utf-8") as f:
                    self.state.update(json.load(f))
            except Exception:
                pass
        if os.path.exists(self.codex_path):
            try:
                with open(self.codex_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                for k in default_codex():
                    if k in loaded:
                        self.codex[k] = loaded[k]
            except Exception:
                pass
        if not self.bible.get("title"):
            self.bible["title"] = (
                self.name.strip("_").replace("_", " ").title() or self.name
            )

    def save(self):
        with open(self.bible_path, "w", encoding="utf-8") as f:
            json.dump(self.bible, f, ensure_ascii=False, indent=2)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def save_codex(self):
        with open(self.codex_path, "w", encoding="utf-8") as f:
            json.dump(self.codex, f, ensure_ascii=False, indent=2)

    # ---------------- chapters ----------------
    def chapter_path(self, n):
        return os.path.join(self.chapters_dir, f"chapter_{n:03d}.txt")

    def save_chapter(self, n, text):
        with open(self.chapter_path(n), "w", encoding="utf-8") as f:
            f.write(text.strip() + "\n")
        self.state["chapter_words"][str(n)] = len(text.split())

    def load_chapter(self, n):
        p = self.chapter_path(n)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
        return ""

    def chapter_count(self):
        n = 0
        while os.path.exists(self.chapter_path(n + 1)):
            n += 1
        return n

    def total_words(self):
        return sum(int(v) for v in self.state.get("chapter_words", {}).values()) or sum(
            len(self.load_chapter(i).split())
            for i in range(1, self.chapter_count() + 1)
        )

    def is_final_book(self):
        """A one-shot is always 'final'; a series book is final when it's the
        last planned one. Governs whether the closing chapter resolves the
        whole story or just this book + a hook."""
        b = self.bible
        if (
            b.get("story_scope", "series") == "oneshot"
            or b.get("planned_books", 1) <= 1
        ):
            return True
        return int(b.get("book_index", 1)) >= int(b.get("planned_books", 1))

    def scope_label(self):
        b = self.bible
        if (
            b.get("story_scope", "series") == "oneshot"
            or b.get("planned_books", 1) <= 1
        ):
            return "One-shot"
        return f"Series · book {b.get('book_index', 1)} of {b.get('planned_books', 1)}"

    def chapter_title(self, n):
        goals = self.bible.get("chapter_list") or []
        if 0 < n <= len(goals):
            g = goals[n - 1]
            if " | " in g:
                return g.split(" | ")[0].strip()[:70]
            g = g.split(".")[0].split(" -- ")[0].strip()
            return g[:70]
        return ""

    # ---------------- editing, deleting, resetting ----------------
    def set_outline_lines(self, lines):
        """Replace the outline with hand-edited lines. A chapter whose line
        changed loses its cached scene beats, so it is re-planned."""
        old = list(self.bible.get("chapter_list") or [])
        beats = self.state.setdefault("chapter_beats", {})
        for i, line in enumerate(lines):
            if i >= len(old) or old[i] != line:
                beats.pop(str(i + 1), None)
        for i in range(len(lines), len(old)):
            beats.pop(str(i + 1), None)
        roles = list(self.bible.get("chapter_roles") or [])
        self.bible["chapter_list"] = list(lines)
        self.bible["chapter_roles"] = roles[: len(lines)]
        self.bible["outline"] = "\n".join(
            f"{i + 1}. {ln}" for i, ln in enumerate(lines)
        )

    def trash(self):
        return move_to_trash(self.dir, f"project-{self.name}")

    def rewind(self, from_chapter):
        """Delete chapter `from_chapter` and everything after it (moved to the
        trash). The story-so-far digest is cleared because it describes the
        removed chapters; per-chapter summaries of the kept ones stay."""
        from_chapter = max(1, int(from_chapter))
        # Every chapter file from there on, also past a gap (1, 2, 4).
        names = (
            os.listdir(self.chapters_dir) if os.path.isdir(self.chapters_dir) else []
        )
        found = (re.fullmatch(r"chapter_(\d+)\.txt", f) for f in names)
        doomed = sorted(
            n for n in (int(m.group(1)) for m in found if m) if n >= from_chapter
        )
        if not doomed:
            return 0
        base = os.path.join(
            TRASH_DIR, f"{self.name}-chapters-{time.strftime('%Y%m%d-%H%M%S')}"
        )
        folder, k = base, 1
        while os.path.exists(folder):  # a second rewind in the same second
            k += 1
            folder = f"{base}~{k}"
        os.makedirs(folder)
        for n in doomed:
            path = self.chapter_path(n)
            shutil.move(path, os.path.join(folder, os.path.basename(path)))
        for key in ("chapter_words", "chapter_summaries", "chapter_beats"):
            bucket = self.state.get(key) or {}
            for k in list(bucket):
                if k.isdigit() and int(k) >= from_chapter:
                    bucket.pop(k)
        self.state["current_chapter"] = min(
            self.state.get("current_chapter", 0), from_chapter - 1
        )
        self.state["running_synopsis"] = ""
        self.compile_manuscript()
        return len(doomed)

    def reset(self, parts):
        """Clear the chosen parts (see RESET_PARTS). Returns what was reset."""
        done = []
        for part in parts:
            if part == "bible":
                for k in BIBLE_TEXT_FIELDS:
                    self.bible[k] = BIBLE_DEFAULTS[k]
                self.bible["open_threads"] = []
            elif part == "outline":
                self.bible["outline"] = ""
                self.bible["chapter_list"] = []
                self.bible["chapter_roles"] = []
                self.state["chapter_beats"] = {}
            elif part == "world_doc":
                self.bible["world_doc"] = ""
            elif part == "codex":
                self.codex = default_codex()
                self.save_codex()
            elif part == "chapters":
                if self.chapter_count():
                    self.rewind(1)
                self.state["current_chapter"] = 0
                self.state["chapter_words"] = {}
            elif part == "memory":
                self.state["chapter_summaries"] = {}
                self.state["running_synopsis"] = ""
                self.state["chapter_beats"] = {}
                self.bible["open_threads"] = []
            else:
                continue
            done.append(part)
        self.save()
        return done

    def delete_codex_entry(self, bucket, key):
        """Remove one character/location/faction by name, or one fact by its
        exact text. Returns True when something was removed."""
        if bucket == "facts":
            facts = self.codex.get("facts") or []
            if key in facts:
                facts.remove(key)
                self.save_codex()
                return True
            return False
        if bucket in ("characters", "locations", "factions") and key in self.codex.get(
            bucket, {}
        ):
            del self.codex[bucket][key]
            self.save_codex()
            return True
        return False

    # ---------------- compiled manuscript ----------------
    def compile_manuscript(self):
        b = self.bible
        parts = [f"# {b.get('title') or self.name}", ""]
        if b.get("genre"):
            parts.append(f"*{b['genre']}*")
        if b.get("book_index", 1) and b.get("series"):
            parts.append(
                f"*{b['series'].replace('_', ' ').title()} — Book {b['book_index']}*"
            )
        parts.append("")
        for n in range(1, self.chapter_count() + 1):
            title = self.chapter_title(n)
            head = f"## Chapter {n}" + (f" — {title}" if title else "")
            parts.append(head)
            parts.append("")
            parts.append(self.load_chapter(n).strip())
            parts.append("")
        text = "\n".join(parts)
        try:
            with open(self.manuscript_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
        return text

    def synopsis(self, max_words=180):
        """A short blurb for feeding this book into a later book as canon."""
        summaries = self.state.get("chapter_summaries", {})
        if summaries:
            ordered = [
                summaries[str(i)]
                for i in range(1, self.chapter_count() + 1)
                if str(i) in summaries
            ]
            joined = " ".join(ordered)
            return " ".join(joined.split()[:max_words])
        return " ".join((self.bible.get("plot") or "").split()[:max_words])

    # ---------------- discovery ----------------
    @staticmethod
    def list_all():
        if not os.path.isdir(PROJECTS_DIR):
            return []
        return sorted(
            d
            for d in os.listdir(PROJECTS_DIR)
            if os.path.isdir(os.path.join(PROJECTS_DIR, d))
        )

    @staticmethod
    def quick_stats(name):
        """Cheap stats for the Home list without fully instantiating."""
        d = os.path.join(PROJECTS_DIR, name)
        chs = len(glob.glob(os.path.join(d, "chapters", "chapter_*.txt")))
        genre = ""
        try:
            with open(os.path.join(d, "bible.json"), encoding="utf-8") as f:
                genre = json.load(f).get("genre", "")
        except Exception:
            pass
        words = 0
        try:
            with open(os.path.join(d, "state.json"), encoding="utf-8") as f:
                words = sum(
                    int(v) for v in json.load(f).get("chapter_words", {}).values()
                )
        except Exception:
            pass
        return {"chapters": chs, "genre": genre, "words": words}


class Series:
    def __init__(self, name):
        self.name = slugify(name)
        self.dir = os.path.join(SERIES_DIR, self.name)
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "series.json")
        self.data = {
            "title": name,
            "books": [],  # ordered project slugs
            "planned_books": 1,
            "arc_synopsis": "",  # the overarching multi-book arc
            "book_meta": {},  # slug -> {"title","one_line","status"}
            "world_doc": "",  # shared worldbuilding document
            "shared_codex": default_codex(),
        }
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass
        self.data.setdefault("shared_codex", default_codex())
        self.data.setdefault("book_meta", {})

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def exists(name):
        return os.path.isdir(os.path.join(SERIES_DIR, slugify(name)))

    def trash(self):
        """Move the series folder to the trash and unlink its books (the
        books themselves are kept)."""
        for slug in self.data.get("books", []):
            if Project.exists(slug):
                p = Project(slug)
                if p.bible.get("series") == self.name:
                    p.bible["series"] = ""
                    p.save()
        return move_to_trash(self.dir, f"series-{self.name}")

    def remove_book(self, project_name):
        if project_name in self.data["books"]:
            self.data["books"].remove(project_name)
        self.data["book_meta"].pop(project_name, None)
        self.save()
        if Project.exists(project_name):
            p = Project(project_name)
            if p.bible.get("series") == self.name:
                p.bible["series"] = ""
                p.bible["book_index"] = 1
                p.save()

    def add_book(self, project_name, title="", one_line=""):
        if project_name not in self.data["books"]:
            self.data["books"].append(project_name)
        self.data["book_meta"].setdefault(project_name, {})
        if title:
            self.data["book_meta"][project_name]["title"] = title
        if one_line:
            self.data["book_meta"][project_name]["one_line"] = one_line
        self.data["book_meta"][project_name].setdefault("status", "planned")
        self.save()

    def set_status(self, project_name, status):
        self.data["book_meta"].setdefault(project_name, {})["status"] = status
        self.save()

    def book_one_line(self, index):
        """The planned one-paragraph arc for book <index> (1-based), if known."""
        if 1 <= index <= len(self.data["books"]):
            slug = self.data["books"][index - 1]
            return self.data["book_meta"].get(slug, {}).get("one_line", "")
        return ""

    def book_index_of(self, project_name):
        try:
            return self.data["books"].index(project_name) + 1
        except ValueError:
            return len(self.data["books"]) + 1

    @staticmethod
    def list_all():
        if not os.path.isdir(SERIES_DIR):
            return []
        return sorted(
            d
            for d in os.listdir(SERIES_DIR)
            if os.path.isdir(os.path.join(SERIES_DIR, d))
        )
