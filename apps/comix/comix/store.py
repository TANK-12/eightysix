"""Series, chapters and per-page download state, in one SQLite file.

Every page a chapter needs is a row, so a chapter that half-loaded keeps its
good pages and only the missing ones are fetched again, even after a crash or
a restart. A chapter becomes "done" only when every page is saved and checked.

Chapter states:
    skipped   listed on the site but not chosen (another group's copy)
    queued    waiting for the worker (next_try says when it may start)
    running   being downloaded right now
    partial   some pages still missing; retried automatically at next_try
    failed    gave up after too many tries; "Retry" puts it back in the queue
    done      CBZ built, cbz holds its path
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from comix import sources

DB_PATH = Path(
    os.environ.get("COMIX_DB", Path.home() / ".local/share/forge/comix/comix.db")
)
GROUP_MODES = ("pending", "one", "ranked", "all")

SCHEMA = """
create table if not exists series (
    id integer primary key,
    url text unique not null,
    title text not null,
    source text not null,
    group_mode text not null default 'ranked',
    groups text not null default '[]',
    from_library integer not null default 0,
    added real not null
);
create table if not exists chapters (
    id integer primary key,
    series_id integer not null references series(id) on delete cascade,
    number real not null,
    grp text not null default '',
    url text unique not null,
    state text not null default 'skipped',
    pages_total integer not null default 0,
    pages_ok integer not null default 0,
    attempts integer not null default 0,
    next_try real not null default 0,
    error text not null default '',
    cbz text not null default '',
    updated real not null default 0
);
create table if not exists pages (
    chapter_id integer not null references chapters(id) on delete cascade,
    idx integer not null,
    state text not null,
    attempts integer not null default 0,
    file text not null default '',
    reason text not null default '',
    primary key (chapter_id, idx)
);
"""


def choose(rows: list[dict], mode: str, groups: list[str]) -> set[str]:
    """Which chapter urls to download, given every (chapter, group) row.

    one     only the first group in ``groups``
    ranked  per chapter number, the first group in ``groups`` that has it;
            a chapter none of them has comes from whichever group does
    all     every group's copy
    pending nothing yet: the series waits for Emerson to pick its groups
    """
    if mode not in GROUP_MODES:
        raise ValueError(f"unknown group mode {mode!r}")
    if mode == "pending":
        return set()
    if mode == "all":
        return {r["url"] for r in rows}
    if mode == "one":
        want = groups[0] if groups else None
        return {r["url"] for r in rows if want is None or r["group"] == want}
    rank = {g: i for i, g in enumerate(groups)}
    best: dict[float, dict] = {}
    for r in rows:
        cur = best.get(r["number"])
        r_rank = rank.get(r["group"], len(rank))
        if cur is None or r_rank < rank.get(cur["group"], len(rank)):
            best[r["number"]] = r
    return {r["url"] for r in best.values()}


class Store:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("pragma foreign_keys = on")
        self._db.executescript(SCHEMA)
        # Rows listed before unnamed chapters were given a group name.
        self._db.execute(
            "update chapters set grp=? where grp=''", (sources.UNKNOWN_GROUP,)
        )
        self._db.commit()
        self._lock = threading.Lock()

    def _x(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur

    def _all(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    # --- series ---------------------------------------------------------------

    def save_series(
        self,
        url: str,
        title: str,
        source: str,
        rows: list[dict],
        mode: str,
        groups: list[str],
        from_library: bool = False,
    ) -> int:
        """Add a series or refresh its chapter list, then queue the chosen rows.

        Rows already in the table keep their state, so a refresh only queues
        chapters that are new since last time.
        """
        rows = [{**r, "group": r["group"] or sources.UNKNOWN_GROUP} for r in rows]
        choose(rows, mode, groups)  # validates mode before anything is written
        self._x(
            "insert into series (url, title, source, group_mode, groups, "
            "from_library, added) values (?,?,?,?,?,?,?) on conflict(url) do "
            "update set title=excluded.title, group_mode=excluded.group_mode, "
            "groups=excluded.groups",
            (
                url,
                title,
                source,
                mode,
                json.dumps(groups),
                int(from_library),
                time.time(),
            ),
        )
        sid = self._all("select id from series where url=?", (url,))[0]["id"]
        known = {r["url"] for r in self.chapters(sid)}
        wanted = choose(rows, mode, groups)
        now = time.time()
        for r in rows:
            if r["url"] in known:
                continue
            state = "queued" if r["url"] in wanted else "skipped"
            self._x(
                "insert into chapters (series_id, number, grp, url, state, updated) "
                "values (?,?,?,?,?,?)",
                (sid, r["number"], r["group"], r["url"], state, now),
            )
        return sid

    def apply_choice(self, sid: int, mode: str, groups: list[str]) -> int:
        """Change a series' group choice; chapters not done or running follow it.

        Returns how many chapters are now queued.
        """
        rows = [
            {"number": c["number"], "group": c["grp"], "url": c["url"]}
            for c in self.chapters(sid)
        ]
        wanted = choose(rows, mode, groups)
        self._x(
            "update series set group_mode=?, groups=? where id=?",
            (mode, json.dumps(groups), sid),
        )
        now = time.time()
        for c in self.chapters(sid):
            if c["state"] in ("done", "running"):
                continue
            if c["url"] in wanted and c["state"] == "skipped":
                self._x(
                    "update chapters set state='queued', next_try=0, updated=? "
                    "where id=?",
                    (now, c["id"]),
                )
            elif c["url"] not in wanted and c["state"] != "skipped":
                self._x(
                    "update chapters set state='skipped', updated=? where id=?",
                    (now, c["id"]),
                )
        return sum(1 for c in self.chapters(sid) if c["state"] in ("queued", "partial"))

    def series(self, sid: int | None = None) -> list[dict]:
        rows = self._all(
            "select s.*, "
            "sum(c.state='done') as done, sum(c.state!='skipped') as wanted, "
            "count(c.id) as listed "
            "from series s left join chapters c on c.series_id=s.id "
            + ("where s.id=? " if sid is not None else "")
            + "group by s.id order by s.title collate nocase",
            (sid,) if sid is not None else (),
        )
        for r in rows:
            r["groups"] = json.loads(r["groups"])
        return rows

    def delete_series(self, sid: int) -> None:
        self._x("delete from series where id=?", (sid,))

    # --- chapters -------------------------------------------------------------

    def chapters(self, sid: int) -> list[dict]:
        return self._all(
            "select * from chapters where series_id=? order by number, grp", (sid,)
        )

    def chapter(self, cid: int) -> dict | None:
        rows = self._all(
            "select c.*, s.title as series_title from chapters c "
            "join series s on s.id=c.series_id where c.id=?",
            (cid,),
        )
        return rows[0] if rows else None

    def set_wanted(self, cid: int, wanted: bool) -> None:
        if wanted:
            self._x(
                "update chapters set state='queued', next_try=0, updated=? "
                "where id=? and state in ('skipped','failed','partial')",
                (time.time(), cid),
            )
        else:
            self._x(
                "update chapters set state='skipped', updated=? "
                "where id=? and state in ('queued','failed','partial')",
                (time.time(), cid),
            )

    def retry_failed(self) -> int:
        return self._x(
            "update chapters set state='queued', next_try=0, attempts=0 "
            "where state in ('failed','partial')"
        ).rowcount

    def queue(self, limit: int = 300) -> list[dict]:
        return self._all(
            "select c.*, s.title as series_title from chapters c "
            "join series s on s.id=c.series_id "
            "where c.state not in ('skipped','done') "
            "order by c.state='running' desc, c.next_try, s.title, c.number "
            "limit ?",
            (limit,),
        )

    def counts(self) -> dict:
        rows = self._all("select state, count(*) as n from chapters group by state")
        return {r["state"]: r["n"] for r in rows}

    def claim_next(self, now: float | None = None) -> dict | None:
        """Take the next chapter that may run now and mark it running."""
        now = time.time() if now is None else now
        with self._lock:
            row = self._db.execute(
                "select id from chapters where state in ('queued','partial') "
                "and next_try<=? order by next_try, series_id, number limit 1",
                (now,),
            ).fetchone()
            if row is None:
                return None
            self._db.execute(
                "update chapters set state='running', updated=? where id=?",
                (now, row["id"]),
            )
            self._db.commit()
        return self.chapter(row["id"])

    def reset_running(self) -> int:
        """After a crash or restart nothing is really running: requeue it."""
        return self._x(
            "update chapters set state='queued', next_try=0 where state='running'"
        ).rowcount

    def set_total(self, cid: int, total: int) -> None:
        self._x("update chapters set pages_total=? where id=?", (total, cid))

    def finish(self, cid: int, cbz: str) -> None:
        self._x(
            "update chapters set state='done', cbz=?, error='', updated=? where id=?",
            (cbz, time.time(), cid),
        )

    def give_up_for_now(
        self, cid: int, error: str, next_try: float, max_attempts: int
    ) -> str:
        """Record a chapter that is still missing pages; returns its new state."""
        ch = self.chapter(cid)
        attempts = (ch["attempts"] if ch else 0) + 1
        state = "failed" if attempts >= max_attempts else "partial"
        self._x(
            "update chapters set state=?, attempts=?, next_try=?, error=?, "
            "updated=? where id=?",
            (state, attempts, next_try, error, time.time(), cid),
        )
        return state

    # --- pages ----------------------------------------------------------------

    def pages(self, cid: int) -> list[dict]:
        return self._all("select * from pages where chapter_id=? order by idx", (cid,))

    def page_ok(self, cid: int, idx: int, file: str) -> None:
        self._x(
            "insert into pages (chapter_id, idx, state, attempts, file) "
            "values (?,?,'ok',1,?) on conflict(chapter_id, idx) do update set "
            "state='ok', attempts=attempts+1, file=excluded.file, reason=''",
            (cid, idx, file),
        )
        self._count_ok(cid)

    def page_failed(self, cid: int, idx: int, reason: str) -> None:
        self._x(
            "insert into pages (chapter_id, idx, state, attempts, reason) "
            "values (?,?,'failed',1,?) on conflict(chapter_id, idx) do update "
            "set state='failed', attempts=attempts+1, reason=excluded.reason",
            (cid, idx, reason),
        )

    def forget_page(self, cid: int, idx: int) -> None:
        self._x("delete from pages where chapter_id=? and idx=?", (cid, idx))
        self._count_ok(cid)

    def _count_ok(self, cid: int) -> None:
        self._x(
            "update chapters set pages_ok=(select count(*) from pages "
            "where chapter_id=? and state='ok') where id=?",
            (cid, cid),
        )
