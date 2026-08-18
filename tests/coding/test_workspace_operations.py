from __future__ import annotations

from pathlib import Path

import pytest

from loushang.coding.workspace_operations import CodingWorkspaceOperations
from loushang.harness.authorization import EffectiveExecutionProfile
from loushang.harness.workspace.operations import LOCAL_TOOL_OPERATIONS


def test_coding_workspace_operations_reject_paths_outside_the_admitted_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    operations = CodingWorkspaceOperations(
        root=root,
        operations=LOCAL_TOOL_OPERATIONS,
        execution_profile=EffectiveExecutionProfile(
            readable_roots=(root,),
            writable_roots=(root,),
        ),
    )

    with pytest.raises(PermissionError, match="outside the admitted root"):
        operations.read_bytes(outside)


def test_coding_workspace_operations_enforce_read_only_admission(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    target = root / "notes.txt"
    target.write_text("old", encoding="utf-8")
    operations = CodingWorkspaceOperations(
        root=root,
        operations=LOCAL_TOOL_OPERATIONS,
        execution_profile=EffectiveExecutionProfile(readable_roots=(root,)),
    )

    assert operations.read_bytes(target) == b"old"
    with pytest.raises(PermissionError, match="outside the admitted writable roots"):
        operations.write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "old"


def test_coding_workspace_operations_honor_narrowed_and_denied_roots(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    writable = root / "generated"
    denied = root / "private"
    writable.mkdir(parents=True)
    denied.mkdir()
    operations = CodingWorkspaceOperations(
        root=root,
        operations=LOCAL_TOOL_OPERATIONS,
        execution_profile=EffectiveExecutionProfile(
            readable_roots=(root,),
            writable_roots=(writable,),
            denied_roots=(denied,),
        ),
    )

    operations.write_text(writable / "result.txt", "ok")
    with pytest.raises(PermissionError, match="writable roots"):
        operations.write_text(root / "source.txt", "no")
    with pytest.raises(PermissionError, match="denied"):
        operations.read_bytes(denied / "secret.txt")
