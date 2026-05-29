from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_global_settings_path() -> Path:
    return Path.home() / ".loushang" / "coding" / "settings.json"


def default_project_settings_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".loushang" / "settings.json"


def load_settings_patch(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}

    settings_path = Path(path)
    if not settings_path.exists():
        return {}

    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Settings payload must be a JSON object: {settings_path}")
    return dict(payload)


def save_settings_patch(path: str | Path | None, patch: dict[str, Any]) -> None:
    if path is None:
        raise ValueError("A settings path is required for persisted updates.")

    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = settings_path.with_suffix(settings_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(patch, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(settings_path)
