import io
import sqlite3
import time
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from comix import settings
from comix.downloader import (
    Worker,
    stop_stray_browsers,
    build_cbz,
    cbz_path,
    chapter_stem,
    retry_delay,
)
from comix.session import read_cookies, summary
from comix.sources import UNKNOWN_GROUP, comix_to, find_for_url
from comix.store import Store, choose

URL = "https://comix.to/title/abc-some-series"


def rows():
    def r(n, g):
        return {
            "number": n,
            "group": g,
            "url": f"{URL}/{g[:1]}-chapter-{n:g}",
            "label": "",
        }

    return [
        r(1, "Asura"),
        r(1, "WebToon"),
        r(2, "WebToon"),
        r(3, "Asura"),
        r(3.5, "Kraken"),
    ]


def page_png(seed: int) -> bytes:
    im = Image.new("RGB", (40, 60))
    im.putdata(
        [((x * 7 + seed) % 256, (x * 3) % 256, seed % 256) for x in range(40 * 60)]
    )
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


class FakeReader:
    """A chapter of ``total`` pages; ``flaky`` pages fail until the Nth reload."""

    loads = 0

    def __init__(self, total=4, flaky=None, blank=(), fixed_after=1):
        self.total, self.flaky, self.blank = total, flaky or {}, set(blank)
        self.fixed_after = fixed_after
        self.captured: list[int] = []

    def __call__(self, cookies, slot):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def load(self, url):
        FakeReader.loads += 1
        self.loaded = getattr(self, "loaded", 0) + 1
        return self.total

    def reload(self):
        return self.load("")

    def capture(self, idx):
        self.captured.append(idx)
        if idx in self.flaky and self.loaded <= self.flaky[idx]:
            return None, "", "image never loaded"
        if idx in self.blank:
            return Image_blank(), "png", ""
        return page_png(idx), "png", ""


def Image_blank():
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), (255, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


def got(value):
    """A row the test expects to exist."""
    assert value is not None
    return value


def make_store(tmp_path):
    return Store(tmp_path / "t.db")


def add(store, mode="ranked", groups=("WebToon", "Asura")):
    return store.save_series(URL, "Some Series", "comix", rows(), mode, list(groups))


def worker(store, reader, logs=None):
    return Worker(
        store,
        (logs if logs is not None else []).append,
        reader_factory=reader,
        cookie_reader=lambda domain: [],
        sleep=lambda s: None,
    )


# --- group choice -------------------------------------------------------------------


def test_ranked_takes_best_group_per_chapter_and_falls_back():
    got = choose(rows(), "ranked", ["WebToon", "Asura"])
    assert got == {
        f"{URL}/W-chapter-1",
        f"{URL}/W-chapter-2",
        f"{URL}/A-chapter-3",
        f"{URL}/K-chapter-3.5",  # no ranked group has 3.5: any group's copy
    }


def test_one_group_and_all_modes():
    assert choose(rows(), "one", ["Asura"]) == {
        f"{URL}/A-chapter-1",
        f"{URL}/A-chapter-3",
    }
    assert len(choose(rows(), "all", [])) == 5
    with pytest.raises(ValueError):
        choose(rows(), "most", [])


def test_refresh_only_queues_new_chapters(tmp_path):
    store = make_store(tmp_path)
    sid = add(store)
    first = {c["url"]: c["state"] for c in store.chapters(sid)}
    assert sorted(first.values()).count("queued") == 4
    cid = store.chapters(sid)[0]["id"]
    store.finish(cid, "/x.cbz")
    newer = rows() + [
        {"number": 4, "group": "WebToon", "url": f"{URL}/W-chapter-4", "label": ""}
    ]
    store.save_series(
        URL, "Some Series", "comix", newer, "ranked", ["WebToon", "Asura"]
    )
    after = {c["url"]: c["state"] for c in store.chapters(sid)}
    assert after[f"{URL}/W-chapter-4"] == "queued"
    assert got(store.chapter(cid))["state"] == "done"  # finished work untouched


def test_pending_series_queues_nothing_until_groups_are_picked(tmp_path):
    store = make_store(tmp_path)
    sid = add(store, mode="pending", groups=())
    assert {c["state"] for c in store.chapters(sid)} == {"skipped"}
    assert store.apply_choice(sid, "one", ["Asura"]) == 2
    assert store.apply_choice(sid, "all", []) == 5
    assert store.apply_choice(sid, "one", ["Kraken"]) == 1
    assert store.series(sid)[0]["group_mode"] == "one"


# --- the worker -------------------------------------------------------------------


def test_clean_chapter_becomes_a_complete_cbz(tmp_path):
    store = make_store(tmp_path)
    add(store)
    ch = got(store.claim_next())
    state = worker(store, FakeReader(total=4)).run_chapter(ch, settings.load())
    assert state == "done"
    done = got(store.chapter(ch["id"]))
    with zipfile.ZipFile(done["cbz"]) as z:
        names = z.namelist()
    assert names == ["0001.png", "0002.png", "0003.png", "0004.png", "ComicInfo.xml"]
    assert "Chapter_0001.cbz" in done["cbz"] and "WebToon" in done["cbz"]
    assert not (tmp_path / "out" / ".work" / str(ch["id"])).exists()


def test_flaky_pages_are_retried_after_a_reload_only(tmp_path):
    store = make_store(tmp_path)
    add(store)
    ch = got(store.claim_next())
    reader = FakeReader(total=5, flaky={2: 1, 4: 2})  # page 4 needs two reloads
    state = worker(store, reader).run_chapter(ch, settings.load())
    assert state == "done"
    # pass 1 reads all 5, pass 2 only the two failures, pass 3 only page 4
    assert reader.captured == [1, 2, 3, 4, 5, 2, 4, 4]


def test_blank_or_missing_pages_block_the_cbz_and_requeue(tmp_path):
    store = make_store(tmp_path)
    add(store)
    settings.save({"page_passes": 2, "chapter_attempts": 3})
    ch = got(store.claim_next())
    state = worker(store, FakeReader(total=3, blank={3})).run_chapter(
        ch, settings.load()
    )
    assert state == "partial"
    row = got(store.chapter(ch["id"]))
    assert row["pages_ok"] == 2 and row["cbz"] == "" and row["next_try"] > time.time()
    assert "looks blank" in store.pages(ch["id"])[2]["reason"]
    assert not list((tmp_path / "out").rglob("*.cbz"))


def test_resume_keeps_saved_pages_after_a_crash(tmp_path):
    store = make_store(tmp_path)
    add(store)
    settings.save({"page_passes": 1})
    ch = got(store.claim_next())
    worker(store, FakeReader(total=4, flaky={3: 99, 4: 99})).run_chapter(
        ch, settings.load()
    )
    # the app restarts mid-way: the chapter is claimable again, pages 1-2 kept
    store._x("update chapters set state='running' where id=?", (ch["id"],))
    assert store.reset_running() == 1
    again = got(store.claim_next())
    assert again["id"] == ch["id"]
    reader = FakeReader(total=4)
    assert worker(store, reader).run_chapter(again, settings.load()) == "done"
    assert reader.captured == [3, 4]


def test_too_many_tries_marks_failed_and_retry_requeues(tmp_path):
    store = make_store(tmp_path)
    add(store)
    settings.save({"page_passes": 1, "chapter_attempts": 2})
    ch = got(store.claim_next())
    w = worker(store, FakeReader(total=2, flaky={1: 99}))
    assert w.run_chapter(ch, settings.load()) == "partial"
    assert w.run_chapter(got(store.chapter(ch["id"])), settings.load()) == "failed"
    assert store.retry_failed() == 1
    assert got(store.claim_next(now=time.time()))["id"] == ch["id"]


def test_retry_delay_grows_and_caps():
    assert retry_delay(1) == 300 and retry_delay(2) == 600
    assert retry_delay(30) == 6 * 3600


def test_names_and_paths(tmp_path):
    assert chapter_stem(12) == "Chapter_0012"
    assert chapter_stem(12.5) == "Chapter_0012.5"
    p = cbz_path(tmp_path, 'A/B: "C"', "", 3)
    assert p.parts[-3:] == ("A B C", "Unknown group", "Chapter_0003.cbz")


def test_cbz_is_written_atomically(tmp_path):
    f = tmp_path / "p.png"
    f.write_bytes(page_png(1))
    dest = tmp_path / "x" / "Chapter_0001.cbz"
    build_cbz(dest, [f], "S", "G", 1)
    assert dest.exists() and not dest.with_suffix(".cbz.part").exists()


# --- login cookies -----------------------------------------------------------------


def cookie_db(path, rows_):
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, name TEXT, value TEXT, "
        "host TEXT, path TEXT, expiry INTEGER, lastAccessed INTEGER, isSecure "
        "INTEGER, isHttpOnly INTEGER, sameSite INTEGER)"
    )
    con.executemany(
        "insert into moz_cookies (name,value,host,path,expiry,isSecure,isHttpOnly,sameSite) "
        "values (?,?,?,?,?,?,?,?)",
        rows_,
    )
    con.commit()
    con.close()


def test_cookies_for_the_site_only_and_unexpired(tmp_path):
    db = tmp_path / "cookies.sqlite"
    future = int(time.time()) + 3600
    cookie_db(
        db,
        [
            ("session", "s3cret", ".comix.to", "/", future, 1, 1, 1),
            ("old", "x", "comix.to", "/", 10, 0, 0, 0),
            ("cdn", "y", "img.comix.to", "/", future, 1, 0, 2),
            ("other", "z", "notcomix.to", "/", future, 0, 0, 0),
        ],
    )
    before = db.read_bytes()
    got = read_cookies("comix.to", db)
    assert [c["name"] for c in got] == ["session", "cdn"]
    assert got[0]["sameSite"] == "Lax" and got[0]["httpOnly"] is True
    assert db.read_bytes() == before  # the browser's own file is never changed
    s = summary("comix.to", db)
    assert s["cookies"] == 2 and "s3cret" not in str(s)


def test_no_browser_profile_means_no_cookies(tmp_path):
    assert read_cookies("comix.to", tmp_path / "missing.sqlite") == []


# --- comix.to parsing ---------------------------------------------------------------


def test_chapter_rows_from_the_list_dom():
    raw = [
        {"href": "/title/abc/1-chapter-12.5", "label": "Ch. 12.5", "group": "Asura"},
        {"href": "/title/abc/comments", "label": "x", "group": ""},
    ]
    got = comix_to.rows_from_dom(raw)
    assert got == [
        {
            "number": 12.5,
            "group": "Asura",
            "url": "https://comix.to/title/abc/1-chapter-12.5",
            "label": "Ch. 12.5",
        }
    ]


def test_library_links_are_unique_series():
    raw = [
        {"href": "/title/a1-one", "text": "One"},
        {"href": "/title/a1-one?x=1", "text": "dup"},
        {"href": "/title/a1-one/99-chapter-1", "text": "a chapter"},
        {"href": "/title/b2-two", "text": "Two"},
    ]
    assert comix_to.title_links(raw) == [
        {"url": "https://comix.to/title/a1-one", "title": "One"},
        {"url": "https://comix.to/title/b2-two", "title": "Two"},
    ]


def test_source_registry_finds_comix():
    assert find_for_url(URL) == "comix"
    assert find_for_url("https://example.com/x") is None


def test_leftover_browsers_only_of_this_instance_are_stopped(tmp_path):
    def proc(pid, *args):
        d = tmp_path / "proc" / str(pid)
        d.mkdir(parents=True)
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in args))

    proc(11, "chrome", "--headless=new", "--user-data-dir=/h/.var/comix-fetch-aaaa-0")
    proc(12, "chrome", "--user-data-dir=/h/.var/comix-fetch-bbbb-0")  # another Comix
    proc(13, "chrome", "--user-data-dir=/h/.var/pf-mangafetch")
    proc(14, "python", "grep", "comix-fetch-aaaa-")
    killed = []
    n = stop_stray_browsers(
        "comix-fetch-aaaa-", tmp_path / "proc", kill=lambda pid, sig: killed.append(pid)
    )
    assert n == 1 and killed == [11]


def test_worker_tags_browsers_by_database(tmp_path):
    a = worker(Store(tmp_path / "a.db"), FakeReader())
    b = worker(Store(tmp_path / "b.db"), FakeReader())
    assert a.tag != b.tag and a.mark == f"comix-fetch-{a.tag}-"


# --- paging through comix.to lists (saved pages from the real site, 2026-09-25) ------

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_page(name):
    return comix_to.parse_page((FIXTURES / f"{name}.html").read_text())


def test_page_address_starts_at_one_whatever_page_the_link_is_on():
    link = "https://comix.to/user?tab=titles&page=2"
    assert comix_to.page_url(link, 1) == "https://comix.to/user?tab=titles"
    assert comix_to.page_url(link, 2) == "https://comix.to/user?tab=titles&page=2"
    assert comix_to.page_url(link, 3) == "https://comix.to/user?tab=titles&page=3"
    path_style = "https://comix.to/library/page/3#top"
    assert comix_to.page_url(path_style, 1) == "https://comix.to/library"
    assert comix_to.page_url(path_style, 2) == "https://comix.to/library/page/2"


def test_library_page_fixture_parses():
    page = fixture_page("library_page1")
    assert len(page["links"]) == 30
    assert page["links"][0] == {
        "url": "https://comix.to/title/y5nn-smoking-behind-the-supermarket-with-you",
        "title": "Smoking Behind the Supermarket with You",
    }
    assert page["last_page"] == 5
    assert fixture_page("library_past_end")["links"] == []


def test_series_page_fixture_rows_count_and_unnamed_groups():
    page = fixture_page("series_page1")
    assert page["title"] == "The Fragrant Flower Blooms With Dignity"
    assert page["total"] == 841 and page["last_page"] == 8
    rows = page["rows"]
    assert len(rows) == 20
    by_url = {r["url"].rsplit("/", 1)[1]: r for r in rows}
    assert by_url["11387886-chapter-203"]["group"] == "DarkQueen2"
    assert by_url["11387886-chapter-203"]["label"] == "Ch.203"
    assert by_url["11350909-chapter-202"]["group"] == "Unknown group"
    assert by_url["11159658-chapter-197"]["group"] == "HeavenlyDEMON (uploader)"
    assert all(r["group"] for r in rows)


def pages_from(table):
    """A fake browser: url -> list of pages to hand out, one per load."""
    calls = []

    def fetch(url, attempt):
        calls.append(url)
        queue = table.get(url, [])
        return queue.pop(0) if len(queue) > 1 else (queue[0] if queue else {})

    return fetch, calls


def test_library_walk_gets_every_page_from_a_page_two_link():
    lib = "https://comix.to/user?tab=titles"
    fetch, calls = pages_from(
        {
            lib: [fixture_page("library_page1")],
            lib + "&page=2": [fixture_page("library_page2")],
            lib + "&page=3": [fixture_page("library_past_end")],
        }
    )
    got = comix_to.list_library(lib + "&page=2", [], lambda m: None, fetch=fetch)
    assert len(got) == 60 and len({s["url"] for s in got}) == 60
    assert calls[0] == lib  # the page without "page" in it comes first


def test_a_page_that_fails_to_load_is_retried_not_the_end():
    base = "https://comix.to/title/abc-x"

    def page(first, total=60):
        rows = [
            {"number": n, "group": "G", "url": f"{base}/{n}-chapter-{n}", "label": ""}
            for n in range(first, first + 20)
        ]
        return {"title": "X", "rows": rows, "links": [], "total": total}

    error_page = {"title": "Web server is returning an unknown error", "rows": []}
    fetch, calls = pages_from(
        {
            base: [error_page, page(1)],
            base + "?page=2": [error_page, error_page, page(21)],
            base + "?page=3": [page(41)],
        }
    )
    info = comix_to.list_series(base, [], lambda m: None, fetch=fetch)
    assert info["title"] == "X"
    assert len(info["rows"]) == 60


def test_a_page_that_never_loads_is_skipped_when_more_pages_follow():
    base = "https://comix.to/title/abc-x"

    def page(first):
        rows = [
            {"number": n, "group": "G", "url": f"{base}/{n}-chapter-{n}", "label": ""}
            for n in range(first, first + 20)
        ]
        return {"title": "X", "rows": rows, "links": [], "total": 60}

    fetch, _ = pages_from({base: [page(1)], base + "?page=3": [page(41)]})
    info = comix_to.list_series(base, [], lambda m: None, fetch=fetch)
    assert len(info["rows"]) == 40


def test_blank_groups_get_a_name_old_ones_too(tmp_path):
    db = tmp_path / "c.db"
    store = Store(db)
    sid = store.save_series(URL, "S", "comix", [], "pending", [])
    raw = sqlite3.connect(db)
    raw.execute(
        "insert into chapters (series_id, number, grp, url, state, updated) "
        "values (?, 1, '', ?, 'skipped', 0)",
        (sid, URL + "/1-chapter-1"),
    )
    raw.commit()
    store = Store(db)  # reopening renames rows saved before names were given
    assert [c["grp"] for c in store.chapters(sid)] == [UNKNOWN_GROUP]
    store.save_series(
        URL,
        "S",
        "comix",
        [{"number": 2, "group": "", "url": URL + "/2-chapter-2"}],
        "one",
        [UNKNOWN_GROUP],
    )
    assert {c["grp"] for c in store.chapters(sid)} == {UNKNOWN_GROUP}
    assert store.apply_choice(sid, "one", [UNKNOWN_GROUP]) == 2


def test_library_sync_adds_new_and_relists_series_still_waiting(tmp_path):
    from types import SimpleNamespace

    from comix import library

    store = Store(tmp_path / "c.db")
    a, b, c = (f"https://comix.to/title/{x}-s" for x in "abc")
    store.save_series(a, "A", "comix", [], "pending", [], from_library=True)
    store.save_series(b, "B", "comix", [], "all", [])  # groups already picked
    listed = []

    def list_series(url, cookies, say):
        listed.append(url)
        return {
            "title": url[-3:],
            "rows": [{"number": 1, "group": "G", "url": url + "/1-chapter-1"}],
        }

    src = SimpleNamespace(
        list_library=lambda link, cookies, say: [
            {"url": u, "title": ""} for u in (a, b, c)
        ],
        list_series=list_series,
    )
    got = library.sync(store, src, "comix", "https://comix.to/user", [], lambda m: None)  # type: ignore[arg-type]
    assert got == {"found": 3, "added": 1, "relisted": 1}
    assert listed == [a, c]
    assert {s["url"]: s["listed"] for s in store.series()} == {a: 1, b: 0, c: 1}
