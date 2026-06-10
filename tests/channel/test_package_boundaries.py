from __future__ import annotations

from pathlib import Path


def test_channel_package_does_not_import_product_or_runtime_layers() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/loushang/channel").glob("*.py")
        if path.name != "__pycache__"
    )

    assert "loushang.agent" not in source
    assert "loushang.coding" not in source
    assert "loushang.method" not in source
    assert "loushang.tui" not in source
