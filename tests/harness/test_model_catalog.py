from __future__ import annotations

from pathlib import Path

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
