"""The model list shows only models that are really there (Emerson,
2026-09-27: NovelForge's model switch listed models whose folders are empty).

A Jan model counts when its folder holds weights, or its model.yml points at
weights that exist (Forge's `-long` entries point at the base model's file).
The old hardcoded fallback names are never listed."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novelforge import catalog  # noqa: E402


class FakeJan:
    def __init__(self, ids):
        self.ids = ids

    def list_models(self):
        return list(self.ids)


def jan_tree(tmp_path: Path) -> Path:
    models = tmp_path / "data" / "llamacpp" / "models"
    (models / "Real-4B").mkdir(parents=True)
    (models / "Real-4B" / "model.gguf").write_bytes(b"GGUF")
    (models / "Real-4B" / "model.yml").write_text("ctx_size: 4096\n")
    (models / "Real-4B-long").mkdir()
    (models / "Real-4B-long" / "model.yml").write_text(
        "model_path: llamacpp/models/Real-4B/model.gguf\nctx_size: 131072\n"
    )
    (models / "embed-mini").mkdir()
    (models / "embed-mini" / "model.gguf").write_bytes(b"GGUF")
    (models / "embed-mini" / "model.yml").write_text("embedding: true\n")
    (models / "Empty-9B").mkdir()
    (models / "Gone-2B").mkdir()
    (models / "Gone-2B" / "model.yml").write_text(
        "model_path: llamacpp/models/Gone-2B/model.gguf\n"
    )
    return models


def fresh(tmp_path: Path) -> catalog.Catalog:
    cat = catalog.Catalog()
    cat.registry = catalog.ModelRegistry(str(tmp_path / "known.json"))
    return cat


def test_only_models_with_weights_are_listed(tmp_path):
    models = jan_tree(tmp_path)
    cat = fresh(tmp_path)
    got = cat.refresh(FakeJan([]), str(models))
    assert sorted(got) == ["Real-4B", "Real-4B-long"]
    assert cat.scan_count == 2


def test_jan_ids_for_empty_folders_are_dropped_but_others_kept(tmp_path):
    models = jan_tree(tmp_path)
    cat = fresh(tmp_path)
    got = cat.refresh(
        FakeJan(["Real-4B", "Empty-9B", "Gone-2B", "remote-model"]), str(models)
    )
    assert "Empty-9B" not in got and "Gone-2B" not in got
    assert "remote-model" in got, "a model Jan serves from elsewhere still counts"


def test_no_hardcoded_fallback_names(tmp_path):
    cat = fresh(tmp_path)
    assert cat.models == []
    got = cat.refresh(FakeJan([]), str(tmp_path / "missing"))
    assert got == []
    assert not set(got) & set(catalog.FALLBACK_MODELS)


def test_the_long_context_entry_keeps_its_own_context_size(tmp_path):
    models = jan_tree(tmp_path)
    cat = fresh(tmp_path)
    cat.refresh(FakeJan([]), str(models))
    assert cat.ctx_size("Real-4B-long") == 131072
    assert cat.ctx_size("Real-4B") == 4096


def test_embedding_models_are_not_offered_for_writing(tmp_path):
    models = jan_tree(tmp_path)
    cat = fresh(tmp_path)
    assert "embed-mini" not in cat.refresh(
        FakeJan(["embed-mini", "Real-4B"]), str(models)
    )
