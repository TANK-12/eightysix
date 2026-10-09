"""
Continuation / Never-Ending Story mode.

Feed in 1–12 (or more) PDFs of an existing series or an author's body of work.
NovelForge reads them, learns the voice, rebuilds the world codex and a
"story so far", notes where the last book ended, and then keeps writing new
chapters in that same style and universe — indefinitely, and optionally with a
deliberate "spin" (alternate POV, time-skip, side-character spin-off, genre
shift, what-if branch).

The ingested material lands in an ordinary Project, so every existing feature —
the generation engine, manuscript compile, PDF export, the codex viewer — works
on it unchanged. Two bible flags drive the continuation-aware behaviour in
engine.py / memory.py:

    bible["continuation_mode"]  = True
    bible["seed_tail"]          = the last ~1500 words of the final source book
    bible["spin_directive"]     = free-text "spin" instruction (may be empty)
    bible["source_books"]       = [titles...]
"""

import os
import re

from .stylelib import StyleLibrary, PDF_OK
from .jsonrepair import strip_reasoning, coerce_world, as_text_list
from .codex import merge_codex, default_codex, codex_stats
from .textquality import strip_scaffolding, is_degenerate


SPIN_PRESETS = {
    "None — straight continuation": "",
    "Alternate POV": "Tell the continuation primarily from the point of view of a "
        "different established character than the original books' main narrator.",
    "Time-skip": "Open the continuation a significant span of time after the last "
        "book ended; show how the world and the characters have changed.",
    "Side-character spin-off": "Centre the continuation on a compelling secondary "
        "character from the source books; the original protagonist becomes a "
        "supporting figure.",
    "Genre shift": "Keep the world and cast but lean the continuation into a "
        "different genre register than the source books.",
    "What-if branch": "Branch from a pivotal choice or event near the end of the "
        "source books and follow the road not taken, as an alternate continuation.",
}

_MAX_CHUNK_ANALYSIS = 9000


def _clean(t):
    return strip_scaffolding(strip_reasoning(t or "")).strip()


# --------------------------------------------------------------------------
# Narrative voice detection
#
# "Continue exactly as the author did" fails mostly on two things: the POV
# person and the tense silently drifting. Counting pronouns and verb markers in
# the real prose is far more reliable than asking a small local model, so the
# counts decide and the model is only asked for the POV character's name.
# Dialogue is stripped first -- otherwise every "I" a character speaks reads as
# first-person narration.
# --------------------------------------------------------------------------
_QUOTED = re.compile(r"[“\"][^”\"]{0,4000}[”\"]")

_FIRST = re.compile(r"\b(I|I'm|I'd|I'll|I've|me|my|mine|myself|we|us|our|ours)\b")
_SECOND = re.compile(r"\b(you|your|yours|yourself)\b")
_THIRD = re.compile(r"\b(he|him|his|she|her|hers|they|them|their|theirs)\b")

_PAST = re.compile(r"\b(was|were|had|did|said|could|would|thought|knew|felt|went|came|"
                   r"looked|turned|took|saw|made|told|asked|seemed|stood|walked)\b", re.I)
_PRESENT = re.compile(r"\b(is|are|has|does|says|can|will|thinks|knows|feels|goes|comes|"
                      r"looks|turns|takes|sees|makes|tells|asks|seems|stands|walks)\b", re.I)


def narration_only(text):
    """Prose with quoted dialogue removed."""
    return _QUOTED.sub(" ", text or "")


def detect_narrative_profile(text, sample_chars=60000):
    """-> {"pov", "tense", "confidence"} measured from the author's own prose."""
    prose = narration_only(text or "")[:sample_chars]
    if len(prose.split()) < 200:
        return {}

    first, second, third = (len(r.findall(prose)) for r in (_FIRST, _SECOND, _THIRD))
    total = first + second + third or 1
    if first / total > 0.28:
        pov, share = "first person", first / total
    elif second / total > 0.30:
        pov, share = "second person", second / total
    else:
        pov, share = "third person", third / total

    past, present = len(_PAST.findall(prose)), len(_PRESENT.findall(prose))
    tense = "past tense" if past >= present else "present tense"
    t_share = max(past, present) / max(past + present, 1)

    return {"pov": pov, "tense": tense,
            "confidence": round(min(share, t_share), 2),
            "counts": {"first": first, "second": second, "third": third,
                       "past": past, "present": present}}


def profile_line(profile):
    """The one-line absolute rule injected into every prompt."""
    if not profile or not profile.get("pov"):
        return ""
    who = (profile.get("pov_character") or "").strip()
    bits = [f"{profile['pov']}, {profile.get('tense', 'past tense')}"]
    if who and profile["pov"] != "third person":
        bits.append(f"narrated by {who}")
    elif who:
        bits.append(f"following {who}")
    return " · ".join(bits)


class CorpusIngest:
    """Runs on a worker thread. `log(str)` streams progress to the UI."""

    def __init__(self, project, client, model, style_lib, settings, log, kill=None):
        self.p = project
        self.client = client
        self.model = model
        self.style = style_lib
        self.s = settings
        self.log = log
        self.kill = kill

    # -- low-level model call (structured, low temp) -----------------------
    def _ask(self, system, user, max_tokens=900, temperature=0.3):
        try:
            comp = self.client.complete(self.model, system, user, max_tokens=max_tokens,
                                        temperature=temperature, kill=self.kill,
                                        label="ingesting")
            return _clean(comp.text)
        except Exception as e:
            self.log(f"  model call failed: {e}")
            return ""

    # -- main entry ------------------------------------------------------
    def run(self, pdf_paths, spin_directive="", extra_notes=""):
        if not PDF_OK:
            raise RuntimeError("PDF reading needs pypdf. Run:  pip install pypdf")
        if not pdf_paths:
            raise RuntimeError("Add at least one PDF first.")

        books = []           # [(title, full_text)]
        for path in pdf_paths:
            if self.kill and self.kill.any:
                break
            base = os.path.splitext(os.path.basename(path))[0]
            self.log(f"Reading {base}…")
            try:
                text = StyleLibrary.extract_pdf_text(path)
            except Exception as e:
                self.log(f"  couldn't read {base}: {e}")
                continue
            wc = len(text.split())
            if wc < 400:
                self.log(f"  {base}: only {wc} words extracted — skipping (scanned image PDF?).")
                continue
            self.log(f"  {base}: {wc:,} words.")
            books.append((self._title_from(base, text), text))

        if not books:
            raise RuntimeError("No readable text came out of those PDFs.")

        books = self._order_books(books)
        titles = [t for t, _ in books]
        self.log(f"Corpus: {len(books)} book(s) — {', '.join(titles)}")

        # 1) house style, from an even sample across the whole corpus -------
        self.log("Learning the house style…")
        style_src_name = f"{self.p.name} · source corpus"
        sample = self._even_sample(books, chars=14000)
        style_notes = self._ask(
            "You are a literary style analyst. Describe patterns abstractly; never "
            "quote more than three consecutive words.",
            "From these excerpts of an author's work, write a STYLE GUIDE as tight "
            "bullet points (<240 words): sentence rhythm and length, narration "
            "distance and POV, tense, dialogue habits, humour, pacing, paragraphing, "
            "recurring devices and diction. Patterns only.\n\n" + sample,
            max_tokens=700, temperature=0.3)
        if style_notes:
            self.style.data["sources"][style_src_name] = {
                "chunks": StyleLibrary._chunk(self._even_sample(books, chars=40000)),
                "style_notes": style_notes, "content_summary": "",
                "enabled": True, "word_count": sum(len(t.split()) for _, t in books),
            }
            self.style.save()
            self.log("  style guide learned and enabled.")

        # 2) per-book synopses + combined "story so far" -------------------
        self.log("Summarising each book…")
        per_book = []
        for i, (title, text) in enumerate(books, 1):
            if self.kill and self.kill.any:
                break
            syn = self._ask(
                "You are a precise, spoiler-tolerant continuity analyst.",
                f"Summarise this book for a series record in 8–12 sentences. Name "
                f"characters and places explicitly; cover the main arc, the ending, "
                f"and every thread left open.\n\nBOOK {i}: {title}\n\n"
                + self._book_digest(text),
                max_tokens=800, temperature=0.25)
            per_book.append(f"BOOK {i} — {title}:\n{syn}")
            self.log(f"  book {i}/{len(books)} summarised.")

        running = self._ask(
            "You maintain a running 'story so far' digest for a novelist.",
            "Combine these per-book summaries into ONE continuous 'story so far' "
            "digest of 4–6 tight paragraphs: the through-line across all books, "
            "where each major character stands at the very end, the state of the "
            "world, and everything still unresolved.\n\n" + "\n\n".join(per_book),
            max_tokens=1100, temperature=0.25)

        # 3) codex from the corpus ---------------------------------------
        self.log("Indexing characters, places, factions and world rules…")
        self.p.codex = default_codex()
        world_digest = self._even_sample(books, chars=16000)
        raw = self._ask(
            "You are a story-bible indexer. Extract every named entity thoroughly. No prose.",
            "Index this material.\n\n" + world_digest + "\n\n"
            'Return ONLY JSON: {"characters":{"Name":{"desc":"","traits":["",""],'
            '"relationships":{"Other":""},"status":""}},"locations":{"Name":{"desc":""}},'
            '"factions":{"Name":{"desc":""}},"facts":["hard world rule"]}',
            max_tokens=3500, temperature=0.25)
        world = coerce_world(raw)
        merge_codex(self.p.codex, world, chapter_n=0)
        # a second loose pass over the summaries catches names the sample missed
        merge_codex(self.p.codex, coerce_world("\n\n".join(per_book)), chapter_n=0)
        self.p.save_codex()
        st = codex_stats(self.p.codex)
        self.log(f"  codex: {st['characters']} characters, {st['locations']} places, "
                 f"{st['factions']} factions, {st['facts']} facts.")

        # 4) open threads ----------------------------------------------
        threads_raw = self._ask(
            "You track unresolved plot threads for continuity.",
            "From this 'story so far', list every plot thread, mystery, promise or "
            "relationship left UNRESOLVED at the end. One per line, terse.\n\n" + running,
            max_tokens=600, temperature=0.2)
        threads = [t for t in as_text_list(threads_raw) if len(t) > 4][:20]

        # 4b) narrative voice — measured, not guessed ------------------
        self.log("Measuring narrative voice (POV + tense)…")
        profile = detect_narrative_profile("\n\n".join(t for _n, t in books))
        if profile:
            who = self._ask(
                "You identify the viewpoint character of a novel. Answer with a name only.",
                "Whose point of view is this story told from? Reply with ONLY the "
                "character's name exactly as spelled in the text, nothing else.\n\n"
                + self._even_sample(books, chars=6000),
                max_tokens=40, temperature=0.1)
            who = re.sub(r"[^\w '\-.]", "", (who or "").splitlines()[0] if who else "").strip()
            # only trust a name the codex already knows -- small models invent
            if who and who in self.p.codex.get("characters", {}):
                profile["pov_character"] = who
            elif who:
                match = next((c for c in self.p.codex.get("characters", {})
                              if who.lower() in c.lower() or c.lower() in who.lower()), "")
                if match:
                    profile["pov_character"] = match
            c = profile.get("counts", {})
            self.log(f"  {profile_line(profile)}  (confidence {profile.get('confidence')}; "
                     f"1st/3rd pronouns {c.get('first')}/{c.get('third')}, "
                     f"past/present {c.get('past')}/{c.get('present')})")

        # 4c) canonical spellings — the exact names the author used ----
        roster = sorted(self.p.codex.get("characters", {}).keys())
        places = sorted(self.p.codex.get("locations", {}).keys())

        # 5) the seed tail — how the last book actually ends ------------
        _, last_text = books[-1]
        seed_tail = " ".join(last_text.split()[-1600:])

        # 6) genre + a one-line premise for the continuation -----------
        meta = self._ask(
            "You extract one-line summaries. Be concrete, use real character names.",
            f"{running}\n\nGive exactly two lines:\nGENRE: <a few words>\n"
            "PREMISE: <2–3 sentences describing a compelling next chapter of this "
            "story — a new problem for the established cast that follows naturally "
            "from where things stand>",
            max_tokens=400, temperature=0.4)
        genre = _first_field(meta, "genre")
        premise = _first_field(meta, "premise")

        # -- write it all into the project bible -----------------------
        b = self.p.bible
        b["continuation_mode"] = True
        b["source_books"] = titles
        b["seed_tail"] = seed_tail
        if profile:
            b["narrative_profile"] = profile
        b["canon_names"] = roster[:80]
        b["canon_places"] = places[:60]
        b["spin_directive"] = spin_directive or ""
        b["story_scope"] = "series"
        b["planned_books"] = 99                      # never a "finale"
        b["book_index"] = len(books) + 1
        b["genre"] = genre or b.get("genre", "")
        b["protagonist"] = b.get("protagonist") or _guess_protagonist(self.p.codex)
        b["plot"] = premise or "Continue the saga for the established cast."
        b["world_doc"] = ("CONTINUATION SOURCE — story so far across "
                          f"{len(books)} book(s): {', '.join(titles)}\n\n" + running)
        if extra_notes.strip():
            b["inspiration_notes"] = (b.get("inspiration_notes", "") + "\n\n" + extra_notes).strip()
        b["open_threads"] = threads
        if style_notes:
            b["style_directives"] = (b.get("style_directives", "").strip()
                                     + "\nMatch the house style guide exactly.").strip()
        self.p.state["running_synopsis"] = running
        self.p.save()

        self.log(f"Ingest complete. '{self.p.name}' is ready to continue the story of "
                 f"{', '.join(titles)}. Set the chapter count on the Continue tab and run.")
        return {
            "titles": titles, "codex_stats": st, "threads": threads,
            "running_synopsis": running, "style_notes": style_notes,
            "genre": genre, "premise": premise, "narrative_profile": profile,
        }

    # -- helpers -------------------------------------------------------
    def _title_from(self, filename, text):
        # a filename like "Author - 03 - The Broken Crown" -> "The Broken Crown"
        cleaned = re.sub(r"[_]+", " ", filename).strip()
        parts = [p.strip() for p in re.split(r"\s[-–—]\s", cleaned) if p.strip()]
        cand = parts[-1] if parts else cleaned
        if 2 < len(cand) < 80:
            return cand
        return cleaned[:80] or "Untitled"

    def _order_books(self, books):
        """Best-effort chronological order from a number in the filename/title."""
        def key(item):
            title = item[0]
            m = re.search(r"\b(\d{1,2})\b", title)
            return int(m.group(1)) if m else 999
        if any(re.search(r"\b\d{1,2}\b", t) for t, _ in books):
            return sorted(books, key=key)
        return books

    def _book_digest(self, text, chars=_MAX_CHUNK_ANALYSIS):
        """Beginning + middle + end of a book, so a summary sees the whole arc."""
        words = text.split()
        if len(" ".join(words)) <= chars:
            return text
        per = chars // 3 // 6           # ~words per slice
        head = " ".join(words[:per])
        mid = " ".join(words[len(words) // 2 - per // 2: len(words) // 2 + per // 2])
        tail = " ".join(words[-per:])
        return f"{head}\n\n[...]\n\n{mid}\n\n[...]\n\n{tail}"

    def _even_sample(self, books, chars=14000):
        """An even spread of excerpts across every book in the corpus."""
        out, per = [], max(1200, chars // max(len(books), 1))
        for title, text in books:
            words = text.split()
            step = max(1, len(words) // 4)
            slabs = [" ".join(words[i:i + per // 5])
                     for i in range(0, len(words), step)][:4]
            out.append(f"[{title}]\n" + "\n…\n".join(s for s in slabs if s))
        return ("\n\n---\n\n".join(out))[:chars]


def _first_field(text, name):
    m = re.search(rf"(?im)^\s*{name}\s*[:\-]\s*(.+)$", text or "")
    return m.group(1).strip() if m else ""


def _guess_protagonist(codex):
    chars = codex.get("characters", {})
    return next(iter(chars), "")
