"""The outline pipeline, built so that a small model can follow it.

Old behaviour: one prompt asked for a batch of up to 40 chapter lines, and any
batch that came back unusable was padded with "Advance the central conflict; a
setback forces X to change tactics". Those filler lines then drove whole
chapters.

Now:

* **Code decides the shape.** Each chapter gets a job from the genre preset's
  structure template (`presets.chapter_roles`): hook, awakening, midpoint
  reveal, arc boss... The model never has to invent the book's structure.
* **Small batches, one fixed line format**:
  `N. Title | what happens (who, where) | what changes | hook`, with one good
  and one bad example in the prompt and the rules repeated at the very end
  (small models follow the last thing they read).
* **Every line is checked** (`check_line`): four parts, sane length, names a
  known character, not vague, not a near-copy of another chapter, no names
  borrowed from the example.
* **A failed line is asked for again, alone, with the reason.** If it still
  fails, the outline stops there and is saved as far as it got. No filler is
  ever written; "Continue outline" picks up from the gap.
* **Careful mode** adds one critique pass that rewrites the weakest chapters.
"""

from __future__ import annotations

import re

from .codex import format_codex
from .jsonrepair import strip_reasoning
from .memory import _trim
from .presets import chapter_roles

LINE_RE = re.compile(r"^\s*(?:chapter\s*)?(\d{1,3})\s*[.:)\-]\s*(.+?)\s*$", re.I)
WORD_RE = re.compile(r"[a-z0-9]+(?:['\-][a-z0-9]+)*")

# Lines that say nothing concrete. Matched as lowercase substrings.
VAGUE = (
    "advance the central conflict",
    "a complication raises the stakes",
    "the story continues",
    "things get worse",
    "things get harder",
    "tension builds",
    "tensions rise",
    "the stakes rise",
    "the plot thickens",
    "something happens",
    "events unfold",
    "faces new challenges",
    "new challenges",
    "a new challenge",
    "learns more about",
    "deals with the consequences",
    "the journey continues",
    "change tactics",
    "something is coming",
)
PLACEHOLDERS = ("<", ">", "...", "…", "tbd", "[title]", "what happens", "hook into")
STOPWORDS = frozenset(
    "a an the and or but of to in on at by for with from into onto over under "
    "his her their its he she they him them it is are was were be been being "
    "as that this these those who whom what when where while then than so "
    "not no yet all any some one two up down out off about after before again "
    "has have had do does did can could will would should may might must".split()
)
BAD_EXAMPLE = (
    "Things get harder | The hero faces new challenges | He grows stronger "
    "| Something is coming"
)
TITLES = frozenset(
    "the a an lord lady sir mr mrs ms dr young master elder guild captain "
    "director senior junior brother sister duke grand".split()
)


def content_words(text: str) -> set[str]:
    return {w for w in WORD_RE.findall((text or "").lower()) if w not in STOPWORDS}


def similarity(a: str, b: str) -> float:
    """Word-overlap (Jaccard) of two lines' content words, 0..1."""
    wa, wb = content_words(a), content_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def protagonist_name(field: str) -> str:
    """'Kang Jin-Woo - stoic - proud' -> 'Kang Jin-Woo'. Hyphens inside a
    name stay; spaced dashes, commas and brackets end it."""
    head = re.split(r"\s[-–—]\s|[,(;:|]|\s—|—\s", field or "")[0]
    return head.strip().strip(".")


def known_names(bible: dict, codex: dict) -> list[str]:
    names = []
    proto = protagonist_name(bible.get("protagonist", ""))
    if proto:
        names.append(proto)
    for name in (codex or {}).get("characters", {}):
        if name and name not in names:
            names.append(name)
    for name in bible.get("canon_names") or []:
        if name and name not in names:
            names.append(name)
    return names


def name_tokens(names: list[str]) -> set[str]:
    """Lowercase pieces of each name a line may use to refer to someone
    ('kang', 'jin-woo', and 'jin'/'woo' for a model that drops the hyphen),
    minus titles like 'Lord' that prove nothing."""
    out = set()
    for name in names:
        for piece in WORD_RE.findall(name.lower()):
            if piece in TITLES:
                continue
            if len(piece) >= 2:
                out.add(piece)
            if "-" in piece:
                out.update(p for p in piece.split("-") if len(p) >= 3)
    return out


def line_tokens(text: str) -> set[str]:
    """Words of a line, with possessives also counted bare (jin-woo's)."""
    out = set()
    for w in WORD_RE.findall((text or "").lower()):
        out.add(w)
        if w.endswith("'s"):
            out.add(w[:-2])
        if "-" in w:
            out.update(w.split("-"))
    return out


def example_names(preset: dict, allowed: set[str]) -> set[str]:
    """The names used in the preset's example line (its `example_names`),
    minus any this story really has, so a line that copied the example is
    caught."""
    return name_tokens(list(preset.get("example_names") or [])) - allowed


def split_line(text: str) -> list[str]:
    return [p.strip().strip("*").strip() for p in (text or "").split("|")]


def check_line(
    text: str,
    others: list[str],
    names: set[str],
    banned: set[str] | None = None,
) -> str | None:
    """Why a chapter line is unusable, or None when it is fine."""
    parts = split_line(text)
    if len(parts) < 4 or not all(parts[:4]):
        return "it must have four parts separated by | : title | what happens | what changes | hook"
    title, event = parts[0], parts[1]
    low = text.lower()
    for ph in PLACEHOLDERS:
        if ph in low:
            return "it still contains template text; replace it with the real event"
    for ph in VAGUE:
        if ph in low:
            return f"it is vague ('{ph}'); name a concrete event instead"
    if len(title.split()) > 12:
        return "the title is too long (keep it under ten words)"
    words = len(" ".join(parts).split())
    if words < 14:
        return "it is too short; say who does what, where, and what changes"
    if words > 110:
        return "it is too long; one line of about 30 to 60 words"
    if len(content_words(event)) < 4:
        return "the 'what happens' part is too thin; name who does what, where"
    tokens = line_tokens(text)
    if names and not tokens & names:
        return "it names none of the story's characters; use their real names"
    if banned and tokens & banned:
        return "it borrows names from the example; use this story's own names"
    for i, other in enumerate(others):
        if other and similarity(text, other) >= 0.6:
            return f"it repeats another chapter's line too closely (line {i + 1})"
    return None


def parse_batch(raw: str, lo: int, hi: int) -> dict[int, str]:
    """{chapter number: line text} from a model reply. Numbered lines are
    taken by their number; if the model dropped the numbers, lines with '|'
    are taken in order."""
    text = strip_reasoning(raw or "")
    found: dict[int, str] = {}
    loose = []
    for ln in text.splitlines():
        s = ln.strip().strip("*").strip()
        if not s:
            continue
        m = LINE_RE.match(s)
        if m and lo <= int(m.group(1)) <= hi:
            found.setdefault(int(m.group(1)), m.group(2).strip())
        elif "|" in s and not m:
            loose.append(s.lstrip("-* ").strip())
    if not found and loose:
        for i, s in enumerate(loose[: hi - lo + 1]):
            found[lo + i] = s
    return found


def render_outline(lines: list[str]) -> str:
    return "\n".join(f"{i + 1}. {ln}" for i, ln in enumerate(lines))


def parse_outline_text(text: str) -> list[str]:
    """An outline edited by hand, back into one line per chapter. A leading
    '12.' / '12:' / 'Chapter 12 -' is dropped; blank lines are ignored."""
    out = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        m = LINE_RE.match(s)
        out.append(m.group(2).strip() if m else s)
    return out


def batch_size(profile: dict) -> int:
    return max(1, int(profile.get("outline_batch", 4)))


class OutlineBuilder:
    """Runs the pipeline for one NovelEngine (its model calls, log and kill
    switch are reused; the outline is written by the engine's planner)."""

    def __init__(self, engine, preset: dict):
        self.e = engine
        self.p = engine.p
        self.preset = preset
        self.retries = int(engine.s.get("outline_line_retries", 2))

    # ---------------------------------------------------------------- prompts
    def _story_block(self, target: int) -> str:
        b = self.p.bible
        e = self.e
        lines = [
            f"Genre: {b.get('genre', '') or self.preset.get('label', '')}",
            f"Protagonist: {b.get('protagonist', '')}",
            f"Premise: {b.get('plot', '')}",
        ]
        if b.get("pinned_facts", "").strip():
            lines.append(f"Fixed facts (never contradict): {b['pinned_facts'].strip()}")
        if b.get("style_directives", "").strip():
            lines.append(f"Author directives: {b['style_directives'].strip()}")
        world_budget = {"tiny": 500, "small": 900, "medium": 1600}.get(
            e.profile.get("label", ""), 2400
        )
        if b.get("world_doc", "").strip():
            lines.append(f"World notes:\n{_trim(b['world_doc'].strip(), world_budget)}")
        cx = format_codex(self.p.codex, max_chars=min(2200, world_budget * 2))
        if cx:
            lines.append(f"Established cast and places:\n{cx}")
        threads = [t for t in b.get("open_threads", []) if str(t).strip()]
        if threads:
            lines.append(
                "Threads to weave in and pay off:\n"
                + "\n".join(f"- {t}" for t in threads)
            )
        lines.append(e.outline_scope_note(target))
        return "\n".join(x for x in lines if x)

    def _system(self) -> str:
        pr = self.preset
        return (
            f"You are a story architect planning a {pr.get('label', 'novel')} chapter by "
            "chapter. "
            + (pr.get("outline_guidance") or "")
            + " Each line names who does "
            "what, where, and what changes, using the story's real character names spelled "
            "exactly. Never write vague lines such as 'tension builds' or 'the hero faces "
            "new challenges'. Output only the numbered lines."
        )

    def _format_rules(self, names: list[str]) -> str:
        who = ", ".join(names[:12])
        return (
            "FORMAT: one line per chapter, exactly four parts separated by |\n"
            "<number>. <title> | <what happens: who does what, where> | <what changes> "
            "| <the hook into the next chapter>\n"
            + (f"Use these names: {who}.\n" if who else "")
        )

    def _examples(self) -> str:
        good = self.preset.get("outline_example") or ""
        out = ""
        if good:
            out += (
                "A good line (from a different story; never reuse its names or events):\n"
                f"7. {good}\n"
            )
        out += f"A bad line (never write like this):\n7. {BAD_EXAMPLE}\n"
        return out

    def _batch_prompt(self, target, roles, lines, lo, hi, names, final_note):
        planned = ""
        if lines:
            start = max(0, len(lines) - 6)
            shown = "\n".join(f"{i + 1}. {lines[i]}" for i in range(start, len(lines)))
            planned = (
                f"ALREADY PLANNED ({len(lines)} chapters"
                + (", last six shown" if start else "")
                + f"):\n{shown}\n\n"
            )
        jobs = "\n".join(
            f"{r['chapter']}. [{r['role']}] {r['guide']}" for r in roles[lo - 1 : hi]
        )
        return (
            f"{self._story_block(target)}\n\n{planned}"
            f"WRITE CHAPTERS {lo} TO {hi} of {target}. Each chapter's job:\n{jobs}\n"
            + (f"{final_note}\n" if hi == target and final_note else "")
            + f"\n{self._examples()}\n{self._format_rules(names)}"
            f"Write chapters {lo} to {hi} now: {hi - lo + 1} numbered lines, four parts "
            "each, nothing else."
        )

    def _single_prompt(
        self, target, roles, lines, c, names, reason, previous, final_note
    ):
        r = roles[c - 1]
        prev = (
            f"\nThe previous chapter is:\n{c - 1}. {lines[c - 2]}\n"
            if c > 1 and len(lines) >= c - 1
            else ""
        )
        rejected = (
            f"\nThis attempt was rejected: {previous}\nReason: {reason}\n"
            if previous
            else f"\nReason for asking again: {reason}\n"
        )
        return (
            f"{self._story_block(target)}\n{prev}"
            f"\nWRITE CHAPTER {c} of {target}. Its job: [{r['role']}] {r['guide']}\n"
            + (f"{final_note}\n" if c == target and final_note else "")
            + rejected
            + f"\n{self._examples()}\n{self._format_rules(names)}"
            f"Write only chapter {c}'s line now, starting with '{c}.'"
        )

    # --------------------------------------------------------------- the run
    def _ask(self, system, user, n_lines):
        e = self.e
        return e._structured(
            system,
            user,
            max_tokens=min(2400, 120 * n_lines + 300),
            temperature=e.s.get("structure_temperature", 0.3) + 0.3,
            model=e.planner,
        )

    def _names(self):
        names = known_names(self.p.bible, self.p.codex)
        allowed = name_tokens(names)
        banned = example_names(self.preset, allowed)
        return names, allowed, banned

    def build(self, target: int, keep_existing=False, careful=False):
        """Returns (lines, complete). Saves the outline as far as it got."""
        e, b = self.e, self.p.bible
        target = max(1, int(target))
        roles = chapter_roles(self.preset.get("structure") or [], target)
        names, allowed, banned = self._names()
        final_note = e.outline_final_note(target)
        system = self._system()
        lines = list(b.get("chapter_list") or [])[:target] if keep_existing else []
        size = batch_size(e.profile)
        stopped = None
        if not allowed:
            e.log(
                "  no character names known yet: the outline can't check names. "
                "Fill in the protagonist or run Free-Rein first for a better outline."
            )

        while len(lines) < target and not stopped:
            if e.kill and e.kill.any:
                stopped = "stopped by you"
                break
            lo = len(lines) + 1
            hi = min(target, lo + size - 1)
            e.log(f"  outline: asking for chapters {lo}-{hi}…")
            raw = self._ask(
                system,
                self._batch_prompt(target, roles, lines, lo, hi, names, final_note),
                hi - lo + 1,
            )
            got = parse_batch(raw, lo, hi)
            for c in range(lo, hi + 1):
                line = got.get(c, "")
                reason = (
                    check_line(line, lines, allowed, banned)
                    if line
                    else "the reply had no line for this chapter"
                )
                tries = 0
                while reason and tries < self.retries and not (e.kill and e.kill.any):
                    tries += 1
                    e.log(
                        f"    chapter {c} rejected ({reason}); asking again ({tries}/{self.retries})."
                    )
                    raw1 = self._ask(
                        system,
                        self._single_prompt(
                            target, roles, lines, c, names, reason, line, final_note
                        ),
                        1,
                    )
                    line = parse_batch(raw1, c, c).get(c, "")
                    reason = (
                        check_line(line, lines, allowed, banned)
                        if line
                        else "the reply had no line for this chapter"
                    )
                if reason:
                    stopped = f"chapter {c}: {reason}"
                    break
                lines.append(line)
            self._save(lines, roles, target)
            e.log(f"  outline: {len(lines)}/{target} chapters.")

        if not stopped and careful and len(lines) == target:
            self._critique(
                target, roles, lines, names, allowed, banned, final_note, system
            )
            self._save(lines, roles, target)

        if stopped:
            e.log(
                f"Outline stopped at {len(lines)}/{target} chapters ({stopped}). "
                "It is saved as far as it got. Press Continue outline to try the rest "
                "(a bigger planner model helps), or write the missing lines yourself."
            )
        return lines, not stopped

    def _critique(
        self, target, roles, lines, names, allowed, banned, final_note, system
    ):
        e = self.e
        e.log("  careful mode: asking for the weakest chapters…")
        raw = e._structured(
            "You are a demanding story editor. Be specific and brief.",
            f"{self._story_block(target)}\n\nOUTLINE:\n{render_outline(lines)}\n\n"
            "Name up to three of the weakest chapters: vague, repetitive, out of "
            "character, or not doing their job. One per line: 'N: reason'. If all are "
            "strong, write OK.",
            max_tokens=400,
            temperature=0.2,
            model=e.planner,
        )
        if raw.strip().upper().startswith("OK"):
            e.log("  careful mode: the editor found nothing to fix.")
            return
        for m in re.finditer(r"(?m)^\s*(\d{1,3})\s*[:.)\-]\s*(.+)$", raw):
            c, why = int(m.group(1)), m.group(2).strip()
            if not 1 <= c <= len(lines) or (e.kill and e.kill.any):
                continue
            others = lines[: c - 1] + lines[c:]
            raw1 = self._ask(
                system,
                self._single_prompt(
                    target,
                    roles,
                    lines,
                    c,
                    names,
                    f"an editor said: {why}",
                    lines[c - 1],
                    final_note,
                ),
                1,
            )
            new = parse_batch(raw1, c, c).get(c, "")
            if new and not check_line(new, others, allowed, banned):
                e.log(f"    chapter {c} rewritten ({why}).")
                lines[c - 1] = new
                self.p.state.get("chapter_beats", {}).pop(str(c), None)

    def _save(self, lines, roles, target):
        b = self.p.bible
        b["chapter_list"] = list(lines)
        b["chapter_roles"] = [r["role"] for r in roles[: len(lines)]]
        b["outline"] = render_outline(lines)
        self.p.state["target_chapters"] = target
        self.p.save()
