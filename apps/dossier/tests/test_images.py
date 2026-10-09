"""Pictures: what gets kept, what gets refused, and what is never re-fetched."""

import dossier
import store
from research import images
from sources.properties import IMAGES, image_url


class FakeResponse:
    def __init__(self, content=b"x", content_type="image/jpeg"):
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        pass


class FakeClient:
    """Stands in for httpx so the tests never touch the network."""

    def __init__(self, by_url=None, boom=False):
        self.by_url = by_url or {}
        self.boom = boom
        self.asked = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        self.asked.append(url)
        if self.boom:
            raise OSError("network down")
        return self.by_url.get(url, FakeResponse())


def hold(tmp_path, name, image_rows):
    slug = store.slugify(name)
    d = store.ensure_subject(slug, tmp_path)
    store.write_json(
        d / dossier.FILES["subject"],
        {"slug": slug, "name": name, "entity_type": "person", "depth": "quick"},
    )
    store.write_json(d / dossier.FILES["images"], image_rows)
    dossier.reindex(tmp_path)
    return slug


def ref(kind="portrait", commons_file="A Photo.jpg", stored=""):
    return {
        "kind": kind,
        "label": kind,
        "commons_file": commons_file,
        "url": image_url(commons_file),
        "credit": "Wikimedia Commons",
        "stored": stored,
    }


# --- turning a Commons filename into something fetchable --------------------


def test_a_commons_filename_becomes_a_width_limited_url():
    url = image_url("Angela Merkel 2019.jpg", width=640)
    assert "Special:FilePath/Angela_Merkel_2019.jpg" in url
    assert url.endswith("?width=640")


def test_awkward_characters_in_a_filename_are_escaped():
    url = image_url("Foo (bar), 50%.jpg")
    assert " " not in url and "(" not in url


def test_every_picture_kind_has_a_kind_and_a_label():
    assert all(len(v) == 2 and all(v) for v in IMAGES.values())
    assert "P18" in IMAGES, "the main portrait property was dropped"


# --- fetching ---------------------------------------------------------------


def test_a_picture_is_written_and_recorded(tmp_path, monkeypatch):
    slug = hold(tmp_path, "Someone", [ref()])
    monkeypatch.setattr(
        images.httpx,
        "Client",
        lambda **kw: FakeClient(
            {},
        ),
    )
    out = images.fetch_for(slug, tmp_path)

    assert out["fetched"] == 1
    stored = dossier.load(slug, tmp_path)["images"][0]["stored"]
    assert stored.startswith("images/portrait-")
    assert (store.subject_dir(slug, tmp_path) / stored).is_file()


def test_a_picture_already_on_disk_is_not_fetched_again(tmp_path, monkeypatch):
    slug = hold(tmp_path, "Someone", [ref()])
    client = FakeClient()
    monkeypatch.setattr(images.httpx, "Client", lambda **kw: client)
    images.fetch_for(slug, tmp_path)
    first = len(client.asked)

    images.fetch_for(slug, tmp_path)
    assert len(client.asked) == first, "it downloaded a file it already had"


def test_something_that_is_not_a_picture_is_refused(tmp_path, monkeypatch):
    """A redirect to an error page must not be written out as a .jpg."""
    row = ref()
    slug = hold(tmp_path, "Someone", [row])
    monkeypatch.setattr(
        images.httpx,
        "Client",
        lambda **kw: FakeClient({row["url"]: FakeResponse(b"<html>", "text/html")}),
    )
    out = images.fetch_for(slug, tmp_path)

    assert out["fetched"] == 0 and out["failed"] == 1
    assert not (store.subject_dir(slug, tmp_path) / "images").exists()


def test_an_enormous_file_is_left_as_a_link(tmp_path, monkeypatch):
    row = ref()
    slug = hold(tmp_path, "Someone", [row])
    huge = FakeResponse(b"x" * (images.MAX_BYTES + 1))
    monkeypatch.setattr(
        images.httpx, "Client", lambda **kw: FakeClient({row["url"]: huge})
    )
    out = images.fetch_for(slug, tmp_path)

    assert out["fetched"] == 0 and out["failed"] == 1
    assert dossier.load(slug, tmp_path)["images"][0]["stored"] == ""


def test_a_network_failure_leaves_the_reference_for_next_time(tmp_path, monkeypatch):
    slug = hold(tmp_path, "Someone", [ref()])
    monkeypatch.setattr(images.httpx, "Client", lambda **kw: FakeClient(boom=True))
    out = images.fetch_for(slug, tmp_path)

    assert out["failed"] == 1
    held = dossier.load(slug, tmp_path)["images"]
    assert len(held) == 1 and held[0]["stored"] == ""


def test_two_pictures_of_different_kinds_do_not_collide(tmp_path, monkeypatch):
    slug = hold(
        tmp_path,
        "A Country",
        [ref("flag", "Flag of X.svg"), ref("arms", "Arms of X.svg")],
    )
    monkeypatch.setattr(images.httpx, "Client", lambda **kw: FakeClient())
    images.fetch_for(slug, tmp_path)

    names = {i["stored"] for i in dossier.load(slug, tmp_path)["images"]}
    assert len(names) == 2


def test_a_subject_with_no_pictures_does_nothing(tmp_path):
    slug = hold(tmp_path, "Someone", [])
    assert images.fetch_for(slug, tmp_path)["fetched"] == 0


# --- the merge keeps what has already been downloaded -----------------------


def test_a_rerun_does_not_forget_where_a_picture_was_saved(tmp_path):
    """The reference arrives again on every pass. If the merge dropped the
    local path, every re-run would re-download the whole library."""
    slug = hold(tmp_path, "Someone", [ref(stored="images/portrait-abc.jpg")])
    result = {
        "slug": slug,
        "name": "Someone",
        "entity_type": "person",
        "identity": {},
        "context_terms": [],
        "updated": "now",
        "sources": [],
        "timeline": [],
        "quotes": [],
        "relations": [],
        "claims": [],
        "images": [ref()],
        "report": {"phase": "quick", "seconds": 1},
    }
    dossier.save(result, tmp_path)

    held = dossier.load(slug, tmp_path)["images"]
    assert len(held) == 1, "the same picture was stored twice"
    assert held[0]["stored"] == "images/portrait-abc.jpg"
