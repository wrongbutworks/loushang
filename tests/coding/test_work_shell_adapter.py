from __future__ import annotations


def test_work_coding_compat_module_exposes_coding_owned_entrypoint() -> None:
    from loushang.coding.work_shell import CodingWorkShell
    from loushang.work.coding import CodingWorkShell as CompatCodingWorkShell

    assert CodingWorkShell is CompatCodingWorkShell
    assert CodingWorkShell.__module__ == "loushang.coding.work_shell"
