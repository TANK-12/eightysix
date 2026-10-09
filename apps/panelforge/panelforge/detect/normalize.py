"""Comic lettering to readable text for speech.

Comics letter everything in capitals, and serif comic fonts often glue short
words together in OCR output ("ISHOULD", "ABLETO"). normalize():

1. fixes common OCR confusions in capital lettering,
2. splits glued words when every piece is a dictionary word,
3. converts to sentence case: lower case for dictionary words, capitalised
   for "I", sentence starts and words the dictionary only knows capitalised
   or does not know at all (names such as Novus or Accretia).

The dictionary is tesseract's own English word list, extracted once with the
tesseract tools into ~/PanelForgeData/cache/detect/; the system cracklib list
is the fallback, and with neither the text is only re-cased.
"""

import functools
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import paths

_WORD = re.compile(r"[A-Za-z][A-Za-z']*")


def _cache_file() -> Path:
    return paths.DATA_ROOT / "cache" / "detect" / "eng-words.txt"


def _extract_tesseract_words(dest: Path) -> bool:
    data = Path("/usr/share/tessdata/eng.traineddata")
    if not (
        data.exists()
        and shutil.which("combine_tessdata")
        and shutil.which("dawg2wordlist")
    ):
        return False
    with tempfile.TemporaryDirectory(prefix="pf-dict-") as d:
        pre = str(Path(d) / "eng.")
        subprocess.run(
            ["combine_tessdata", "-u", str(data), pre], capture_output=True, timeout=120
        )
        out = Path(d) / "words.txt"
        subprocess.run(
            [
                "dawg2wordlist",
                pre + "lstm-unicharset",
                pre + "lstm-word-dawg",
                str(out),
            ],
            capture_output=True,
            timeout=120,
        )
        if not out.exists() or out.stat().st_size == 0:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, dest)
    return True


@functools.lru_cache(maxsize=1)
def dictionary() -> tuple[frozenset[str], frozenset[str]]:
    """(lower-case words, words the list only has capitalised) ."""
    f = _cache_file()
    if not f.exists():
        try:
            _extract_tesseract_words(f)
        except (OSError, subprocess.SubprocessError):
            pass
    src = f if f.exists() else Path("/usr/share/dict/cracklib-small")
    lower: set[str] = set()
    caps: set[str] = set()
    if src.exists():
        for w in src.read_text(errors="ignore").split():
            if not w.isalpha() and "'" not in w:
                continue
            if w.islower():
                lower.add(w)
            elif w[0].isupper() and w[1:].islower():
                caps.add(w.lower())
    caps -= lower
    return frozenset(lower), frozenset(caps)


# Words this series taught us: names and coined words the dictionary lacks
# ("BELLATO", "CORITE"), learned from the other chapters' reads and the cast
# list. A word in here is never split into "bella to".
GLOSSARY: set[str] = set()
GLOSSARY_MIN_SEEN = 2


def learn_glossary(chapter_dir: Path | str) -> set[str]:
    """Fill GLOSSARY from the series around `chapter_dir`: every unknown
    word of four or more letters read in two or more bubbles of the other
    chapters, plus the cast names. Returns the words learned."""
    import json
    from collections import Counter

    chapter_dir = Path(chapter_dir)
    series_dir = chapter_dir.parent.parent
    lower, caps = dictionary()
    seen: Counter[str] = Counter()
    for other in sorted(series_dir.glob("chapters/*/bubbles.json")):
        if other.parent == chapter_dir:
            continue
        try:
            doc = json.loads(other.read_text())
        except (OSError, ValueError):
            continue
        for b in doc.get("bubbles", []):
            for w in set(_WORD.findall(b.get("text_raw") or "")):
                w = w.lower()
                if len(w) >= 4 and w not in lower and w not in caps:
                    seen[w] += 1
    words = {w for w, n in seen.items() if n >= GLOSSARY_MIN_SEEN}
    cast = series_dir / "cast.json"
    if cast.exists():
        try:
            doc = json.loads(cast.read_text())
            for c in doc.get("cast", []) + doc.get("extras", []):
                for w in _WORD.findall(c.get("name") or ""):
                    if len(w) >= 3:
                        words.add(w.lower())
        except (OSError, ValueError):
            pass
    extra = read_series_words(series_dir)
    words |= {w.lower() for w in extra.get("words", [])}
    words -= {w.lower() for w in extra.get("banned", [])}
    GLOSSARY.clear()
    GLOSSARY.update(words)
    return words


def read_series_words(series_dir: Path | str) -> dict:
    """`glossary.json` in the series folder: {"words": [...], "banned": [...]}
    -- words a person added (always in the glossary) and words the reader
    learned wrongly (never in it)."""
    import json

    path = Path(series_dir) / "glossary.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"words": [], "banned": []}
    return {
        "words": [str(w) for w in doc.get("words", []) if w],
        "banned": [str(w) for w in doc.get("banned", []) if w],
    }


def known(word: str) -> bool:
    lower, caps = dictionary()
    w = word.lower()
    stem = w.rstrip("'s")
    return w in GLOSSARY or w in lower or w in caps or stem in lower or stem in GLOSSARY


_ONE_LETTER = {"a", "i"}
# the only two-letter pieces a glued word may split into: the tesseract
# word list also holds "co", "wu", "rt", which turned WURT into "wu rt"
TWO_LETTER = {
    "to",
    "of",
    "in",
    "on",
    "at",
    "is",
    "it",
    "be",
    "we",
    "he",
    "me",
    "my",
    "so",
    "no",
    "do",
    "go",
    "up",
    "us",
    "if",
    "or",
    "an",
    "as",
    "by",
    "am",
    "ok",
    "oh",
    "ah",
    "hi",
    "eh",
    "um",
    "uh",
    "ya",
    "yo",
}


def split_glued(token: str) -> list[str]:
    """Split a token of glued words into dictionary words, fewest pieces first."""
    w = token.lower()
    lower, caps = dictionary()
    if not lower or known(w) or len(w) < 3 or w in GLOSSARY:
        return [token]
    n = len(w)

    def cost(parts: list[str]) -> tuple[int, int, int]:
        # fewest pieces, then fewest name-only pieces, then one long word plus
        # a short one ("i should") over two middling rare ones ("ish ould")
        return (
            len(parts),
            sum(p not in lower for p in parts),
            -sum(len(p) ** 2 for p in parts),
        )

    best: list[list[str] | None] = [None] * (n + 1)
    best[0] = []
    for i in range(1, n + 1):
        for j in range(max(0, i - 20), i):
            piece = w[j:i]
            prev = best[j]
            if prev is None:
                continue
            ok = piece in lower or piece in caps
            if len(piece) == 1 and piece not in _ONE_LETTER:
                ok = False
            if len(piece) == 2 and piece not in TWO_LETTER:
                ok = False
            if not ok:
                continue
            cand = prev + [piece]
            cur = best[i]
            if cur is None or cost(cand) < cost(cur):
                best[i] = cand
    parts = best[n]
    if not parts or len(parts) > max(2, n // 3):
        return [token]
    # keep the original letters' case
    out, k = [], 0
    for p in parts:
        out.append(token[k : k + len(p)])
        k += len(p)
    return out


_FIXES = [
    (re.compile(r"(?<=[A-Z])0(?=[A-Z])"), "O"),
    (re.compile(r"(?<=[A-Z])1(?=[A-Z])"), "I"),
    (re.compile(r"\|"), "I"),
    (re.compile(r"[‘’`]"), "'"),
    (re.compile(r"[“”]"), '"'),
    (re.compile(r"\s+([,.!?])"), r"\1"),
    (re.compile(r"\.\s*\.\s*\."), "..."),
    (re.compile(r"…"), "..."),
]


# words after which a lone "1" or "[" is the pronoun I ("1 GUESS", "[ CAN'T")
_I_VERBS = (
    "guess|think|know|can|can't|will|won't|am|have|had|was|don't|didn't|just|"
    "need|want|got|see|mean|must|should|could|would|really|never|still|"
    "thought|told|said|feel|hope|wish|swear|promise"
)
_STROKES = [
    # balloon and box edges that the reader turns into strokes and brackets
    (re.compile(r"[/\\]\s*\d(?=\s)"), " "),  # "/7 YOU" -> "YOU"
    (re.compile(r"\[(?=[A-Za-z])"), "I"),  # "[T TAKES" -> "IT TAKES"
    (re.compile(r"[/\\{}\]^=&%<>~]"), " "),
    (re.compile(r"(?<!\S)[\"']+(?!\S)"), " "),  # a quote mark standing alone
    (re.compile(r"\b1(?=[a-z]{2,})"), "I"),  # "1must" -> "Imust"
    (re.compile(r"\b1(?=[A-Z]{1,2}\b)"), "I"),  # "1S" -> "IS"
    (re.compile(r"(?i)\bT(?='(?:ll|m|ve|d)\b)"), "I"),  # "T'LL" -> "I'LL"
    (re.compile(r"(?<![A-Za-z0-9'])T(?![A-Za-z0-9'.])"), "I"),  # a lone T is I
    (re.compile(r"^7\s+(?=[A-Za-z])"), ""),  # a leading 7 is a balloon edge
    (re.compile(r"(?<=[.?!])\s*7\s*$"), ""),  # "...7" at the end is one too
    (re.compile(r"\?7\b"), "?"),
    # T glued to a verb is the pronoun I: "THAVE" -> "I HAVE"
    (
        re.compile(
            r"(?i)\bT(?=(?:have|had|was|can't|don't|won't|need|want|know|"
            r"guess|must|should|could|would|just)\b)"
        ),
        "I ",
    ),
    (re.compile(r"(?i)\b[1\[](?=\s+(?:" + _I_VERBS + r")\b)"), "I"),
    (re.compile(r"(?i)(^|[.!?]\s+)1(?=\s+[A-Za-z])"), r"\1I"),
]


def _drop_stray_letters(t: str) -> str:
    """Single consonants standing alone are stroke reads, not words:
    "N HAVE GOTTEN" -> "HAVE GOTTEN". A, I and O may stand alone."""
    return re.sub(
        r"(?i)(?<![A-Za-z0-9'])(?<!Mr\. )(?<!Dr\. )(?<!Ms\. )(?<!Mrs\. )"
        r"[B-HJ-NP-Zb-hj-np-z](?![A-Za-z'.-])",
        " ",
        t,
    )


def _trim_ends(t: str) -> str:
    """Runs of one-character scraps before the first word or after the last
    sentence are edge noise: 'N " - IF THE ...' and '... SCREWED! & S s 2'."""
    toks = t.split()
    first = next((i for i, w in enumerate(toks) if len(_LETTERS.findall(w)) >= 2), None)
    if first is None:
        return t
    if first >= 1 and all(
        len(w) <= 2 and not w.isalnum() and w.upper() not in ("I", "A")
        for w in toks[:first]
    ):
        toks = toks[first:]
    last = max((i for i, w in enumerate(toks) if re.search(r"[.!?]$", w)), default=None)
    if last is not None and len(toks) - 1 - last >= 1:
        tail = toks[last + 1 :]
        if all(len(w) == 1 for w in tail):
            toks = toks[: last + 1]
    return " ".join(toks)


_LETTERS = re.compile(r"[A-Za-z]")


def _join_glossary(t: str) -> str:
    """Two neighbouring tokens that spell a glossary word are that word:
    "BELLA TO" -> "BELLATO" when the series taught us bellato."""
    if not GLOSSARY:
        return t
    toks = t.split(" ")
    out: list[str] = []
    i = 0
    while i < len(toks):
        if i + 1 < len(toks):
            a, b = toks[i], toks[i + 1]
            core = (a + b).rstrip(".,!?;:")
            if core.isalpha() and core.lower() in GLOSSARY:
                out.append(a + b)
                i += 2
                continue
        out.append(toks[i])
        i += 1
    return " ".join(out)


def clean_raw(text: str) -> str:
    t = " ".join(text.split())
    for pat, rep in _STROKES:
        t = pat.sub(rep, t)
    for pat, rep in _FIXES:
        t = pat.sub(rep, t)
    t = _drop_stray_letters(t)
    # hyphenated line breaks: "IMPOR- TANT" -> "IMPORTANT"
    t = re.sub(r"([A-Za-z])- ([A-Za-z])", r"\1\2", t)
    t = _trim_ends(" ".join(t.split()))
    return _join_glossary(t).strip()


def normalize(raw: str) -> str:
    """Readable sentence-case text from raw comic lettering."""
    t = clean_raw(raw)
    if not t:
        return ""
    letters = [c for c in t if c.isalpha()]
    mostly_caps = letters and sum(c.isupper() for c in letters) / len(letters) > 0.7
    tokens = re.split(r"(\s+)", t)
    words: list[str] = []
    for tok in tokens:
        if tok.isspace() or not tok:
            words.append(tok)
            continue
        m = re.match(r"^([^A-Za-z']*)([A-Za-z']+)([^A-Za-z']*)$", tok)
        if m and mostly_caps:
            pieces = split_glued(m.group(2))
            words.append(m.group(1) + " ".join(pieces) + m.group(3))
        else:
            words.append(tok)
    t = "".join(words)
    if not mostly_caps:
        return t
    lower, caps = dictionary()
    out = []
    start = True
    for piece in re.split(r"(\s+)", t):
        if not piece or piece.isspace():
            out.append(piece)
            continue

        def recase(m: re.Match) -> str:
            w = m.group(0)
            lw = w.lower()
            if lw == "i" or lw.startswith("i'"):
                return "I" + lw[1:]
            if lw in caps or (
                lower and lw not in lower and lw.split("'")[0] not in lower
            ):
                return lw.capitalize()
            return lw

        new = _WORD.sub(recase, piece)
        if start:
            new = re.sub(r"[A-Za-z]", lambda m: m.group(0).upper(), new, count=1)
        out.append(new)
        start = bool(re.search(r"[.!?]$", piece)) and not piece.endswith("...")
    return "".join(out)
