from __future__ import annotations


def test_coding_path_adapter_preserves_existing_input_policy(tmp_path, monkeypatch) -> None:
    from loushang.coding.tools.path_utils import (
        canonicalize_tool_path,
        expand_path,
        resolve_tool_path,
    )
    from loushang.harness.workspace.paths import canonicalize_workspace_path

    monkeypatch.setenv("HOME", str(tmp_path))

    assert expand_path("@file\u00a0name.txt") == "file name.txt"
    assert resolve_tool_path("~/notes.txt", cwd="/ignored") == (tmp_path / "notes.txt").resolve()
    assert canonicalize_tool_path(tmp_path / "todo.txt") == str(
        canonicalize_workspace_path(tmp_path / "todo.txt")
    )


def test_coding_mutation_queue_preserves_harness_owner_identity() -> None:
    import loushang.coding as coding
    import loushang.coding.tools as coding_tools
    from loushang.coding.tools import file_mutation_queue as coding_queue
    from loushang.harness.workspace import mutation_queue as harness_queue

    assert coding_queue.with_file_mutation_queue is harness_queue.with_file_mutation_queue
    assert coding_tools.with_file_mutation_queue is harness_queue.with_file_mutation_queue
    assert coding.with_file_mutation_queue is harness_queue.with_file_mutation_queue
    assert coding_queue.run_with_file_mutation_queue is harness_queue.run_with_file_mutation_queue
    assert coding_tools.run_with_file_mutation_queue is harness_queue.run_with_file_mutation_queue
    assert coding.run_with_file_mutation_queue is harness_queue.run_with_file_mutation_queue
    assert coding_queue._mutation_locks is harness_queue._mutation_locks
    assert coding_queue.withFileMutationQueue is harness_queue.run_with_file_mutation_queue
