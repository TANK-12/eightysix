"""Finding the library again after its folder moved (A25: AN3 -> laptop)."""

import json

import pytest

import location
import store


def library(path, subjects):
    (path / "subjects").mkdir(parents=True)
    for i in range(subjects):
        (path / "subjects" / f"s{i}").mkdir()
    (path / "index.json").write_text("{}")
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(location, "CHOICE_FILE", tmp_path / "cfg" / "location.json")
    monkeypatch.setattr(store, "USB_ROOT", tmp_path / "usb" / "DossierData")
    monkeypatch.setattr(store, "LOCAL_ROOT", tmp_path / "DossierData-local")
    monkeypatch.setattr(store, "_resolved", None)
    return tmp_path


def test_finds_library_shaped_folders_biggest_first(home):
    library(home / "AN3-backup" / "DossierData", 3)
    library(home / "DossierData-local", 0)
    (home / "notes" / "subjects").mkdir(parents=True)  # no index.json: not one
    library(home / ".cache" / "old", 9)  # hidden folders are not searched
    library(home / "deep" / "a" / "b" / "c" / "d" / "e" / "DossierData", 1)
    found = location.find([home])
    assert [(f["path"], f["subjects"]) for f in found] == [
        (str(home / "AN3-backup" / "DossierData"), 3),
        (str(home / "DossierData-local"), 0),
    ]


def test_a_chosen_folder_wins_over_the_fallback_and_is_remembered(home):
    moved = library(home / "AN3-backup" / "DossierData", 2)
    assert store.data_root().path == home / "DossierData-local"
    location.choose(moved)
    assert json.loads(location.CHOICE_FILE.read_text()) == {"path": str(moved)}
    root = store.data_root(refresh=True)
    assert root.path == moved and not root.on_usb
    assert root.detail.startswith("The library folder you chose")


def test_only_a_library_shaped_folder_can_be_chosen(home):
    (home / "empty").mkdir()
    with pytest.raises(ValueError):
        location.choose(home / "empty")
    with pytest.raises(ValueError):
        location.choose(home / "missing")


def test_a_chosen_folder_that_went_away_falls_back(home):
    moved = library(home / "gone" / "DossierData", 1)
    location.choose(moved)
    for p in sorted(moved.rglob("*"), reverse=True):
        p.rmdir() if p.is_dir() else p.unlink()
    moved.rmdir()
    (home / "gone").rmdir()
    root = store.data_root(refresh=True)
    assert root.path == home / "DossierData-local"
    assert "not found" in root.detail
