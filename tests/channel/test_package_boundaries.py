from __future__ import annotations

from pathlib import Path


def test_channel_package_does_not_import_product_or_agent_runtime_layers() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/loushang/channel").glob("*.py")
        if path.name != "__pycache__"
    )

    assert "loushang.agent" not in source
    assert "loushang.coding" not in source
    assert "loushang.method" not in source
    assert "loushang.tui" not in source


def test_channel_consumes_only_the_runtime_event_view_from_harness() -> None:
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in Path("src/loushang/channel").glob("*.py")
        if path.name != "__pycache__"
    }

    harness_imports = {
        name for name, source in sources.items() if "loushang.harness" in source
    }

    assert harness_imports == {"json_codec.py", "types.py"}
    assert all(
        "loushang.harness.events.projection" in sources[name]
        for name in harness_imports
    )
