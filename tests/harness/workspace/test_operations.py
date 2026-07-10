from __future__ import annotations

import asyncio


def test_resolve_operation_accepts_sync_and_async_results() -> None:
    from loushang.harness.workspace.operations import resolve_operation

    async def async_value() -> str:
        return "async"

    async def run() -> tuple[str, str]:
        return await resolve_operation("sync"), await resolve_operation(async_value())

    assert asyncio.run(run()) == ("sync", "async")


def test_local_tool_operations_cover_filesystem_primitives(tmp_path) -> None:
    from loushang.harness.workspace.operations import LocalToolOperations

    operations = LocalToolOperations()
    root = tmp_path / "workspace"
    nested = root / "nested"
    first = root / "first.txt"
    second = nested / "second.txt"

    operations.mkdir(nested, parents=True, exist_ok=True)
    operations.write_text(first, "first\n")
    operations.write_text(second, "second\n", newline="")

    assert operations.exists(root)
    assert operations.is_dir(root)
    assert operations.is_file(first)
    assert operations.read_bytes(first) == b"first\n"
    assert operations.read_text(second, newline="") == "second\n"
    assert sorted(path.name for path in operations.iterdir(root)) == ["first.txt", "nested"]
    assert list(operations.walk_files(root)) == [first, second]


def test_default_local_operations_use_harness_class() -> None:
    from loushang.harness.workspace.operations import (
        LOCAL_TOOL_OPERATIONS,
        LocalToolOperations,
    )

    assert type(LOCAL_TOOL_OPERATIONS) is LocalToolOperations
