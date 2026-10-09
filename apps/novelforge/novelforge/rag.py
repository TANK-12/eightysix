"""Retrieval ("RAG") for NovelForge: before each scene, find the earlier
passages and world notes that scene needs, so chapter 30 can stay consistent
with a detail from chapter 3 without the whole book in the prompt.

Pure Python BM25, a keyword-ranking formula: a passage scores higher the more
of the query's words it contains, rare words count for more than common ones,
and long passages are not favoured just for being long. No model call, no
download, no vectors, so it costs nothing and never takes one of Jan's model
slots (an embedding model would, and could push the 27B out of memory).

What gets indexed for chapter N:
* earlier chapters, cut into ~200-word passages, except the chapters already
  in the prompt word for word;
* the world document, cut at its headings and paragraphs, except the opening
  part that the prompt already carries.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[a-z0-9]+(?:['\-][a-z0-9]+)*")
STOPWORDS = frozenset(
    "a an the and or but of to in on at by for with from into onto over under "
    "his her their its he she they him them it is are was were be been being "
    "as that this these those who whom what when where while then than so "
    "not no yet all any some one up down out off about after before again "
    "has have had do does did can could will would should may might must "
    "i you we me my your our us there here just very too also only said".split()
)
HEADING_RE = re.compile(
    r"^\s*(#{1,6}\s+\S.*|[A-Z][A-Z /&'\-]{2,40}:.*|[A-Z][A-Z /&'\-]{3,40})\s*$"
)


def tokenize(text: str) -> list[str]:
    out = []
    for t in TOKEN_RE.findall((text or "").lower()):
        if t.endswith("'s"):
            t = t[:-2]
        if len(t) > 1 and t not in STOPWORDS:
            out.append(t)
    return out


def chunk_words(text: str, size: int = 200, overlap: int = 40) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    step = max(1, size - overlap)
    chunks = []
    for start in range(0, len(words), step):
        piece = words[start : start + size]
        if len(piece) < 25 and chunks:
            break  # a tiny tail is already inside the previous chunk's overlap
        chunks.append(" ".join(piece))
        if start + size >= len(words):
            break
    return chunks


def world_sections(doc: str, size: int = 200) -> list[str]:
    """The world document cut where its author cut it: at headings
    ('## Magic', 'LOCATION: Ashford', 'HISTORY'), then long sections into
    ~size-word pieces. Each piece keeps its heading so it reads on its own."""
    sections: list[tuple[str, list[str]]] = []
    heading, body = "", []
    for line in (doc or "").splitlines():
        if HEADING_RE.match(line) and len(line.split()) <= 12:
            if body:
                sections.append((heading, body))
            heading, body = line.strip().lstrip("#").strip(), []
            if ":" in heading and heading.split(":", 1)[1].strip():
                body.append(heading)
        elif line.strip():
            body.append(line.strip())
    if body:
        sections.append((heading, body))
    out = []
    for heading, lines in sections:
        text = " ".join(lines)
        for piece in chunk_words(text, size=size, overlap=30):
            out.append(
                f"{heading}: {piece}"
                if heading and not piece.startswith(heading)
                else piece
            )
    return out


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.lengths = [len(d) for d in self.docs]
        self.avg = (sum(self.lengths) / len(self.lengths)) if self.docs else 0.0
        self.tf: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for toks in self.docs:
            counts: dict[str, int] = {}
            for t in toks:
                counts[t] = counts.get(t, 0) + 1
            self.tf.append(counts)
            for t in counts:
                df[t] = df.get(t, 0) + 1
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for i, counts in enumerate(self.tf):
            s = 0.0
            norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / (self.avg or 1))
            for t in q:
                f = counts.get(t)
                if f:
                    s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (f + norm)
            out.append(s)
        return out

    def top(self, query: str, k: int) -> list[tuple[int, float]]:
        ranked = sorted(enumerate(self.scores(query)), key=lambda x: -x[1])
        return [(i, s) for i, s in ranked[:k] if s > 0]


def _probe(section: str) -> str:
    """The first words of a section's body (its 'Heading: ' prefix dropped),
    to tell whether the prompt already carries that section."""
    body = section.split(": ", 1)[1] if ": " in section[:60] else section
    return " ".join(body.split()[:12])


@dataclass
class Passage:
    label: str
    text: str


class Retriever:
    def __init__(self, passages: list[Passage]):
        self.passages = passages
        self.index = BM25([p.text for p in passages])

    @classmethod
    def for_chapter(
        cls,
        project,
        upcoming_n: int,
        verbatim_from: int | None = None,
        world_skip_words: int = 0,
        size: int = 200,
    ) -> "Retriever":
        """Passages for writing chapter `upcoming_n`: chapters before
        `verbatim_from` (those from it on are already in the prompt whole) and
        the world document past its first `world_skip_words` words."""
        stop = upcoming_n if verbatim_from is None else min(verbatim_from, upcoming_n)
        passages = []
        for n in range(1, stop):
            for piece in chunk_words(project.load_chapter(n), size=size):
                passages.append(Passage(f"Chapter {n}", piece))
        doc = project.bible.get("world_doc", "") or ""
        sections = world_sections(doc, size=size)
        if world_skip_words:
            included = " ".join(doc.split()[:world_skip_words])
            sections = [s for s in sections if _probe(s) not in included]
        for piece in sections:
            passages.append(Passage("World notes", piece))
        return cls(passages)

    def search(self, query: str, k: int = 4, max_tokens: int = 900) -> list[Passage]:
        picked, used = [], 0
        for i, _score in self.index.top(query, k * 2):
            p = self.passages[i]
            cost = max(len(p.text) // 4, len(p.text.split()))
            if used + cost > max_tokens:
                continue
            picked.append(p)
            used += cost
            if len(picked) >= k:
                break
        return picked


def format_block(passages: list[Passage]) -> str:
    if not passages:
        return ""
    body = "\n".join(f"[{p.label}] {p.text}" for p in passages)
    return (
        "RELEVANT EARLIER MATERIAL (found for this scene; stay consistent with it, "
        "do not copy it):\n" + body
    )
