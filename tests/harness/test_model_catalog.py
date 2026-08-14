from __future__ import annotations

from pathlib import Path

from loushang.ai.model.domain import Model, Provider
from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
from loushang.harness.model_catalog import ModelCatalog


def test_model_catalog_reloads_only_when_project_layer_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    catalog = ModelCatalog()
    calls: list[tuple[Path | None, Path | None]] = []
    monkeypatch.setattr(
        catalog,
        "reload",
        lambda *, user_dir=None, project_dir=None: calls.append(
            (user_dir, project_dir)
        ),
    )
    user_dir = tmp_path / "user-models"
    user_dir.mkdir()
    project_dir = tmp_path / "project-models"

    assert catalog.reload_if_project_layer(
        user_dir=user_dir,
        project_dir=project_dir,
    ) is False
    assert calls == []

    project_dir.mkdir()

    assert catalog.reload_if_project_layer(
        user_dir=user_dir,
        project_dir=project_dir,
    ) is True
    assert calls == [(user_dir, project_dir)]


def test_model_catalog_registration_compatibility_baseline() -> None:
    catalog = ModelCatalog(AiModelRegistry())
    first_model = Model(
        id="shared",
        provider="vendor",
        endpoint="default",
        api="custom",
        name="First model",
    )
    replacement_model = Model(
        id="shared",
        provider="vendor",
        endpoint="default",
        api="custom",
        name="Replacement model",
    )

    assert catalog.register_model(first_model) is None
    assert catalog.register_model(replacement_model) is None
    assert len(catalog.ai_registry.list_models()) == 1
    assert catalog.ai_registry.get_model("vendor", "default", "shared").name == (
        "Replacement model"
    )

    first_provider = Provider(id="provider", name="First provider")
    replacement_provider = Provider(id="provider", name="Replacement provider")
    assert catalog.register_provider(first_provider) is None
    assert catalog.register_provider(replacement_provider) is None
    registered_provider = catalog.ai_registry.get_provider("provider")
    assert registered_provider is not None
    assert registered_provider.name == "Replacement provider"

    assert catalog.unregister_provider("missing") is None
    assert catalog.unregister_provider("provider") is None
    assert catalog.ai_registry.get_provider("provider") is None
