from __future__ import annotations


def test_coding_work_shell_adapter_exposes_coding_owned_entrypoint() -> None:
    from loushang.coding.work_shell import CodingWorkShell
    from loushang.work import CodingWorkShell as CompatCodingWorkShell

    assert CodingWorkShell is CompatCodingWorkShell
    assert CodingWorkShell.__module__ == "loushang.coding.work_shell"
