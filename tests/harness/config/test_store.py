from __future__ import annotations

from pathlib import Path


def test_json_config_store_round_trip_and_atomic_cleanup(tmp_path: Path) -> None:
    from loushang.harness.config import JsonConfigStore

    store = JsonConfigStore()
    path = tmp_path / "nested" / "config.json"

    store.save(path, {"name": "配置", "enabled": True})

    assert store.load(path) == {"name": "配置", "enabled": True}
    assert not path.with_suffix(".json.tmp").exists()


def test_json_config_store_requires_object_payload(tmp_path: Path) -> None:
    import pytest

    from loushang.harness.config import JsonConfigStore

    path = tmp_path / "config.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        JsonConfigStore().load(path)
