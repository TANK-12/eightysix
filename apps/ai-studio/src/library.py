"""A tiny persistent, searchable history of everything generated.

Every image/video job gets one row: prompt, params, output path, timestamp.
Backed by sqlite3 (stdlib, no extra dependency) so the whole "library"
feature costs nothing in disk footprint beyond a small .db file.
"""

import contextlib
import json
import sqlite3
import subprocess
import time
from pathlib import Path

import config

DB_PATH = config.OUTPUTS_DIR / "library.db"
THUMB_NAME = "thumb.jpg"
THUMB_SIZE = 384  # longest side, px: plenty for a gallery tile


@contextlib.contextmanager
def _connect():
    """One connection per call, committed on success and always closed
    (sqlite3's own `with conn` only commits; it never closes)."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def output_path(url):
    """The file on disk behind an "/outputs/<id>/<file>" url, or None when the
    url points anywhere else (outside the outputs folder included)."""
    prefix = "/outputs/"
    if not url or not url.startswith(prefix):
        return None
    root = Path(config.OUTPUTS_DIR).resolve()
    path = (root / url[len(prefix) :]).resolve()
    if root not in path.parents:
        return None
    return path


def make_thumbnail(source, dest):
    """A small JPEG of an image, or of a video's first frame (via ffmpeg).
    Returns True when `dest` was written."""
    from PIL import Image

    source, dest = Path(source), Path(dest)
    try:
        if source.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv"):
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-vf",
                    # shrink to fit THUMB_SIZE, never enlarge
                    f"scale='min({THUMB_SIZE},iw)':'min({THUMB_SIZE},ih)'"
                    ":force_original_aspect_ratio=decrease",
                    str(dest),
                ],
                capture_output=True,
                timeout=60,
            )
            return proc.returncode == 0 and dest.is_file()
        with Image.open(source) as im:
            im.draft(
                "RGB", (THUMB_SIZE, THUMB_SIZE)
            )  # fast JPEG decode at reduced size
            im = im.convert("RGB")
            im.thumbnail((THUMB_SIZE, THUMB_SIZE))
            im.save(dest, quality=85)
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def thumbnail_url(url):
    """Url of a small thumbnail beside the output, made the first time it is
    asked for. Falls back to the output's own url when one can't be made."""
    path = output_path(url)
    if path is None or not path.is_file():
        return url
    thumb = path.with_name(THUMB_NAME)
    if thumb.is_file() or make_thumbnail(path, thumb):
        return url.rsplit("/", 1)[0] + "/" + THUMB_NAME
    return url


def _row(r):
    row = dict(r)
    path = output_path(row["url"])
    row["missing"] = path is not None and not path.is_file()
    row["thumb_url"] = row["url"] if row["missing"] else thumbnail_url(row["url"])
    return row


def init():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,           -- 'image' or 'video'
                prompt TEXT NOT NULL,
                negative_prompt TEXT,
                params TEXT,                  -- json blob of the request
                url TEXT NOT NULL,
                created_at REAL NOT NULL,
                total_seconds REAL
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS generations_fts
            USING fts5(id UNINDEXED, prompt, negative_prompt)
        """)


def record(job_id, kind, prompt, negative_prompt, params, url, total_seconds):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO generations (id, kind, prompt, negative_prompt, params, url, created_at, total_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                kind,
                prompt,
                negative_prompt,
                json.dumps(params),
                url,
                time.time(),
                total_seconds,
            ),
        )
        conn.execute(
            "INSERT INTO generations_fts (id, prompt, negative_prompt) VALUES (?, ?, ?)",
            (job_id, prompt, negative_prompt or ""),
        )


def delete(job_id):
    with _connect() as conn:
        cur = conn.execute("DELETE FROM generations WHERE id = ?", (job_id,))
        conn.execute("DELETE FROM generations_fts WHERE id = ?", (job_id,))
        return cur.rowcount > 0


def search(query="", kind=None, limit=60):
    limit = max(1, min(int(limit), 500))
    with _connect() as conn:
        match = _match_expr(query)
        if query.strip() and not match:
            return []  # only punctuation: nothing to look for
        if match:
            sql = """
                SELECT g.* FROM generations g
                JOIN generations_fts f ON f.id = g.id
                WHERE generations_fts MATCH ?
            """
            params: list = [match]
        else:
            sql = "SELECT * FROM generations g WHERE 1=1"
            params: list = []
        if kind:
            sql += " AND g.kind = ?"
            params.append(kind)
        sql += " ORDER BY g.created_at DESC LIMIT ?"
        params.append(limit)
        try:
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        except sqlite3.OperationalError:
            return []  # a query FTS5 still cannot parse finds nothing
    # thumbnails are made after the connection is closed, so a first search
    # that makes many never holds the database while a job records its result
    return [_row(r) for r in rows]


def _match_expr(query):
    """Turn what someone typed into a safe FTS5 query: every word becomes a
    quoted phrase (so quotes, AND, NEAR, colons and brackets are just text)
    and the last one matches as a prefix, as it did before."""
    words = [w for w in query.split() if any(c.isalnum() for c in w)]
    if not words:
        return ""
    return " ".join('"' + w.replace('"', '""') + '"' for w in words) + "*"


def orphans():
    """Job folders in outputs/ that no library row points at, with their size
    in bytes: what a failed or cancelled video job left behind. Listed only;
    nothing here deletes them."""
    root = Path(config.OUTPUTS_DIR)
    with _connect() as conn:
        known = {r["id"] for r in conn.execute("SELECT id FROM generations")}
    found = []
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if d.is_dir() and d.name.isalnum() and d.name not in known:
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            found.append({"id": d.name, "bytes": size})
    return found
