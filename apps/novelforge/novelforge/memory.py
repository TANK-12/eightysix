"""
Context assembly under a token budget.

Never dropped (in priority order): the scope directive, story-bible core, pinned
facts, the World Document, earlier-books canon, the World Codex, open threads,
and the running "story so far" synopsis. Only the chapter-history tail flexes:
older chapters collapse to one-paragraph summaries, and the verbatim-recent
window shrinks last.

The budget is clamped to the model's real ctx_size (from model.yml) minus the
reply allowance, so we never silently overflow a small-context model.
"""

from .codex import format_codex, codex_is_empty


def est_tokens(text):
    if not text:
        return 0
    return max(len(text) // 4, len(text.split()))


def _trim(text, max_tokens):
    if est_tokens(text) <= max_tokens:
        return text
    words = text.split()
    keep = int(max_tokens * 0.85)
    return " ".join(words[:keep]) + " …(trimmed for this prompt only)"


class MemoryManager:
    def __init__(
        self,
        project,
        client,
        model,
        profile,
        log,
        context_budget=24000,
        safety_margin=1500,
        reply_tokens=4096,
        summary_temperature=0.2,
        reserve=0,
    ):
        self.p = project
        self.client = client
        self.model = model
        self.profile = profile
        self.log = log
        self.reply_tokens = reply_tokens
        self.summary_temp = summary_temperature
        ctx = profile.get("ctx_size", 8192)
        # `reserve` keeps room for what is added after this context: the
        # retrieved passages for each scene.
        hard_cap = max(1200, ctx - reply_tokens - safety_margin - reserve)
        self.budget = min(context_budget, hard_cap)
        if self.budget < context_budget:
            self.log(
                f"Context budget clamped to {self.budget} tokens "
                f"(model ctx {ctx} − reply {reply_tokens} − margin {safety_margin}"
                + (f" − retrieval {reserve}" if reserve else "")
                + ")."
            )
        # Set by build_context, read by the retriever so it never repeats
        # what the prompt already carries word for word.
        self.verbatim_from = None
        self.world_words_included = 0

    # ---------------- chapter summaries ----------------
    def summarize_chapter(self, n, text):
        system = "You are a precise, spoiler-free continuity tracker for a novel."
        user = (
            "Summarise this chapter for the story record in 4-6 sentences. "
            "Name characters explicitly. State plot events, relationship "
            "shifts, new information, and where/when the chapter ends. "
            "This summary is the ONLY verbatim-free memory of this chapter kept "
            "later.\n\n" + text
        )
        try:
            return self.client.complete(
                self.model, system, user, max_tokens=520, temperature=self.summary_temp
            ).text.strip()
        except Exception as e:
            return f"[summary unavailable: {e}]"

    def ensure_summary(self, n):
        key = str(n)
        cache = self.p.state["chapter_summaries"]
        if key not in cache or not cache[key]:
            text = self.p.load_chapter(n)
            if text.strip():
                cache[key] = self.summarize_chapter(n, text)
                self.p.save()
        return cache.get(key, "")

    # ---------------- continuation directive ----------------
    def continuation_directive(self):
        """Prepended to the canon block when this project continues existing books."""
        b = self.p.bible
        if not b.get("continuation_mode"):
            return ""
        src = ", ".join(b.get("source_books", []) or []) or "the source books"
        lines = [
            f"CONTINUATION: This is an ongoing continuation of an existing story "
            f"({src}). Its world, cast, history and voice are already ESTABLISHED — "
            "never reintroduce or re-explain them as if new to the reader, and never "
            "contradict them. Write as the next instalment, picking up the saga.",
        ]
        # POV and tense drifting is the single most common way a continuation
        # stops reading like the same author, so it is stated as a hard rule
        # rather than left to "the POV established so far".
        from .continuation import profile_line

        line = profile_line(b.get("narrative_profile") or {})
        if line:
            lines.append(
                f"NARRATIVE VOICE (ABSOLUTE — measured from the author's own prose): "
                f"{line}. Every sentence of narration must stay in this person and "
                "this tense. Do not switch to another character's head, do not slip "
                "into present tense, do not add a framing narrator."
            )
        roster = [n for n in (b.get("canon_names") or []) if n][:40]
        if roster:
            lines.append(
                "CANONICAL SPELLINGS (use these exactly; never rename, never invent "
                "a variant, never introduce a new name for an existing character):\n  "
                + ", ".join(roster)
            )
        places = [n for n in (b.get("canon_places") or []) if n][:30]
        if places:
            lines.append("CANONICAL PLACES: " + ", ".join(places))
        spin = (b.get("spin_directive") or "").strip()
        if spin:
            lines.append("SPIN (deliberate variation for this continuation): " + spin)
        tail = (b.get("seed_tail") or "").strip()
        if tail:
            lines.append(
                "HOW THE PREVIOUS BOOK ENDED (continue naturally from this — "
                "do not retell it):\n" + _trim(tail, 700)
            )
        return "\n".join(lines)

    # ---------------- scope directive ----------------
    def scope_directive(self, upcoming_n):
        b = self.p.bible
        total = self.p.state.get("target_chapters", 30)
        scope = b.get("story_scope", "series")
        planned = int(b.get("planned_books", 1) or 1)
        if b.get("continuation_mode"):
            return (
                "SCOPE: An open-ended continuation. Each chapter must move the "
                "story concretely and end on a beat or hook. Do NOT wrap up the "
                "whole saga — leave room for it to keep going."
            )
        if scope == "oneshot" or planned <= 1:
            return (
                "SCOPE: This is a SELF-CONTAINED story. Every major thread must be "
                f"resolved by chapter {total}; the ending is definitive."
            )
        k = int(b.get("book_index", 1))
        lines = [f"SCOPE: This is BOOK {k} OF {planned} of a series."]
        if b.get("arc_synopsis", "").strip():
            lines.append(
                "OVERARCHING SERIES ARC:\n" + _trim(b["arc_synopsis"].strip(), 700)
            )
        if k >= planned:
            lines.append(
                f"This is the FINALE. Chapter {total} must resolve the ENTIRE "
                "series — every thread from every book — with an earned ending."
            )
        else:
            climax = max(2, int(total * 0.8))
            lines.append(
                f"This book tells a COMPLETE arc of its own: build to this book's climax "
                f"around chapter {climax}, resolve this book's central tension by chapter "
                f"{total - 1}, then in chapter {total} land a beat of the overarching arc "
                f"and end on a strong hook into book {k + 1}. Do NOT resolve the "
                "overarching series in this book."
            )
        return "\n".join(lines)

    # ---------------- the big assembly ----------------
    def _canon_block(self, upcoming_n):
        b = self.p.bible
        parts = []
        cont = self.continuation_directive()
        if cont:
            parts += [cont, ""]
        parts += [self.scope_directive(upcoming_n), ""]
        parts += [
            "STORY BIBLE (canon — never contradict):",
            f"  Title: {b.get('title', '')}",
            f"  Genre: {b.get('genre', '')}",
            f"  Protagonist: {b.get('protagonist', '')}",
            f"  Core plot / conflict: {b.get('plot', '')}",
        ]
        if b.get("pinned_facts", "").strip():
            parts.append("  Pinned facts (absolute):")
            parts += [
                f"    {ln}" for ln in b["pinned_facts"].splitlines() if ln.strip()
            ]

        if b.get("world_doc", "").strip():
            # The opening of the world document goes in every prompt; the
            # rest is searched per scene (rag.py), so a long document is no
            # longer mostly invisible. Bigger context, bigger opening.
            world_tokens = max(1200, min(6000, self.budget // 6))
            shown = _trim(b["world_doc"].strip(), world_tokens)
            self.world_words_included = (
                len(shown.split()) - 5
                if shown.endswith("(trimmed for this prompt only)")
                else len(b["world_doc"].split())
            )
            parts.append(
                "\nWORLD DOCUMENT (the setting, systems, cast and history — "
                "stay consistent with this):"
            )
            parts.append(shown)

        if b.get("series_context", "").strip():
            parts.append("\nEARLIER BOOKS IN THIS SERIES (canon):")
            parts.append(
                _trim("  " + b["series_context"].strip().replace("\n", "\n  "), 900)
            )

        if not codex_is_empty(self.p.codex):
            parts.append(
                "\nWORLD CODEX (entities established so far — keep every one "
                "consistent; OFFSCREEN characters still exist):"
            )
            parts.append(
                format_codex(self.p.codex, max_chars=5500, current_chapter=upcoming_n)
            )

        threads = [t for t in b.get("open_threads", []) if str(t).strip()]
        if threads:
            near_end = upcoming_n >= self.p.state.get("target_chapters", 30) - 4
            parts.append(
                "\nOPEN PLOT THREADS (keep advancing or paying these off"
                + (
                    "; the closing chapters MUST resolve all of them):"
                    if near_end
                    else "):"
                )
            )
            parts += [f"  - {t}" for t in threads]

        if b.get("inspiration_notes", "").strip():
            parts.append("\nINSPIRATION NOTES (loose flavour, not binding):")
            parts.append(
                _trim("  " + b["inspiration_notes"].strip().replace("\n", "\n  "), 500)
            )

        syn = self.p.state.get("running_synopsis", "").strip()
        if syn:
            parts.append(
                "\nSTORY SO FAR (the running digest of everything up to now — "
                "this is your primary memory of the plot):"
            )
            parts.append(_trim(syn, 1400))
        return "\n".join(parts)

    def build_context(self, upcoming_n):
        canon = self._canon_block(upcoming_n)
        recent_keep = max(1, int(self.p.state.get("recent_full_chapters", 2)))

        def assemble(keep):
            recent_start = max(1, upcoming_n - keep)
            summaries = []
            for n in range(1, recent_start):
                s = self.ensure_summary(n)
                if s:
                    summaries.append(f"  Ch{n}: {s}")
            fulls = []
            for n in range(recent_start, upcoming_n):
                t = self.p.load_chapter(n).strip()
                if t:
                    fulls.append(f"--- Chapter {n} (verbatim) ---\n{t}")
            return summaries, fulls

        summaries, fulls = assemble(recent_keep)
        while (
            est_tokens(canon + "\n".join(summaries) + "\n\n".join(fulls)) > self.budget
            and recent_keep > 1
        ):
            recent_keep -= 1
            summaries, fulls = assemble(recent_keep)

        # Still over budget with a single verbatim chapter? Drop oldest summaries
        # (the running synopsis already covers them).
        while (
            est_tokens(canon + "\n".join(summaries) + "\n\n".join(fulls)) > self.budget
            and len(summaries) > 2
        ):
            summaries.pop(0)

        # Last resort: trim the one verbatim chapter.
        if (
            fulls
            and est_tokens(canon + "\n".join(summaries) + "\n\n".join(fulls))
            > self.budget
        ):
            fulls[-1] = _trim(fulls[-1], max(800, self.budget // 3))

        self.verbatim_from = max(1, upcoming_n - recent_keep) if fulls else upcoming_n
        out = [canon]
        if summaries:
            out.append(
                "\nEARLIER CHAPTERS (condensed — retain every fact):\n"
                + "\n".join(summaries)
            )
        if fulls:
            out.append("\n" + "\n\n".join(fulls))
        return "\n".join(out)
