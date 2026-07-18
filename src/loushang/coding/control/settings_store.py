from __future__ import annotations

from pathlib import Path
from typing import Any

from loushang.harness.config import JsonConfigStore

_STORE = JsonConfigStore()


def default_global_settings_path() -> Path:
    return Path.home() / ".loushang" / "coding" / "settings.json"


def default_project_settings_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".loushang" / "settings.json"


def load_settings_patch(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return dict(_STORE.load(Path(path)))


def save_settings_patch(path: str | Path | None, patch: dict[str, Any]) -> None:
    if path is None:
        raise ValueError("A settings path is required for persisted updates.")
    _STORE.save(Path(path), patch)
