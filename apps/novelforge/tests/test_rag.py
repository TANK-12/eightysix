"""Keyword retrieval over earlier chapters and the world document."""

from __future__ import annotations

from novelforge import rag
from novelforge.project import Project


def test_tokenize_keeps_names_and_drops_filler():
    assert rag.tokenize("Jin-Woo's sword and THE gate") == ["jin-woo", "sword", "gate"]


def test_chunks_overlap_and_cover_the_text():
    words = [f"w{i}" for i in range(450)]
    chunks = rag.chunk_words(" ".join(words), size=200, overlap=40)
    assert len(chunks) == 3
    assert chunks[0].split()[-40:] == chunks[1].split()[:40]
    assert chunks[-1].split()[-1] == "w449"
    assert rag.chunk_words("") == []


def test_world_sections_split_at_headings():
    doc = "## Magic\nMana costs blood.\n\nLOCATION: Ashford\nA river town.\n\nHISTORY\nThe war ended."
    secs = rag.world_sections(doc)
    assert secs[0].startswith("Magic: Mana costs blood")
    assert any("Ashford" in s and "river town" in s for s in secs)
    assert any(s.startswith("HISTORY: The war ended") for s in secs)


def test_bm25_ranks_the_passage_about_the_query_first():
    docs = [
        "Soo-Ah bandaged the wound in the clinic while rain hit the window.",
        "The red key opened the vault under Seoul Station; Jin-Woo kept it.",
        "Breakfast was rice and soup; nobody talked about the gate.",
    ]
    bm = rag.BM25(docs)
    assert bm.top("where is the red key vault", 3)[0][0] == 1
    assert bm.top("nothing matches zzz", 3) == []


def test_retriever_skips_what_the_prompt_already_has(data_dirs):
    p = Project("R")
    p.save_chapter(1, "The red key was hidden in the ferry locker by Jin-Woo. " * 5)
    p.save_chapter(2, "Soo-Ah healed the guild master with blue light. " * 5)
    p.save_chapter(3, "The red key again, in chapter three, verbatim. " * 5)
    p.bible["world_doc"] = (
        "OPENING shown in the prompt.\n\n## Keys\nThe red key opens gates of rank S."
    )
    r = rag.Retriever.for_chapter(p, 4, verbatim_from=3, world_skip_words=5)
    labels = {x.label for x in r.passages}
    assert labels == {"Chapter 1", "Chapter 2", "World notes"}
    assert not any("OPENING" in x.text for x in r.passages)
    hits = r.search("red key", k=2, max_tokens=900)
    assert hits and hits[0].label in ("Chapter 1", "World notes")
    assert all("chapter three" not in h.text for h in hits)
    block = rag.format_block(hits)
    assert block.startswith("RELEVANT EARLIER MATERIAL")
    assert rag.format_block([]) == ""


def test_search_respects_the_token_budget(data_dirs):
    p = Project("B")
    p.save_chapter(1, " ".join(["gate"] * 600))
    r = rag.Retriever.for_chapter(p, 2)
    assert (
        r.search("gate", k=4, max_tokens=250)
        and len(r.search("gate", k=4, max_tokens=250)) == 1
    )
    assert r.search("gate", k=4, max_tokens=10) == []
