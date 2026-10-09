"""
The generation engine.

What it does differently from the earlier scripts / earlier NovelForge:

* LENGTH  -- a chapter is planned into scene beats; each beat is streamed and,
  if it stalls under target, nudged to continue (bounded). The loop keeps
  adding prose until the words-per-chapter target is met or the scene cap hits.

* ANTI-COLLAPSE -- every prose call carries DRY + light repetition penalties
  (small local models loop without them). Output is checked for degeneration
  and for prompt-scaffolding leakage; a looping scene is retried once hotter,
  then trimmed to its healthy prefix; a whole chapter that still reads as a
  loop is NOT saved (the old code saved 8000-word loops and poisoned every
  later chapter's context with them).

* GROUNDING -- scenes are told to use real character names from the codex, to
  make something happen, and to include dialogue; abstract "prose-poem" output
  is detected and retried.

* SCOPE -- one-shot vs an N-book series changes the outline shape, the closing
  chapters, and how books are saved and chained.

* MEMORY -- per-chapter summary + a rolling "story so far" synopsis + open-thread
  tracking + periodic codex reconciliation, so a 30-chapter book stops
  forgetting (and stops contradicting) itself.
"""

import re
import time

from .config import WORLD_DEPTH
from .jsonrepair import (
    strip_reasoning,
    extract_json,
    coerce_world,
    coerce_codex_update,
    parse_outline,
    parse_beats,
    as_text_list,
)
from .codex import (
    merge_codex,
    default_codex,
    format_codex,
    codex_stats,
    codex_is_empty,
    apply_reconcile,
)
from .textquality import (
    strip_scaffolding,
    is_degenerate,
    healthy_prefix,
    looks_abstract,
    repetition_report,
    count_phrases,
)
from .memory import MemoryManager, _trim
from .janclient import JanError, ram_is_low, free_jan_memory
from .outline import OutlineBuilder, protagonist_name
from .presets import preset_for_bible, all_cliches
from .rag import Retriever, format_block

_HEADER_RE = re.compile(
    r"^\s{0,3}(#{1,4}\s*)?(chapter|scene|part)\s+[\w\d]+\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


def _clean_prose(text):
    t = strip_reasoning(text or "")
    t = strip_scaffolding(t)
    t = re.sub(r"```[a-z]*", "", t)
    t = _HEADER_RE.sub("", t, count=1)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _wc(t):
    return len((t or "").split())


class NovelEngine:
    def __init__(
        self,
        project,
        client,
        model,
        style_lib,
        profile,
        settings,
        log,
        progress=None,
        stream=None,
        kill=None,
        planner=None,
    ):
        self.p = project
        self.client = client
        self.model = model
        # The model that plans (outline). Defaults to the writer; a separate
        # planner only swaps in for outline building, never mid-chapter.
        self.planner = planner or model
        self.preset = preset_for_bible(project.bible)
        self.style = style_lib
        self.profile = profile
        self.s = settings
        self.log = log
        self.progress = progress or (lambda **k: None)
        self.stream = stream or (lambda s: None)
        self.kill = kill
        self.mem = MemoryManager(
            project,
            client,
            model,
            profile,
            log,
            context_budget=settings.get("context_budget", 24000),
            safety_margin=settings.get("context_safety_margin", 1500),
            reply_tokens=settings.get("max_tokens_per_call", 4096),
            summary_temperature=settings.get("summary_temperature", 0.2),
            reserve=self._rag_tokens(),
        )
        self._retriever = None

    def _rag_tokens(self):
        if not self.s.get("rag_enabled", True):
            return 0
        return int(self.profile.get("rag_tokens", 900))

    # ==================================================================
    # sampling / low-level calls
    # ==================================================================
    def _sampling(self, prose=True, dry_boost=0.0):
        s = self.s
        if not prose:
            # structured / JSON: DRY and hard penalties break legit repeats
            # ("desc":, character names) -- keep it minimal.
            return {
                "frequency_penalty": 0.1,
                "repeat_penalty": 1.03,
                "top_p": 0.95,
                "cache_prompt": True,
            }
        extra = {
            # llama.cpp keeps the evaluated prompt and reuses the longest
            # matching prefix: the system prompt and canon block stay the same
            # for every scene of a chapter, so only the new tail is read. On
            # the iGPU a 10k-token prompt otherwise takes minutes per scene.
            "cache_prompt": True,
            "repeat_penalty": float(s.get("repeat_penalty", 1.08)),
            "repeat_last_n": int(s.get("repeat_last_n", 512)),
            "frequency_penalty": float(s.get("frequency_penalty", 0.3)),
            "presence_penalty": float(s.get("presence_penalty", 0.3)),
            "top_p": float(s.get("top_p", 0.92)),
            "min_p": float(s.get("min_p", 0.03)),
        }
        dm = float(s.get("dry_multiplier", 0.8)) + dry_boost
        if dm > 0:
            extra.update(
                {
                    "dry_multiplier": round(dm, 3),
                    "dry_base": float(s.get("dry_base", 1.75)),
                    "dry_allowed_length": int(s.get("dry_allowed_length", 2)),
                    "dry_penalty_last_n": int(s.get("dry_penalty_last_n", 1024)),
                }
            )
        return extra

    def _structured(
        self, system, user, max_tokens, temperature=None, retries=None, model=None
    ):
        model = model or self.model
        temp = (
            self.s.get("structure_temperature", 0.3)
            if temperature is None
            else temperature
        )
        retries = (
            retries if retries is not None else self.profile.get("structure_retries", 3)
        )
        last = ""
        for attempt in range(retries):
            if self.kill and self.kill.any:
                return last
            try:
                comp = self.client.complete(
                    model,
                    system,
                    user,
                    max_tokens=max_tokens,
                    temperature=temp,
                    kill=self.kill,
                    extra=self._sampling(prose=False),
                )
                last = strip_reasoning(comp.text)
            except JanError as e:
                self.log(f"  model call failed ({attempt + 1}/{retries}): {e}")
                time.sleep(1)
                continue
            if last.strip() and not is_degenerate(last, strict=True):
                return last
            if is_degenerate(last, strict=True):
                self.log(
                    f"  structured reply looped (attempt {attempt + 1}); retrying hotter."
                )
                temp = min(temp + 0.2, 1.1)
            user += "\n\n(Answer concisely and plainly now; do not repeat yourself.)"
        return last

    def _prose_call(self, system, user, max_tokens, temperature, dry_boost=0.0):
        got = []

        def on_delta(pc):
            got.append(pc)
            self.stream(pc)

        comp = self.client.complete(
            self.model,
            system,
            user,
            max_tokens=max_tokens,
            temperature=temperature,
            kill=self.kill,
            on_delta=on_delta,
            extra=self._sampling(prose=True, dry_boost=dry_boost),
        )
        return ("".join(got) or comp.text), comp

    def _loose_or_json(self, j, loose):
        return loose if self.profile.get("loose_json") else j

    # ==================================================================
    # Free-Rein -- multi-pass, prose-first, scaled by world_depth
    # ==================================================================
    def _world_seed_block(self, g, pr, pl):
        b = self.p.bible
        lines = [
            f"Seed genre: {g or '(choose one with strong long-form potential)'}",
            f"Seed protagonist: {pr or '(invent a specific, named protagonist)'}",
            f"Seed premise: {pl or '(invent a concrete premise with a real conflict)'}",
        ]
        if b.get("pinned_facts", "").strip():
            lines.append(
                "World rules the author has ALREADY fixed (build around these, "
                "never contradict, you may add):\n" + b["pinned_facts"].strip()
            )
        if b.get("inspiration_notes", "").strip():
            lines.append(
                "Author inspiration notes (honour the spirit):\n"
                + b["inspiration_notes"].strip()
            )
        if b.get("style_directives", "").strip():
            lines.append("Author directives: " + b["style_directives"].strip())
        if not codex_is_empty(self.p.codex):
            lines.append(
                "Already in the codex (extend, do not duplicate):\n"
                + format_codex(self.p.codex, max_chars=1600)
            )
        return "\n".join(lines)

    def build_world(
        self, seed_genre, seed_protagonist, seed_plot, expand_existing=False
    ):
        depth = self.s.get("world_depth", "rich")
        cfg = WORLD_DEPTH.get(depth, WORLD_DEPTH["rich"])
        scope = self.p.bible.get("story_scope", "series")
        planned = int(self.p.bible.get("planned_books", 1) or 1)
        seeds = self._world_seed_block(seed_genre, seed_protagonist, seed_plot)
        temp = self.s.get("worldbuild_temperature", 0.78)

        system = (
            "You are a master worldbuilder and character designer. Be concrete and "
            "specific: real proper names for every person and place (never role "
            "labels like 'the Teacher' or 'the Friend'), tangible detail, cause and "
            "effect. Write generously — length and richness are wanted. Do NOT write "
            "the story itself, and do not lapse into abstract mood writing."
        )
        scope_hint = (
            f"This world must sustain a {planned}-book series."
            if scope == "series" and planned > 1
            else "This world is for a single self-contained book."
        )

        self.log(f"Free-Rein ({cfg['label']}): 1/ foundation…")
        p1, _ = self._prose_call(
            system,
            f"{seeds}\n\n{scope_hint}\n\n"
            f"Write an expansive WORLDBUILDING DOCUMENT of at least {cfg['foundation_words']} "
            "words. Cover, concretely: the premise expanded into a central dramatic "
            "engine with real stakes; the setting (place names, era, technology or "
            "magic, the texture of daily life); exactly how the core system/rules "
            "work — their costs, limits and failure modes; the social, political and "
            "economic landscape and its current fault lines; tone and recurring "
            "themes; the protagonist by name, their concrete situation, and the named "
            "forces opposing them. Prose; headers welcome.",
            max_tokens=cfg["pass_tokens"],
            temperature=temp,
        )

        self.log("Free-Rein: 2/ cast dossiers…")
        p2, _ = self._prose_call(
            system,
            f"{seeds}\n\nWorld so far:\n{_trim(p1, 3500)}\n\n"
            f"Invent the CAST — {cfg['cast']} characters with real names: the "
            "protagonist, their allies and foils, at least two distinct antagonists, "
            "and several recurring minor figures. For EACH, write a real dossier of "
            "several sentences: name; role; a line of appearance; how they talk and "
            "carry themselves; background; what they want vs. what they actually "
            "need; a secret or contradiction; their key relationships (by name); "
            "where they stand as the book opens.\n\n"
            "Begin each with a line 'CHARACTER: <Name>' then prose. No JSON.",
            max_tokens=cfg["pass_tokens"],
            temperature=temp,
        )

        p3 = p4 = ""
        if cfg["passes"] >= 3:
            self.log("Free-Rein: 3/ places, factions, history, tensions…")
            p3, _ = self._prose_call(
                system,
                f"{seeds}\n\nWorld so far:\n{_trim(p1, 2600)}\n\n"
                f"Detail {cfg['locations']} named LOCATIONS (what it looks and feels "
                f"like, who holds it, why it matters to the plot) and {cfg['factions']} "
                "named FACTIONS/ORGANISATIONS (goal, methods, leadership by name, how "
                "they clash). Then a short TIMELINE of the history that made the "
                f"present, and exactly {cfg['threads']} UNRESOLVED TENSIONS or open "
                "questions, each concrete enough to drive its own plotline.\n\n"
                "Headers: 'LOCATION: <Name>', 'FACTION: <Name>', 'HISTORY', 'TENSIONS'. "
                "Prose. No JSON.",
                max_tokens=cfg["pass_tokens"],
                temperature=temp,
            )
        if cfg["passes"] >= 4:
            self.log("Free-Rein: 4/ myth, culture, deep arcs…")
            p4, _ = self._prose_call(
                system,
                f"{seeds}\n\nWorld so far:\n{_trim(p1, 2200)}\n\n"
                "Go deeper: the myths and religions people actually believe; everyday "
                "culture (food, music, rites, slang); how the core system is popularly "
                "understood versus how it truly works; older powers lurking at the "
                "edges; and three large directions the overall story could take. "
                "Prose, headers welcome. No JSON.",
                max_tokens=cfg["pass_tokens"],
                temperature=min(temp + 0.05, 1.0),
            )

        parts = [
            x
            for x in (p1, p2, p3, p4)
            if x and x.strip() and not is_degenerate(x, strict=True)
        ]
        if not parts:
            raise RuntimeError(
                "Free-Rein output looped or came back empty. Try a different model "
                "(a dense 12-14B instruct model works far better than a small MoE or "
                "an RP finetune), or fill the Story fields by hand."
            )
        world_doc = "\n\n".join(strip_scaffolding(x).strip() for x in parts)

        existing_doc = self.p.bible.get("world_doc", "").strip()
        self.p.bible["world_doc"] = (
            existing_doc + "\n\n---\n\n" + world_doc
            if existing_doc and expand_existing
            else world_doc
        )

        # ---- index the prose into the structured codex ----
        self.log("Free-Rein: indexing world into codex…")
        world = self._extract_world_structure(world_doc)
        # also parse the loose CHARACTER:/LOCATION:/FACTION: blocks directly
        merge_codex(
            self.p.codex,
            {
                "characters": world["characters"],
                "locations": world["locations"],
                "factions": world["factions"],
                "facts": world["facts"],
            },
            chapter_n=0,
        )
        loose = coerce_world(p2 + "\n\n" + p3)
        merge_codex(
            self.p.codex,
            {
                "characters": loose["characters"],
                "locations": loose["locations"],
                "factions": loose["factions"],
            },
            chapter_n=0,
        )
        self.p.save_codex()

        # ---- one-line bible fields ----
        oneliners = self._structured(
            "You extract one-line summaries. Be concrete; use the protagonist's real name.",
            f"{_trim(world_doc, 6000)}\n\nGive exactly three lines:\n"
            "GENRE: <a few words>\nPROTAGONIST: <name> — <defining trait> — <flaw>\n"
            "PLOT: <2-3 sentences: who wants what, what stands in the way, the stakes>",
            max_tokens=400,
            temperature=0.3,
        )
        got = {}
        for line in oneliners.splitlines():
            m = re.match(r"(?i)\s*(genre|protagonist|plot)\s*[:\-]\s*(.+)", line)
            if m:
                got[m.group(1).lower()] = m.group(2).strip()
        b = self.p.bible
        for key in ("genre", "protagonist", "plot"):
            if got.get(key) and (expand_existing or not b.get(key)):
                b[key] = got[key]

        # ---- pinned facts (dedup) ----
        if world["facts"]:
            merged = self._dedup_facts(
                [ln for ln in b.get("pinned_facts", "").splitlines() if ln.strip()]
                + [f"- {f}" for f in world["facts"]]
            )
            b["pinned_facts"] = "\n".join(merged)

        # ---- open threads from the world's TENSIONS ----
        trail = ""
        for chunk in (p3, p4):
            m = re.search(r"(?is)\btensions?\b[:\s]*(.+)$", chunk or "")
            if m:
                trail = m.group(1)
                break
        if trail:
            b["open_threads"] = as_text_list(trail)[: cfg["threads"]]

        self.p.save()

        # ---- series arc ----
        if scope == "series" and planned > 1 and not b.get("arc_synopsis", "").strip():
            self.build_arc(planned)

        st = codex_stats(self.p.codex)
        self.log(
            f"World ready: {len(world_doc.split())} words · {st['characters']} characters, "
            f"{st['locations']} locations, {st['factions']} factions, {st['facts']} facts."
        )
        return {"world_doc": world_doc, **world}

    def _extract_world_structure(self, world_doc):
        j = (
            'Return ONLY JSON: {"characters":{"Name":{"desc":"","traits":["",""],'
            '"relationships":{"Other":""},"status":""}},"locations":{"Name":{"desc":""}},'
            '"factions":{"Name":{"desc":""}},"facts":["hard world rule"]}. No prose.'
        )
        loose = (
            "Plain lines only:\n"
            "CHARACTER: Name | description | trait, trait\n"
            "LOCATION: Name | description\nFACTION: Name | description\n"
            "FACT: a hard world rule"
        )
        raw = self._structured(
            "You are a story-bible indexer. Extract every named entity. Be thorough, no prose.",
            f"Index this worldbuilding document.\n\n{_trim(world_doc, 9000)}\n\n"
            + self._loose_or_json(j, loose),
            max_tokens=min(
                4000, WORLD_DEPTH[self.s.get("world_depth", "rich")]["pass_tokens"]
            ),
            temperature=0.25,
        )
        return coerce_world(raw)

    @staticmethod
    def _dedup_facts(lines):
        seen, out = [], []
        for ln in lines:
            key = re.sub(r"[^a-z0-9 ]", "", ln.lower()).strip()
            key = re.sub(r"\s+", " ", key)
            if not key:
                continue
            if any(key in s or s in key for s in seen):
                continue
            seen.append(key)
            out.append(ln if ln.strip().startswith("-") else f"- {ln.strip()}")
        return out

    # ==================================================================
    # Series arc
    # ==================================================================
    def build_arc(self, planned_books):
        b = self.p.bible
        self.log(f"Planning the {planned_books}-book series arc…")
        raw = self._structured(
            "You are a series architect. Design multi-book arcs that escalate and pay off. "
            "Use the real character and place names from the material.",
            f"Genre: {b.get('genre', '')}\nPremise: {b.get('plot', '')}\n"
            f"World:\n{_trim(b.get('world_doc', ''), 5000)}\n\n"
            f"Plan a {planned_books}-book series. First, one paragraph: the question the "
            "whole series answers and the shape of its ending. Then, for EACH book, a "
            "line:\n'BOOK k: <title> — <one-paragraph arc with its own climax> — "
            "<how it moves the overarching story> — <the hook it ends on>'\n"
            f"Book {planned_books} resolves everything.",
            max_tokens=3200,
            temperature=0.5,
        )
        b["arc_synopsis"] = strip_scaffolding(strip_reasoning(raw)).strip()
        self.p.save()

        # push per-book briefs into the attached Series
        try:
            from .project import Series

            if b.get("series"):
                s = Series(b["series"])
                s.data["planned_books"] = planned_books
                s.data["arc_synopsis"] = b["arc_synopsis"]
                s.data.setdefault("world_doc", b.get("world_doc", ""))
                for m in re.finditer(
                    r"(?im)^\s*book\s+(\d+)\s*[:\-]\s*(.+)$", b["arc_synopsis"]
                ):
                    idx = int(m.group(1))
                    rest = m.group(2).strip()
                    title = rest.split("—")[0].split("-")[0].strip().strip('"')
                    while len(s.data["books"]) < idx:
                        s.data["books"].append(
                            f"{s.name}_book_{len(s.data['books']) + 1}"
                        )
                    slug = s.data["books"][idx - 1]
                    s.data["book_meta"].setdefault(slug, {})
                    s.data["book_meta"][slug].update(
                        title=title, one_line=rest, status="planned"
                    )
                s.save()
        except Exception as e:
            self.log(f"  (series file not updated: {e})")
        return b["arc_synopsis"]

    def _this_book_brief(self):
        b = self.p.bible
        k = int(b.get("book_index", 1))
        try:
            from .project import Series

            if b.get("series"):
                ol = Series(b["series"]).book_one_line(k)
                if ol:
                    return ol
        except Exception:
            pass
        m = re.search(
            rf"(?im)^\s*book\s+{k}\s*[:\-]\s*(.+)$", b.get("arc_synopsis", "")
        )
        return m.group(1).strip() if m else ""

    # ==================================================================
    # Outline -- the pipeline lives in outline.py; the scope notes stay here
    # ==================================================================
    def outline_scope_note(self, target_chapters):
        """Series / continuation context the outline must respect."""
        b = self.p.bible
        scope = b.get("story_scope", "series")
        planned = int(b.get("planned_books", 1) or 1)
        k = int(b.get("book_index", 1))
        if b.get("continuation_mode"):
            note = (
                "This outline CONTINUES an existing story; its world and cast are "
                "established, so do not restart or re-explain them."
            )
            tail = _trim(b.get("seed_tail", ""), 500)
            if tail:
                note += f"\nThe previous book ended:\n{tail}"
            spin = (b.get("spin_directive") or "").strip()
            if spin:
                note += f"\nDeliberate spin for this continuation: {spin}"
            syn = self.p.state.get("running_synopsis", "")
            if syn:
                note += "\nStory so far:\n" + _trim(syn, 900)
            return note
        if scope == "series" and planned > 1:
            brief = self._this_book_brief()
            note = f"This is BOOK {k} OF {planned} of a series."
            if b.get("arc_synopsis", "").strip():
                note += f"\nSeries arc:\n{_trim(b['arc_synopsis'], 900)}"
            if brief:
                note += f"\nThis book covers: {brief}"
            if b.get("series_context", "").strip():
                note += f"\nEarlier books:\n{_trim(b['series_context'], 600)}"
            return note
        return "This is a single self-contained book."

    def outline_final_note(self, target_chapters):
        """What the last chapter must do, by scope."""
        b = self.p.bible
        scope = b.get("story_scope", "series")
        planned = int(b.get("planned_books", 1) or 1)
        k = int(b.get("book_index", 1))
        if b.get("continuation_mode"):
            return (
                f"Chapter {target_chapters} ends on a strong hook; this is an open-ended "
                "continuation, so do not resolve the whole saga."
            )
        if scope == "oneshot" or planned <= 1:
            return f"Chapter {target_chapters} delivers a complete, definitive ending."
        if k < planned:
            return (
                f"Chapter {target_chapters} resolves this book's own conflict, lands a "
                f"beat of the series arc and ends on a hook into book {k + 1}. Do not "
                "resolve the series."
            )
        return (
            f"This is the final book: chapter {target_chapters} resolves the entire "
            "series, every major thread from every book."
        )

    def build_outline(self, target_chapters, keep_existing=False, careful=None):
        """Plan the chapters (see outline.py). Returns (outline_text, lines);
        the outline may be shorter than asked when a chapter could not be
        got right -- it is never padded with filler."""
        if careful is None:
            careful = bool(self.s.get("outline_careful", False))
        lines, complete = OutlineBuilder(self, self.preset).build(
            target_chapters, keep_existing=keep_existing, careful=careful
        )
        if complete:
            self.log(
                f"Outline ready: {len(lines)} chapters "
                f"({self.preset.get('label', 'general')} structure)."
            )
        return self.p.bible.get("outline", ""), lines

    # ==================================================================
    # Chapter writing
    # ==================================================================
    def _synthetic_beats(self, n, goal, want):
        proto = (
            protagonist_name(self.p.bible.get("protagonist", "")) or "the protagonist"
        )
        skel = [
            f"Open in a concrete place with {proto} already in motion; establish the "
            f"chapter's problem through action, not narration. ({goal})",
            f"The problem sharpens: an obstacle, a person, or new information forces "
            f"{proto} to make a choice. Show it in scene, with dialogue.",
            f"A turn — a revelation, a reversal, or a confrontation — changes what "
            f"{proto} wants or believes.",
            f"Fallout: the cost of the turn lands, relationships shift, and the "
            f"chapter ends on a concrete hook into what comes next.",
        ]
        return (skel * ((want // len(skel)) + 1))[:want]

    def _plan_scenes(self, n, goal, context):
        want = self.profile.get("plan_scenes", 4)
        role = self._chapter_role(n)
        guidance = " ".join(self.preset.get("scene_guidance") or [])
        raw = self._structured(
            "You plan scenes for a novelist. Each beat is ONE concrete line: who, "
            "where, what happens, what changes. Real names. No abstraction, no repetition. "
            + guidance,
            f"{_trim(context, 3000)}\n\nChapter {n} plan: {goal}"
            + (f"\nThis chapter's job in the book: {role}" if role else "")
            + f"\n\nBreak this chapter into {want} sequential scene beats, one per line:\n"
            f"1: <who does what, where>\n2: …\nThe last beat ends on the chapter's hook. "
            "No commentary.",
            max_tokens=700,
            temperature=self.s.get("structure_temperature", 0.3) + 0.15,
        )
        beats = parse_beats(raw, want=want)
        # repair bad beats
        synth = self._synthetic_beats(n, goal, want)
        fixed = []
        for i, bt in enumerate(beats):
            if not bt or len(bt) > 420 or is_degenerate(bt) or looks_abstract(bt * 4):
                fixed.append(synth[i % len(synth)])
            else:
                fixed.append(bt)
        if not fixed:
            fixed = synth
        self.p.state["chapter_beats"][str(n)] = fixed
        return fixed

    def _chapter_role(self, n):
        roles = self.p.bible.get("chapter_roles") or []
        return roles[n - 1] if 0 < n <= len(roles) else ""

    def _style_excerpts(self, goal):
        """Per-chapter reference excerpts; they change with the goal, so they
        go in the user message, after the cached prefix."""
        refs = self.style.retrieve(goal, top_k=2)
        if not refs:
            return ""
        return (
            "STYLE EXCERPTS (imitate rhythm only, never phrasing):\n"
            + "\n---\n".join(f"[{nm}] {ch}" for nm, ch in refs)
        )

    def _style_glue(self, goal=None):
        """Book-wide style additions for the system prompt: stable across the
        whole run, so they never break the prompt cache."""
        glue = ""
        notes = self.style.active_style_notes()
        if notes:
            glue += "\n\nHOUSE STYLE (match the technique, not the words):\n" + notes
        d = self.p.bible.get("style_directives", "").strip()
        if d:
            glue += "\n\nAUTHOR DIRECTIVES (obey exactly):\n" + d
        spin = (self.p.bible.get("spin_directive") or "").strip()
        if spin and self.p.bible.get("continuation_mode"):
            glue += (
                "\n\nCONTINUATION SPIN (hold to this the whole way through):\n" + spin
            )
        return glue

    def _names_line(self):
        names = list(self.p.codex.get("characters", {}).keys())[:24]
        proto = protagonist_name(self.p.bible.get("protagonist", ""))
        if proto and proto not in names:
            names.insert(0, proto)
        return ", ".join(names)

    def _pov_line(self):
        from .continuation import profile_line

        voice = profile_line(self.p.bible.get("narrative_profile") or {})
        return voice

    def _scene_system(self, style_glue=None):
        """The system prompt for prose: the genre's voice, the hard rules and
        the worn phrases to avoid. Built once per book, so it is identical on
        every call and stays in llama.cpp's prompt cache."""
        pr = self.preset
        names = self._names_line()
        voice = self._pov_line()
        rules = []
        if voice:
            rules.append(
                f"Write in {voice}. Hold that person and tense in every sentence "
                "of narration; never switch heads, never slip tense."
            )
        else:
            rules.append(
                "Keep one point of view and one tense per scene, as established "
                "so far; never switch heads mid-scene."
            )
        if names:
            rules.append(
                f"These are the ONLY correct character names, spelled exactly: "
                f"{names}. Never rename them or invent variants; never use role "
                "labels like 'the Teacher' instead of a name."
            )
        else:
            rules.append("Give every character a real proper name.")
        rules += [
            "Write only the story's prose: no headings, chapter numbers, labels, notes, "
            "summaries or commentary.",
            "Every scene has concrete action and, when people are together, real dialogue. "
            "Show, don't tell. No abstract meditation on time, space or the heart.",
        ]
        voice_rules = list(pr.get("voice") or []) + list(pr.get("common_voice") or [])
        cliches = all_cliches(pr)
        out = f"You are an expert novelist writing a {pr.get('label', 'novel')}, one scene " "at a time.\n\nVOICE:\n" + "\n".join(
            f"- {r}" for r in voice_rules
        ) + "\n\nHARD RULES:\n" + "\n".join(
            f"- {r}" for r in rules
        )
        if cliches:
            out += "\n\nNEVER use these worn phrases: " + "; ".join(cliches) + "."
        sample = (pr.get("sample") or "").strip()
        if sample and self.s.get("preset_sample", True):
            out += (
                "\n\nRHYTHM SAMPLE (a different story: match its rhythm and paragraphing, "
                "never its names or events):\n" + sample
            )
        return out + (self._style_glue() if style_glue is None else style_glue)

    def _final_check(self):
        """Repeated at the very end of each prose request: small models follow
        the last thing they read."""
        pr = self.preset
        top = (pr.get("voice") or [])[:2]
        names = self._names_line()
        bits = [f"FINAL CHECK: {' '.join(top)}"] if top else ["FINAL CHECK:"]
        if names:
            bits.append(f"Use only these names: {names}.")
        voice = self._pov_line()
        if voice:
            bits.append(f"Stay in {voice}.")
        bits.append("Prose only, no headings or notes.")
        return " ".join(bits)

    def _write_scene(
        self,
        n,
        idx,
        total,
        beat,
        context,
        chapter_so_far,
        style_glue,
        is_last_scene,
        ending_mode,
    ):
        target_words = max(
            450, self.p.state.get("target_words_per_chapter", 3500) // total
        )
        max_toks = self.s.get("max_tokens_per_call", 4096)
        temp = self.s.get("prose_temperature", 0.9)
        system = self._scene_system(style_glue)
        tail = strip_scaffolding(chapter_so_far)[-2200:]
        role = self._chapter_role(n)
        found = self._retrieve(n, f"{beat} {goal_of(self, n)}")
        excerpts = self._style_excerpts(beat)

        close = ""
        if is_last_scene and ending_mode == "series_finale":
            close = (
                " This is the last scene of the book AND the series: resolve every "
                "major thread and give the whole story an earned, definitive ending."
            )
        elif is_last_scene and ending_mode == "book_finale":
            close = " This is the last scene of the book: reach a complete, definitive ending."
        elif is_last_scene and ending_mode == "book_hook":
            close = (
                " This is the last scene of the book: resolve THIS book's central "
                "tension, land a beat of the larger arc, and end on a hook into the "
                "next book — but do NOT resolve the overarching series."
            )
        elif is_last_scene:
            close = " End the chapter on a concrete beat or a small hook; don't resolve the book."

        def build_user(extra_note=""):
            # Order matters for the prompt cache: the context (the same for
            # every scene of this chapter) first, everything scene-specific after.
            return (
                f"{context}\n\n"
                + (f"{found}\n\n" if found else "")
                + (f"{excerpts}\n\n" if excerpts else "")
                + f"CHAPTER {n} PLAN: {goal_of(self, n)}"
                + (f" (its job in the book: {role})" if role else "")
                + "\n"
                + f"SCENE {idx} OF {total}: {beat}\n\n"
                + (
                    f"The chapter so far — continue seamlessly from the final sentence, "
                    f"do not repeat any of it:\n<<<\n{tail}\n>>>\n\n"
                    if tail.strip()
                    else ""
                )
                + f"Write the scene now: about {target_words} words of concrete, "
                "event-driven prose with dialogue."
                + close
                + extra_note
                + "\n\n"
                + self._final_check()
            )

        text, comp = self._prose_call(system, build_user(), max_toks, temp)

        # --- degeneration guard: one hotter retry, then salvage the prefix ---
        if self.s.get("degeneration_guard", True) and is_degenerate(text):
            r = repetition_report(text)
            self.log(
                f"  scene {idx} looped (sent {r['sentence_repeat']:.2f} / "
                f"tri {r['trigram_repeat']:.2f}); retrying with stronger anti-repeat."
            )
            self.stream("\n[retrying — the model looped]\n")
            text, comp = self._prose_call(
                system,
                build_user(
                    "\n\nYour previous attempt repeated itself. Write it fresh, "
                    "varied sentence to sentence, and keep the plot moving."
                ),
                max_toks,
                min(temp + 0.12, 1.15),
                dry_boost=0.3,
            )
            if is_degenerate(text):
                text = healthy_prefix(text)
                self.log(f"  kept the {_wc(text)}-word healthy prefix of scene {idx}.")

        # --- abstract-drift guard (only if we have room to retry) ---
        if looks_abstract(text) and not (self.kill and self.kill.any):
            self.log(f"  scene {idx} drifted abstract; one grounded retry.")
            text, comp = self._prose_call(
                system,
                build_user(
                    "\n\nWrite it CONCRETELY this time: specific actions, objects, "
                    "places and dialogue. No meditation on time, space or the heart."
                ),
                max_toks,
                temp,
            )

        # --- bounded continuation to hit the word target ---
        cont, cap = 0, self.profile.get(
            "max_continues_per_scene", self.s.get("max_continues_per_scene", 3)
        )
        while (
            not (self.kill and self.kill.any)
            and comp.hit_length_cap
            and _wc(text) < target_words * 0.8
            and cont < cap
            and not is_degenerate(text[-1800:])
        ):
            cont += 1
            self.stream("\n")
            add, comp = self._prose_call(
                system,
                f"{_trim(context, 2500)}\n\nContinue this scene seamlessly. Do not repeat, "
                f"do not restart, do not add a heading. Keep events moving.\n<<<\n{text[-2000:]}\n>>>",
                max_toks,
                temp,
            )
            add = strip_scaffolding(add)
            if not add.strip() or is_degenerate(add):
                break
            text += ("" if text.endswith((" ", "\n")) else " ") + add.lstrip()

        return _clean_prose(text)

    def _retrieve(self, n, query):
        """Earlier passages and world notes for this scene (rag.py)."""
        budget = self._rag_tokens()
        if not budget:
            return ""
        try:
            if self._retriever is None or self._retriever[0] != n:
                self._retriever = (
                    n,
                    Retriever.for_chapter(
                        self.p,
                        n,
                        verbatim_from=self.mem.verbatim_from,
                        world_skip_words=self.mem.world_words_included,
                    ),
                )
            names = [nm for nm in self.p.codex.get("characters", {}) if nm in query]
            hits = self._retriever[1].search(
                query + " " + " ".join(names * 2),
                k=int(self.s.get("rag_passages", 4)),
                max_tokens=budget,
            )
        except Exception as e:  # retrieval is a help, never a reason to stop
            self.log(f"  retrieval skipped: {e}")
            return ""
        return format_block(hits)

    def write_chapter(self, n, goal, ending_mode):
        context = self.mem.build_context(n)
        self._goal = (n, goal)
        cached = self.p.state.get("chapter_beats", {}).get(str(n))
        beats = cached if cached else self._plan_scenes(n, goal, context)
        total = len(beats)
        glue = self._style_glue()
        self.log(f"Chapter {n}: {total} scenes.")

        parts = []
        for i, beat in enumerate(beats, 1):
            if self.kill and self.kill.hard:
                break
            self.progress(stage="scene", chapter=n, scene=i, scene_total=total)
            self.log(f"  scene {i}/{total}: {beat[:90]}")
            self.stream(f"\n\n· chapter {n}, scene {i}/{total} ·\n")
            try:
                prose = self._write_scene(
                    n,
                    i,
                    total,
                    beat,
                    context,
                    "\n\n".join(parts),
                    glue,
                    is_last_scene=(i == total),
                    ending_mode=ending_mode,
                )
            except JanError as e:
                self.log(f"  scene {i} failed: {e}")
                break
            if prose.strip() and not is_degenerate(prose, strict=True):
                parts.append(prose)
            elif prose.strip():
                salv = healthy_prefix(prose)
                if _wc(salv) > 120 and not is_degenerate(salv, strict=True):
                    parts.append(salv)
                    self.log(f"  scene {i}: salvaged {_wc(salv)} words.")
                else:
                    self.log(f"  scene {i}: discarded (looped).")
            if self.kill and self.kill.soft:
                break

        chapter = "\n\n".join(p for p in parts if p.strip()).strip()
        worn = count_phrases(chapter, all_cliches(self.preset))
        if worn:
            self.log(
                f"  worn phrases in chapter {n}: {sum(c for _, c in worn)} ("
                + ", ".join(f"{ph} x{c}" for ph, c in worn[:6])
                + ")"
            )
        return chapter

    # ==================================================================
    # Continuity maintenance
    # ==================================================================
    def _clean_for_analysis(self, text):
        return strip_scaffolding(strip_reasoning(text))[:9000]

    def update_codex(self, n, chapter_text):
        chapter_text = self._clean_for_analysis(chapter_text)
        j = (
            'Return ONLY JSON: {"characters":{"Name":{"desc":"","traits":[],'
            '"relationships":{"Other":""},"status":""}},"locations":{"Name":{"desc":""}},'
            '"factions":{"Name":{"desc":""}},"facts":["new established fact"]}. '
            "Omit keys with nothing new. No prose."
        )
        loose = (
            "Plain lines:\nCHARACTER: Name | new info | new traits\n"
            "LOCATION: Name | info\nFACTION: Name | info\nFACT: new fact\n"
            "Only genuinely NEW things. Nothing new -> write NONE"
        )
        user = (
            f"Codex so far:\n{format_codex(self.p.codex, max_chars=2400)}\n\n"
            f"--- Chapter {n} ---\n{chapter_text}\n\nExtract ONLY new entities or new "
            "details for existing ones.\n" + self._loose_or_json(j, loose)
        )
        try:
            raw = self._structured(
                "You are a meticulous continuity editor.",
                user,
                max_tokens=1400,
                temperature=self.s.get("summary_temperature", 0.2),
            )
            if raw.strip().upper().startswith("NONE") and not extract_json(raw):
                return
            upd = coerce_codex_update(raw)
            if any(
                upd.get(k) for k in ("characters", "locations", "factions", "facts")
            ):
                merge_codex(self.p.codex, upd, n)
                self.p.save_codex()
        except Exception as e:
            self.log(f"  codex update ch{n} skipped: {e}")

    def update_running_synopsis(self, n, chapter_text):
        chapter_text = self._clean_for_analysis(chapter_text)
        prev = self.p.state.get("running_synopsis", "")
        try:
            comp = self.client.complete(
                self.model,
                "You maintain a running 'story so far' digest for a novelist. Plain, "
                "concrete, names explicit. No repetition.",
                f"Current digest:\n{prev or '(none yet)'}\n\n--- New chapter {n} ---\n"
                f"{chapter_text}\n\nRewrite the digest to cover the whole story through "
                "this chapter in 3-5 tight paragraphs: the through-line, where each main "
                "character stands, what is still unresolved, and how this chapter ended.",
                max_tokens=900,
                temperature=0.25,
                kill=self.kill,
                extra=self._sampling(prose=False),
            )
            syn = strip_scaffolding(strip_reasoning(comp.text)).strip()
            if syn and not is_degenerate(syn, strict=True):
                self.p.state["running_synopsis"] = syn
                self.p.save()
        except Exception as e:
            self.log(f"  synopsis update ch{n} skipped: {e}")

    def update_open_threads(self, n, chapter_text):
        chapter_text = self._clean_for_analysis(chapter_text)
        cur = "\n".join(f"- {t}" for t in self.p.bible.get("open_threads", []))
        try:
            raw = self._structured(
                "You track unresolved plot threads for continuity.",
                f"Open threads before:\n{cur or '(none)'}\n\n--- Chapter {n} ---\n{chapter_text}\n\n"
                "List every plot thread / mystery / promise to the reader still OPEN after "
                "this chapter (drop resolved ones, add new ones). One per line, terse. "
                "None -> write NONE.",
                max_tokens=600,
                temperature=0.2,
            )
            if not raw.strip().upper().startswith("NONE"):
                th = [t for t in as_text_list(raw) if len(t) > 4][:20]
                if th:
                    self.p.bible["open_threads"] = th
                    self.p.save()
        except Exception as e:
            self.log(f"  open-threads update ch{n} skipped: {e}")

    def reconcile_codex(self):
        self.log("  reconciling codex for contradictions…")
        raw = self._structured(
            "You are a continuity auditor. Report corrections only.",
            f"World codex:\n{format_codex(self.p.codex, max_chars=9000)}\n\n"
            f"Story so far:\n{_trim(self.p.state.get('running_synopsis', ''), 1200)}\n\n"
            "Report only real problems, one per line:\n"
            "MERGE: WrongName -> RealName   (same person, two names)\n"
            "STATUS: Name | corrected current status\n"
            "FIX: Name | corrected description\n"
            "If everything is consistent, write OK.",
            max_tokens=800,
            temperature=0.2,
        )
        if raw.strip().upper().startswith("OK"):
            return
        ops = []
        for line in raw.splitlines():
            m = re.match(r"(?i)\s*MERGE\s*:\s*(.+?)\s*-+>\s*(.+)", line)
            if m:
                ops.append(
                    {
                        "kind": "merge",
                        "from": m.group(1).strip(),
                        "into": m.group(2).strip(),
                    }
                )
                continue
            m = re.match(r"(?i)\s*STATUS\s*:\s*(.+?)\s*\|\s*(.+)", line)
            if m:
                ops.append(
                    {
                        "kind": "status",
                        "name": m.group(1).strip(),
                        "value": m.group(2).strip(),
                    }
                )
                continue
            m = re.match(r"(?i)\s*FIX\s*:\s*(.+?)\s*\|\s*(.+)", line)
            if m:
                ops.append(
                    {
                        "kind": "fix",
                        "name": m.group(1).strip(),
                        "value": m.group(2).strip(),
                    }
                )
        changed = apply_reconcile(self.p.codex, ops)
        if changed:
            self.p.save_codex()
            for c in changed:
                self.log(f"    · {c}")

    def rebuild_codex(self):
        self.p.codex = default_codex()
        for n in range(1, self.p.chapter_count() + 1):
            if self.kill and self.kill.any:
                break
            self.log(f"Rebuilding codex from chapter {n}…")
            self.update_codex(n, self.p.load_chapter(n))
        self.p.save_codex()
        self.log("Codex rebuild complete.")

    # ==================================================================
    # Series import
    # ==================================================================
    def import_series_canon(self, prior_projects):
        chunks = []
        for bk in prior_projects:
            chunks.append(
                f"Book {bk.bible.get('book_index', '?')} — "
                f"{bk.bible.get('title', bk.name)}:\n{bk.synopsis(max_words=240)}"
            )
            merge_codex(
                self.p.codex,
                {
                    "characters": bk.codex.get("characters", {}),
                    "locations": bk.codex.get("locations", {}),
                    "factions": bk.codex.get("factions", {}),
                    "facts": bk.codex.get("facts", []),
                },
                chapter_n=0,
            )
            if bk.bible.get("world_doc") and not self.p.bible.get("world_doc"):
                self.p.bible["world_doc"] = bk.bible["world_doc"]
            if bk.bible.get("arc_synopsis") and not self.p.bible.get("arc_synopsis"):
                self.p.bible["arc_synopsis"] = bk.bible["arc_synopsis"]
        self.p.bible["series_context"] = "\n\n".join(chunks)
        self.p.save()
        self.p.save_codex()
        self.log(f"Imported canon from {len(prior_projects)} earlier book(s).")

    # ==================================================================
    # RAM guard
    # ==================================================================
    def _ram_gate(self):
        """Called before each chapter. If free system RAM is low, nudge Jan to
        drop idle models and wait briefly for it to recover. Returns True to
        proceed, False to stop the run cleanly (it resumes from this chapter)."""
        if not self.s.get("ram_guard", True):
            return True
        min_gb = float(self.s.get("min_free_ram_gb", 2.5))
        low, st = ram_is_low(min_gb)
        if not low or st.get("available_gb") is None:
            return True
        self.log(
            f"  ⚠ low RAM: {st['available_gb']:.1f} GB free (need {min_gb}). "
            "Asking Jan to free idle models…"
        )
        ok, _ = free_jan_memory(self.client.base_url, keep_model=self.model)
        limit = int(self.s.get("ram_guard_wait_s", 90))
        waited = 0
        while waited < limit:
            if self.kill and self.kill.any:
                return False
            time.sleep(5)
            waited += 5
            low, st = ram_is_low(min_gb)
            if not low:
                self.log(
                    f"  RAM recovered: {st['available_gb']:.1f} GB free — continuing."
                )
                return True
        self.log(
            f"  RAM still low ({st['available_gb']:.1f} GB) after {limit}s — stopping "
            "here. Close some apps or other loaded models, then press "
            "Start / Resume to continue from this chapter."
        )
        return False

    # ==================================================================
    # Top-level run
    # ==================================================================
    def _ending_mode(self, n, target):
        if n != target:
            return "chapter"
        if self.p.is_final_book():
            b = self.p.bible
            return (
                "series_finale"
                if b.get("story_scope") == "series"
                and int(b.get("planned_books", 1)) > 1
                else "book_finale"
            )
        return "book_hook"

    def continue_run(self, n_more, target_words):
        """Never-ending mode: write `n_more` further chapters from wherever the
        book currently stands, extending the outline as needed."""
        done = self.p.chapter_count()
        target = done + max(1, int(n_more))
        self.log(f"Continuing: chapters {done + 1}–{target}.")
        have = len(self.p.bible.get("chapter_list") or [])
        if have < target:
            self.log(f"  extending the outline to {target} chapters…")
            self.build_outline(target, keep_existing=True)
        self.run(target, target_words)

    def run(self, target_chapters, target_words):
        self.p.state["target_chapters"] = target_chapters
        self.p.state["target_words_per_chapter"] = target_words
        self.p.state["last_model"] = self.model
        self.p.save()

        chapters = self.p.bible.get("chapter_list") or []
        start_n = self.p.state.get("current_chapter", 0) + 1
        if len(chapters) < target_chapters and start_n <= target_chapters:
            self.log(
                "No outline yet — building one."
                if not chapters
                else f"The outline has {len(chapters)} chapters; planning the rest."
            )
            _, chapters = self.build_outline(target_chapters, keep_existing=True)

        start = self.p.state.get("current_chapter", 0) + 1
        stopped_early = None
        for n in range(start, target_chapters + 1):
            if self.kill and self.kill.any:
                self.log("Killed." if self.kill.hard else "Stopped.")
                break
            if not self._ram_gate():
                break
            if n - 1 >= len(chapters):
                stopped_early = (
                    f"The outline stops at chapter {len(chapters)}, so chapter {n} "
                    "has no plan. Continue the outline (or write the missing "
                    "lines on the Story tab), then Resume."
                )
                self.log(stopped_early)
                break
            goal = chapters[n - 1]
            mode = self._ending_mode(n, target_chapters)
            self.progress(stage="chapter", chapter=n, chapter_total=target_chapters)
            self.log(f"=== chapter {n}/{target_chapters} ({mode}) ===")
            t0 = time.time()
            try:
                text = self.write_chapter(n, goal, ending_mode=mode)
            except Exception as e:
                self.log(f"Chapter {n} crashed: {e}")
                stopped_early = f"Chapter {n} crashed: {e}"
                break

            hard = self.kill and self.kill.hard
            if hard and not self.kill.keep_partial:
                self.log(f"Chapter {n} discarded (kill: discard partial).")
                break

            if (not text.strip() or is_degenerate(text, strict=True)) and not hard:
                why = "empty" if not text.strip() else "looped"
                self.log(f"Chapter {n} came back {why} — one direct retry…")
                try:
                    t2, _ = self._prose_call(
                        self._scene_system(),
                        f"{self.mem.build_context(n)}\n\nWrite chapter {n} in full as concrete, "
                        f"event-driven prose with dialogue. What happens: {goal}",
                        self.s.get("max_tokens_per_call", 4096),
                        self.s.get("prose_temperature", 0.9) + 0.1,
                        dry_boost=0.3,
                    )
                    t2 = _clean_prose(t2)
                    if not is_degenerate(t2, strict=True):
                        text = t2
                    else:
                        text = healthy_prefix(t2)
                except Exception as e:
                    self.log(f"  retry failed: {e}")
            if not text.strip() or is_degenerate(text, strict=True):
                self.log(
                    f"Chapter {n} still bad. NOT saving. This model keeps collapsing — "
                    "switch to a dense 12–14B instruct model (see the README) and resume."
                )
                stopped_early = (
                    f"Chapter {n} kept coming back empty/looping even after a retry "
                    "— stopped without saving it. Try a different (usually larger/"
                    "denser) model, then Resume."
                )
                break

            self.p.save_chapter(n, text)
            self.p.state["current_chapter"] = n
            self.p.save()
            self.log(
                f"Chapter {n} saved — {_wc(text)} words in {time.time() - t0:.0f}s."
            )

            if not hard:
                if self.s.get("auto_summary", True):
                    self.mem.ensure_summary(n)
                if self.s.get("auto_running_synopsis", True):
                    self.log("  updating story-so-far synopsis…")
                    self.update_running_synopsis(n, text)
                if self.s.get("auto_codex", True):
                    self.log("  updating world codex…")
                    self.update_codex(n, text)
                if self.s.get("auto_open_threads", True) and (
                    n % 3 == 0 or n >= target_chapters - 4
                ):
                    self.update_open_threads(n, text)
                rec = int(self.s.get("reconcile_every", 12) or 0)
                if rec and n % rec == 0 and n < target_chapters:
                    self.reconcile_codex()

            self.p.compile_manuscript()
            self.progress(
                stage="chapter_done",
                chapter=n,
                chapter_total=target_chapters,
                words=self.p.total_words(),
            )
            if self.kill and self.kill.soft:
                self.log("Soft-stop — halting after this chapter.")
                break

        self.p.compile_manuscript()
        self._finalise_series_book()
        self.log(
            f"Run finished. {self.p.chapter_count()} chapters, {self.p.total_words()} words."
        )
        if stopped_early:
            raise RuntimeError(stopped_early)

    def _finalise_series_book(self):
        b = self.p.bible
        if not b.get("series"):
            return
        done = self.p.chapter_count() >= self.p.state.get("target_chapters", 0)
        try:
            from .project import Series

            s = Series(b["series"])
            s.data["book_meta"].setdefault(self.p.name, {})
            s.data["book_meta"][self.p.name]["status"] = (
                "done" if done else "in_progress"
            )
            s.data["book_meta"][self.p.name]["synopsis"] = self.p.synopsis(
                max_words=240
            )
            if self.p.name not in s.data["books"]:
                s.data["books"].append(self.p.name)
            s.save()
        except Exception:
            pass


def goal_of(engine, n):
    """The plan line of the chapter being written (set by write_chapter)."""
    g = getattr(engine, "_goal", None)
    if g and g[0] == n:
        return g[1]
    lines = engine.p.bible.get("chapter_list") or []
    return lines[n - 1] if 0 < n <= len(lines) else ""
