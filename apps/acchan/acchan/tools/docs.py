"""Documents: read PDFs, Word/ODF/PowerPoint, EPUB, Markdown and web pages in
full, and answer questions about a whole document.

Small models have a 20k-token window and read poorly past a few thousand
tokens, so a question about a 300-page PDF is answered in two steps: pick the
passages that best match the question (BM25 over page-tagged chunks, stdlib),
then give only those to the model. Every passage carries its page number so
the answer can cite it. Extracted text is cached by path and modification
time in ~/.cache/acchan/docs.
"""

from __future__ import annotations

import hashlib
import math
import re
import subprocess
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Annotated

from ..registry import ToolError, tool
from ..sysutil import CACHE, run
from ..sysutil import path as to_path

TOOLSET = "docs"
TOOLSET_SUMMARY = "read PDF/Word/slides/EPUB/Markdown/web documents in full and answer questions about a whole document"

TOOLSET_KEYWORDS = (
    "pdf",
    "document",
    "doc",
    "docx",
    "slides",
    "lecture",
    "notes",
    "chapter",
    "page",
    "textbook",
    "worksheet",
    "assignment",
    "paper",
    "read",
    "summarise",
    "summarize",
    "book",
    "epub",
    "class",
    "course",
    "calculus",
    "exam",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_COMPANIONS = ("find_files", "list_dir")  # documents must be found first
TOOLSET_EXAMPLES = [
    ("find my MATH1014 lecture notes", "find_files", {"name": "MATH1014"}),
    ("read me the pdf on my screen", "whats_on_screen", {}),
    (
        "in my calc lecture 5 pdf, how do I differentiate ln x?",
        "ask_document",
        {
            "source": "~/Documents/calc/lecture5.pdf",
            "question": "how to differentiate ln x",
        },
    ),
]

STOP = set(
    "a an the and or but if of to in on at for with by from as is are was were be been it this that these those "
    "what which who whom how why when where do does did can could should would will i you he she we they me my "
    "your its our their about into than then there here so not no yes also just only very more most such".split()
)


def pdf_bytes_to_text(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(data)
        tmp.flush()
        return _pdf_text(Path(tmp.name))


def _pdf_text(file: Path, first: int = 0, last: int = 0) -> str:
    cmd = ["pdftotext", "-layout", "-enc", "UTF-8"]
    if first:
        cmd += ["-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    cmd += [str(file), "-"]
    code, out = run(cmd, timeout=180)
    if code != 0:
        raise ToolError(f"Could not read the PDF: {out.strip()[-300:]}")
    pages = out.split("\f")
    start = first or 1
    tagged = [
        f"[page {start + i}]\n{p.strip()}" for i, p in enumerate(pages) if p.strip()
    ]
    text = "\n\n".join(tagged)
    if len(re.sub(r"\[page \d+\]|\s", "", text)) < 50 and shutil_which("tesseract"):
        text = _ocr_pdf(file, first, last)
    return text


def shutil_which(name: str) -> bool:
    import shutil

    return shutil.which(name) is not None


def _ocr_pdf(file: Path, first: int, last: int) -> str:
    """Scanned PDFs have no text layer; render pages and OCR them."""
    with tempfile.TemporaryDirectory(prefix="acchan-ocr-") as work:
        cmd = ["pdftoppm", "-r", "150", "-gray", "-png"]
        cmd += ["-f", str(first or 1), "-l", str(last or (first or 1) + 29)]
        cmd += [str(file), f"{work}/p"]
        run(cmd, timeout=600)
        parts = []
        for image in sorted(Path(work).glob("p-*.png")):
            number = int(re.findall(r"(\d+)", image.stem)[-1])
            code, out = run(["tesseract", str(image), "-", "--psm", "3"], timeout=120)
            parts.append(f"[page {number}]\n{out.strip()}")
        return "\n\n".join(parts)


def _xml_text(xml: str) -> str:
    xml = re.sub(r"</(w:p|text:p|text:h|a:p|p|div|h\d|li|tr)>", "\n", xml)
    xml = re.sub(r"<(w:tab|text:tab)[^>]*/>", "\t", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    import html

    return re.sub(r"\n{3,}", "\n\n", html.unescape(xml)).strip()


def _zip_text(file: Path) -> str:
    suffix = file.suffix.lower()
    with zipfile.ZipFile(file) as z:
        names = z.namelist()
        if suffix == ".docx":
            return _xml_text(z.read("word/document.xml").decode("utf-8", "replace"))
        if suffix in (".odt", ".odp", ".ods"):
            return _xml_text(z.read("content.xml").decode("utf-8", "replace"))
        if suffix == ".pptx":
            slides = sorted(
                (n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                key=lambda n: int(re.findall(r"\d+", n)[-1]),
            )
            return "\n\n".join(
                f"[slide {i}]\n{_xml_text(z.read(n).decode('utf-8', 'replace'))}"
                for i, n in enumerate(slides, 1)
            )
        if suffix == ".xlsx":
            shared = ""
            if "xl/sharedStrings.xml" in names:
                shared = _xml_text(
                    z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
                )
            return "Spreadsheet text (cells, flattened):\n" + shared
        if suffix == ".epub":
            parts = [n for n in names if n.endswith((".xhtml", ".html", ".htm"))]
            return "\n\n".join(
                _xml_text(z.read(n).decode("utf-8", "replace")) for n in sorted(parts)
            )
    raise ToolError(f"Cannot read {file.suffix} files.")


def document_text(source: str) -> tuple[str, str]:
    """(display name, full text) of a file or web address, cached."""
    if re.match(r"^[a-z]+://", source.strip()):
        from .browser import fetch

        title, text = fetch(source.strip())
        return title or source, text
    file = to_path(source)
    if not file.exists():
        raise ToolError(
            f"{file} does not exist. Use find_files to locate it, or whats_on_screen if the user means a document they have open."
        )
    stat = file.stat()
    key = hashlib.sha1(f"{file}|{stat.st_mtime}|{stat.st_size}".encode()).hexdigest()
    cache = CACHE / "docs"
    cache.mkdir(parents=True, exist_ok=True)
    hit = cache / f"{key}.txt"
    if hit.exists():
        return file.name, hit.read_text(encoding="utf-8")
    suffix = file.suffix.lower()
    if suffix == ".pdf":
        text = _pdf_text(file)
    elif suffix in (".docx", ".odt", ".odp", ".ods", ".pptx", ".xlsx", ".epub"):
        text = _zip_text(file)
    elif suffix in (".doc", ".ppt", ".rtf") and shutil_which("libreoffice"):
        with tempfile.TemporaryDirectory() as work:
            subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "txt:Text",
                    "--outdir",
                    work,
                    str(file),
                ],
                capture_output=True,
                timeout=180,
            )
            out = next(Path(work).glob("*.txt"), None)
            text = out.read_text(errors="replace") if out else ""
    elif suffix in (".html", ".htm"):
        text = _xml_text(file.read_text(encoding="utf-8", errors="replace"))
    elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"):
        code, text = run(["tesseract", str(file), "-"], timeout=120)
    else:
        raw = file.read_bytes()[:5_000_000]
        if b"\0" in raw[:4096]:
            raise ToolError(f"{file.name} is not a document I can read.")
        text = raw.decode("utf-8", "replace")
    hit.write_text(text, encoding="utf-8")
    return file.name, text


def _tokens(text: str) -> list[str]:
    return [
        w
        for w in re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())
        if w not in STOP and len(w) > 1
    ]


def _chunks(text: str, size: int) -> list[str]:
    """Paragraph-aligned chunks of about `size` characters, each starting with
    the page marker it falls under."""
    page = ""
    chunks, current = [], ""
    for para in re.split(r"\n\s*\n", text):
        marker = re.match(r"\[(page|slide|topic) ([\w.-]+)\]", para)
        if marker:
            page = marker.group(0)
        if len(current) + len(para) > size and current:
            chunks.append(current.strip())
            current = page + "\n" if page and not para.startswith("[") else ""
        current += para + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def best_passages(text: str, question: str, k: int = 5, size: int = 1200) -> list[str]:
    """The k chunks of `text` that best match `question`, in document order."""
    chunks = _chunks(text, size)
    if len(chunks) <= k:
        return chunks
    query = _tokens(question)
    if not query:
        return chunks[:k]
    docs = [Counter(_tokens(c)) for c in chunks]
    avg = sum(sum(d.values()) for d in docs) / len(docs) or 1
    df = Counter(t for d in docs for t in set(d))
    n = len(docs)
    scores = []
    for i, d in enumerate(docs):
        length = sum(d.values()) or 1
        s = 0.0
        for t in query:
            if t not in d:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            tf = d[t]
            s += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg))
        # Numbers and exact phrases matter in course notes ("question 4b").
        if question.lower() in chunks[i].lower():
            s += 5
        scores.append((s, i))
    top = sorted(scores, reverse=True)[:k]
    return [chunks[i] for _s, i in sorted(top, key=lambda x: x[1]) if _s > 0] or [
        chunks[i] for _s, i in top
    ]


@tool(
    TOOLSET,
    example={"source": "~/Documents/calc/notes.pdf", "start_page": 1, "end_page": 3},
    voice="ok",
)
def read_document(
    source: Annotated[str, "File path or web address of the document"],
    start_page: Annotated[int, "First page (PDF) to read"] = 1,
    end_page: Annotated[int, "Last page to read; 0 for as much as fits"] = 0,
    start: Annotated[int, "Character offset to continue from (non-PDF)"] = 0,
) -> str:
    """Read a document's text: PDF (by pages), Word, ODF, PowerPoint, EPUB, Markdown, HTML, images (OCR) or a web address."""
    name, text = document_text(source)
    if "[page " in text[:200] and (start_page > 1 or end_page):
        parts = re.split(r"(?=\[page \d+\])", text)
        wanted = []
        for part in parts:
            m = re.match(r"\[page (\d+)\]", part)
            if (
                m
                and int(m.group(1)) >= start_page
                and (not end_page or int(m.group(1)) <= end_page)
            ):
                wanted.append(part)
        text = "".join(wanted)
        start = 0
    piece = text[start : start + 9000]
    total = len(text)
    more = ""
    if start + len(piece) < total:
        last_page = re.findall(r"\[page (\d+)\]", piece)
        nxt = (
            f"start_page={int(last_page[-1]) + 1}"
            if last_page
            else f"start={start + len(piece)}"
        )
        more = f"\n[shown {len(piece)} of {total} characters; continue with {nxt}, or use ask_document for a question about the whole thing]"
    return f"# {name}\n{piece}{more}"


@tool(
    TOOLSET,
    example={
        "source": "~/Documents/calc/lecture5.pdf",
        "question": "how do I find the derivative of ln x?",
    },
    voice="ok",
)
def ask_document(
    source: Annotated[str, "File path or web address of the document"],
    question: Annotated[str, "The question to answer from the document"],
) -> str:
    """Find the passages of a whole document (any length) that answer a question. Answer from them and cite the pages."""
    name, text = document_text(source)
    if not text.strip():
        raise ToolError(f"{name} has no readable text.")
    passages = best_passages(text, question, k=5, size=1200)
    return (
        f"From {name} ({len(text)} characters total), the most relevant passages:\n\n"
        + "\n\n---\n\n".join(passages)
    )


@tool(TOOLSET, example={"source": "~/Documents/book.pdf"}, voice="ok")
def document_info(source: Annotated[str, "File path of the document"]) -> str:
    """Page count, title and headings of a document, to plan how to read it."""
    file = to_path(source)
    lines = [f"{file.name}  ({file.stat().st_size // 1024} KB)"]
    if file.suffix.lower() == ".pdf":
        code, out = run(["pdfinfo", str(file)], timeout=30)
        lines += [
            l
            for l in out.splitlines()
            if l.split(":")[0] in ("Title", "Author", "Pages")
        ]
    _name, text = document_text(source)
    heads = [
        l.strip()
        for l in text.splitlines()
        if re.match(r"^(#{1,3} |\d+(\.\d+)*\s+[A-Z]|[A-Z][A-Z ]{6,}$)", l.strip())
    ]
    if heads:
        lines.append("Headings:\n" + "\n".join(heads[:40]))
    lines.append(f"{len(text)} characters of text.")
    return "\n".join(lines)
