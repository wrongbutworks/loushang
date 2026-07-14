from __future__ import annotations

import asyncio

from loushang.harness.resources.watcher import (
    ResourceChangeWatcher,
    snapshot_resource_paths,
)


def test_resource_change_watcher_establishes_baseline_and_awaits_callback(
    tmp_path,
) -> None:
    resources = tmp_path / "resources"
    resources.mkdir()
    prompt = resources / "review.md"
    prompt.write_text("first", encoding="utf-8")
    calls: list[str] = []

    async def changed() -> None:
        await asyncio.sleep(0)
        calls.append("changed")

    watcher = ResourceChangeWatcher(
        get_paths=lambda: [resources],
        on_change=changed,
    )

    assert asyncio.run(watcher.poll_once()) is False
    prompt.write_text("second", encoding="utf-8")
    assert asyncio.run(watcher.poll_once()) is True
    assert asyncio.run(watcher.poll_once()) is False
    assert calls == ["changed"]


def test_resource_snapshot_ignores_runtime_and_vcs_directories(tmp_path) -> None:
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "review.md").write_text("review", encoding="utf-8")
    ignored = resources / "node_modules"
    ignored.mkdir()
    (ignored / "generated.js").write_text("generated", encoding="utf-8")

    snapshot = snapshot_resource_paths([resources])

    assert any(path.endswith("review.md") for path in snapshot)
    assert not any("node_modules" in path for path in snapshot)
