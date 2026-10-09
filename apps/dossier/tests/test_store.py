"""Where the library lives. Getting this wrong splits it in two silently."""

import concurrent.futures as cf

import store


def test_the_write_probe_survives_concurrent_use(tmp_path, monkeypatch):
    """The original probe used one shared filename. With several subjects being
    researched at once, one thread unlinked the file another had just written,
    the second thread's unlink raised, and a perfectly good drive was declared
    unwritable - sending some subjects to the fallback directory and, at worst,
    raising outright."""
    target = tmp_path / "data"

    def probe(_):
        return store._usable(target)

    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(probe, range(200)))
    assert all(results), "a writable directory was reported unwritable under load"


def test_the_probe_leaves_nothing_behind(tmp_path):
    target = tmp_path / "data"
    assert store._usable(target)
    assert not list(target.glob(".write-probe*"))


def test_an_unwritable_location_is_reported_as_such(tmp_path):
    missing_parent = tmp_path / "nope" / "deeper" / "data"
    assert not store._usable(missing_parent)


def test_the_root_is_resolved_once_and_reused(monkeypatch, tmp_path):
    """It used to re-decide on every call, so one transient failure could put a
    single subject's files somewhere else while everything around it was fine."""
    monkeypatch.setattr(store, "_resolved", None)
    monkeypatch.setattr(store, "USB_ROOT", tmp_path / "usb" / "Data")
    monkeypatch.setattr(store, "LOCAL_ROOT", tmp_path / "local")
    (tmp_path / "usb").mkdir()

    first = store.data_root()
    calls = []
    original = store._usable

    def counting(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(store, "_usable", counting)
    for _ in range(20):
        assert store.data_root().path == first.path
    assert not calls, "the root was re-probed after it had been decided"
    monkeypatch.setattr(store, "_resolved", None)


def test_refresh_re_checks_deliberately(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_resolved", None)
    monkeypatch.setattr(store, "USB_ROOT", tmp_path / "usb" / "Data")
    monkeypatch.setattr(store, "LOCAL_ROOT", tmp_path / "local")
    store.data_root()
    seen = []
    original = store._usable
    monkeypatch.setattr(store, "_usable", lambda p: seen.append(p) or original(p))
    store.data_root(refresh=True)
    assert seen, "refresh should re-probe"
    monkeypatch.setattr(store, "_resolved", None)
