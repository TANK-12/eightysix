"""
Cheap, dependency-free detectors for the two ways local models fail at prose:

  * degeneration  -- the model falls into a loop, repeating sentences or phrases
    (the classic small-model collapse). Caught by sentence-repeat ratio,
    trigram-repeat ratio, and gzip compression ratio.
  * scaffolding leak -- the model starts echoing the prompt's own structural
    markers back into the "prose": chapter/scene headers, "Scene goal:",
    "The chapter so far (continue seamlessly...)", bare triple-quote fences.

Both were silently saved to disk by earlier versions. Now they abort / trim.
"""

import re
import zlib

# Lines / fragments that are ours, not the story's. If the model emits these it
# has started parroting the prompt -- everything from the first hit is garbage.
_SCAFFOLD_PATTERNS = [
    r"^\s*=+\s*chapter\b.*?=+\s*$",
    r"^\s*=+\s*scene\b.*?=+\s*$",
    r"^\s*\[\s*chapter\s+\d+\b.*?\]\s*$",
    r"^\s*chapter\s+\d+\s+cont(?:inued|ued|d)?\b",
    r"^\s*scene\s+goal\s*:",
    r"^\s*chapter\s+\d+\s+goal\s*:",
    r"the chapter so far \(continue",
    r"continue this scene of chapter",
    r"^\s*write this scene now\b",
    r"^\s*\"{3}\s*$",
    r"^\s*'{3}\s*$",
    r"aim for about \d+ words",
    r"the chapter so far\W+continue",
    r"^\s*relevant earlier material\b",
    r"^\s*final check\s*:",
    r"^\s*chapter\s+\d+\s+plan\s*:",
    r"^\s*scene\s+\d+\s+of\s+\d+\s*:",
]
_SCAFFOLD_RE = re.compile(
    "|".join(f"(?:{p})" for p in _SCAFFOLD_PATTERNS), re.IGNORECASE | re.MULTILINE
)


def strip_scaffolding(text):
    """Cut the text at the first prompt-marker it parrots, then remove any
    stray marker lines before that point."""
    if not text:
        return ""
    m = _SCAFFOLD_RE.search(text)
    if m:
        text = text[: m.start()]
    # belt & braces: drop any remaining marker-ish lines
    kept = [ln for ln in text.splitlines() if not _SCAFFOLD_RE.match(ln.strip())]
    return "\n".join(kept).strip()


def _sentences(text):
    return [
        re.sub(r"\W+", " ", s).strip().lower()
        for s in re.split(r"(?<=[.!?])\s+", text)
        if len(s.strip()) > 15
    ]


def repetition_report(text):
    """Return a dict of the three repetition signals (0..1, higher = worse)."""
    out = {"sentence_repeat": 0.0, "trigram_repeat": 0.0, "compressibility": 0.0}
    if not text or len(text) < 200:
        return out

    sents = _sentences(text)
    if len(sents) >= 6:
        out["sentence_repeat"] = 1 - len(set(sents)) / len(sents)

    words = re.findall(r"[a-z']+", text.lower())
    if len(words) > 80:
        tris = [tuple(words[i : i + 3]) for i in range(len(words) - 2)]
        out["trigram_repeat"] = 1 - len(set(tris)) / len(tris)

    if len(text) > 500:
        raw = text.encode("utf-8", "ignore")
        out["compressibility"] = 1 - (len(zlib.compress(raw, 6)) / len(raw))

    return out


def is_degenerate(text, strict=False):
    """True when the text has collapsed into repetition.

    `strict=True` (used before *saving* a whole chapter) tolerates less;
    the looser default is for per-scene checks where some echo is survivable.
    """
    r = repetition_report(text)
    if strict:
        return (
            r["sentence_repeat"] > 0.34
            or r["trigram_repeat"] > 0.50
            or r["compressibility"] > 0.72
        )
    return (
        r["sentence_repeat"] > 0.45
        or r["trigram_repeat"] > 0.62
        or r["compressibility"] > 0.80
    )


def healthy_prefix(text, window_sentences=4):
    """When a passage degenerates partway through, return the good opening part
    by scanning a sliding window and cutting where repetition spikes."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    if len(parts) <= window_sentences:
        return text
    for i in range(window_sentences, len(parts)):
        window = " ".join(parts[i - window_sentences : i + 1])
        r = repetition_report(window * 3)  # amplify so short windows register
        if r["sentence_repeat"] > 0.5 or r["trigram_repeat"] > 0.6:
            return " ".join(parts[: i - window_sentences + 1]).strip()
    return text


def looks_abstract(text):
    """Heuristic for the 'prose-poem with no events' failure: lots of abstract
    nouns, no dialogue, few concrete verbs."""
    if not text or len(text) < 400:
        return False
    low = text.lower()
    words = low.split()
    abstract = sum(
        low.count(w)
        for w in (
            "heart",
            "space",
            "stillness",
            "quiet",
            "silence",
            "belongs",
            "matters",
            "held",
            "meaning",
            "presence",
            "absence",
            "moment",
            "something",
        )
    )
    has_dialogue = (
        '"' in text or "“" in text or "‘" in text or re.search(r"\n\s*[-—]\s*\w", text)
    )
    return (abstract / max(len(words), 1) > 0.045) and not has_dialogue


def count_phrases(text, phrases):
    """How often each worn phrase appears (case-insensitive), most first.
    Only phrases that occur are returned: [(phrase, count), ...]."""
    low = (text or "").lower()
    hits = []
    for ph in phrases or []:
        key = (ph or "").lower().strip()
        if key:
            n = low.count(key)
            if n:
                hits.append((ph, n))
    return sorted(hits, key=lambda x: -x[1])
