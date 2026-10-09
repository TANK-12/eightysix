"""
Style & Reference library, learned from the user's own PDFs.

Two very different things are produced per source and kept apart on purpose:

  * Style Guide   -- HOW the book is written (rhythm, tone, POV, dialogue).
                     Auto-folded into every chapter prompt.
  * Content Summary -- WHAT the book is about (plot, cast, world).
                     Kept only as the user's reference. NEVER auto-injected,
                     so the new novel doesn't end up echoing the source's plot.

Also does lightweight keyword retrieval to surface a couple of on-topic style
excerpts per chapter (pattern only -- the prompt tells the model never to copy
phrasing).

Shared across all projects (one library per machine).
"""

import os
import re
import json

from .config import STYLE_LIB_PATH

try:
    from pypdf import PdfReader
    PDF_OK = True
except Exception:
    try:
        from PyPDF2 import PdfReader
        PDF_OK = True
    except Exception:
        PDF_OK = False


class StyleLibrary:
    def __init__(self, path=STYLE_LIB_PATH):
        self.path = path
        self.data = {"sources": {}}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                self.data.setdefault("sources", {})
            except Exception:
                self.data = {"sources": {}}

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------------- ingestion ----------------
    @staticmethod
    def extract_pdf_text(path):
        if not PDF_OK:
            raise RuntimeError("PDF reading needs pypdf. Run:  pip install pypdf")
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts)

    @staticmethod
    def _chunk(text, words=650):
        w = text.split()
        chunks = []
        for i in range(0, len(w), words):
            c = " ".join(w[i:i + words]).strip()
            if len(c) > 220:
                chunks.append(c)
        return chunks

    def add_source(self, name, text, max_chunks=80):
        chunks = self._chunk(text)
        if len(chunks) > max_chunks:                     # even sampling across the book
            step = len(chunks) / max_chunks
            chunks = [chunks[int(i * step)] for i in range(max_chunks)]
        self.data["sources"][name] = {
            "chunks": chunks, "style_notes": "", "content_summary": "",
            "enabled": True, "word_count": len(text.split()),
        }
        self.save()
        return len(chunks)

    def remove_source(self, name):
        self.data["sources"].pop(name, None)
        self.save()

    def set_enabled(self, name, enabled):
        if name in self.data["sources"]:
            self.data["sources"][name]["enabled"] = bool(enabled)
            self.save()

    def names(self):
        return list(self.data["sources"].keys())

    def get(self, name):
        return self.data["sources"].get(name, {})

    # ---------------- analysis (uses the model) ----------------
    def analyze_style(self, client, model, name, sample=5, temperature=0.3):
        src = self.data["sources"].get(name)
        if not src or not src["chunks"]:
            return ""
        joined = "\n\n---\n\n".join(src["chunks"][:sample])
        system = ("You are a literary style analyst. Describe patterns abstractly. "
                  "Never quote more than three consecutive words from the text.")
        user = ("From these excerpts, write a STYLE GUIDE as tight bullet points "
                "(<220 words) covering: sentence rhythm and length, narration "
                "distance and POV, tense, dialogue habits and beat style, humour, "
                "pacing, paragraphing, and recurring devices. Patterns only.\n\n" + joined)
        notes = client.complete(model, system, user, max_tokens=700,
                                temperature=temperature).text
        src["style_notes"] = notes
        self.save()
        return notes

    def summarize_content(self, client, model, name, sample=10, temperature=0.3):
        src = self.data["sources"].get(name)
        if not src or not src["chunks"]:
            return ""
        joined = "\n\n---\n\n".join(src["chunks"][:sample])
        system = ("You are a literary analyst. Summarise in your own words only; "
                  "never reproduce sentences from the text.")
        user = ("Write a SUMMARY (<300 words) of the apparent plot, setting, tone "
                "and main characters of this book, purely as reference for a "
                "writer seeking inspiration. Your own words only.\n\n" + joined)
        notes = client.complete(model, system, user, max_tokens=700,
                                temperature=temperature).text
        src["content_summary"] = notes
        self.save()
        return notes

    # ---------------- retrieval / prompt glue ----------------
    def active_style_notes(self):
        out = []
        for name, src in self.data["sources"].items():
            if src.get("enabled", True) and src.get("style_notes"):
                out.append(f"[{name}]\n{src['style_notes']}")
        return "\n\n".join(out)

    def retrieve(self, query, top_k=2, max_len=480):
        q = set(re.findall(r"[a-zA-Z']{4,}", query.lower()))
        if not q:
            return []
        scored = []
        for name, src in self.data["sources"].items():
            if not src.get("enabled", True):
                continue
            for chunk in src["chunks"]:
                c = set(re.findall(r"[a-zA-Z']{4,}", chunk.lower()))
                overlap = len(q & c)
                if overlap >= 2:
                    scored.append((overlap, name, chunk))
        scored.sort(key=lambda x: -x[0])
        return [(name, chunk[:max_len]) for _, name, chunk in scored[:top_k]]
