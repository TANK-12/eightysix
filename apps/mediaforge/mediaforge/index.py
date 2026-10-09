"""
SQLite file index — fast search, largest-files, and duplicate detection across
big folders / drives without re-walking every time.

Schema: files(path UNIQUE, name, ext, dir, size, mtime, sig)
`sig` (quick hash) is filled lazily, only for duplicate scans.
"""

import os
import sqlite3
import time
from pathlib import Path

from .config import INDEX_DB
from .manifest import quick_hash


class FileIndex:
    def __init__(self, db_path=INDEX_DB):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS files(
            path TEXT PRIMARY KEY, name TEXT, ext TEXT, dir TEXT,
            size INTEGER, mtime REAL, sig TEXT)""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_size ON files(size)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_name ON files(name)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_sig ON files(sig)")
        self.conn.commit()

    # ---------------- scanning ----------------
    def scan(self, root, min_bytes=0, exts=None, on_status=lambda s: None, should_stop=lambda: False):
        root = Path(root)
        exts = {e.lower() for e in exts} if exts else None
        buf, n = [], 0
        stack = [str(root)]
        while stack:
            if should_stop():
                break
            d = stack.pop()
            try:
                with os.scandir(d) as it:
                    for e in it:
                        try:
                            if e.is_symlink():
                                continue
                            if e.is_dir():
                                stack.append(e.path)
                            elif e.is_file():
                                st = e.stat()
                                if st.st_size < min_bytes:
                                    continue
                                ext = os.path.splitext(e.name)[1].lower()
                                if exts and ext not in exts:
                                    continue
                                buf.append((e.path, e.name, ext, d, st.st_size, st.st_mtime, None))
                                n += 1
                                if len(buf) >= 800:
                                    self._flush(buf); buf = []
                                    on_status(f"indexed {n:,} files…")
                        except OSError:
                            continue
            except OSError:
                continue
        if buf:
            self._flush(buf)
        on_status(f"scan complete — {n:,} files indexed under {root}")
        return n

    def _flush(self, rows):
        self.conn.executemany(
            "INSERT OR REPLACE INTO files(path,name,ext,dir,size,mtime,sig) VALUES(?,?,?,?,?,?,?)",
            rows)
        self.conn.commit()

    # ---------------- queries ----------------
    def search(self, term="", min_mb=0, ext="", limit=800, order="size"):
        q = "SELECT name, ext, size, path FROM files WHERE 1=1"
        args = []
        if term:
            q += " AND name LIKE ?"; args.append(f"%{term}%")
        if min_mb:
            q += " AND size >= ?"; args.append(int(min_mb * 1024 * 1024))
        if ext:
            q += " AND ext = ?"; args.append(ext if ext.startswith(".") else "." + ext)
        q += f" ORDER BY {'size DESC' if order == 'size' else 'name'} LIMIT ?"
        args.append(limit)
        return self.conn.execute(q, args).fetchall()

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    def clear(self):
        self.conn.execute("DELETE FROM files")
        self.conn.commit()

    def clean_dead(self):
        rows = self.conn.execute("SELECT path FROM files").fetchall()
        gone = [(p,) for (p,) in rows if not os.path.exists(p)]
        if gone:
            self.conn.executemany("DELETE FROM files WHERE path = ?", gone)
            self.conn.commit()
        return len(gone)

    # ---------------- duplicates ----------------
    def find_duplicates(self, min_bytes=1_000_000, on_status=lambda s: None, should_stop=lambda: False):
        """Group by size, then quick-hash the candidates. Returns list of groups
        (each a list of paths), all identical."""
        rows = self.conn.execute(
            "SELECT size, COUNT(*) c FROM files WHERE size >= ? GROUP BY size HAVING c > 1",
            (min_bytes,)).fetchall()
        groups = []
        done = 0
        for size, _ in rows:
            if should_stop():
                break
            paths = [p for (p,) in self.conn.execute(
                "SELECT path FROM files WHERE size = ?", (size,)).fetchall()
                if os.path.exists(p)]
            by_sig = {}
            for p in paths:
                sig = quick_hash(p)
                if sig:
                    self.conn.execute("UPDATE files SET sig=? WHERE path=?", (sig, p))
                    by_sig.setdefault(sig, []).append(p)
            for sig, plist in by_sig.items():
                if len(plist) > 1:
                    groups.append(sorted(plist))
            done += 1
            if done % 20 == 0:
                self.conn.commit()
                on_status(f"checked {done}/{len(rows)} size-buckets, {len(groups)} dup groups")
        self.conn.commit()
        return groups
