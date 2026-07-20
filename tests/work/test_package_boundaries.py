from __future__ import annotations

from pathlib import Path


def test_work_package_does_not_own_coding_work_shell_implementation() -> None:
    text = Path("src/loushang/work/coding.py").read_text(encoding="utf-8")

    assert "class CodingWorkShell" not in text
    assert "SubmitCodingTurn" not in text


def test_work_standard_projection_does_not_depend_on_coding() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/loushang/work").glob("*.py")
        if path.name != "coding.py"
    )

    assert "loushang.coding" not in sources


def test_work_runtime_is_product_neutral_and_harness_does_not_import_work() -> None:
    work_runtime = Path("src/loushang/work/runtime.py").read_text(encoding="utf-8")
    coding_shell = Path("src/loushang/coding/work_shell.py").read_text(
        encoding="utf-8"
    )
    coding_executor = Path("src/loushang/coding/work_executor.py").read_text(
        encoding="utf-8"
    )
    harness_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/loushang/harness").rglob("*.py")
    )

    assert "loushang.coding" not in work_runtime
    assert "loushang.harness" not in work_runtime
    assert "loushang.agent" not in work_runtime
    assert "class WorkRuntime" in work_runtime
    assert "WorkRunStarted" in work_runtime
    assert "WorkRunCompleted" in work_runtime

    assert "WorkRunStarted" not in coding_shell
    assert "WorkRunCompleted" not in coding_shell
    assert "event_log.append" not in coding_shell
    assert "WorkRunStarted" not in coding_executor
    assert "WorkRunCompleted" not in coding_executor

    assert "loushang.work" not in harness_source
    assert not Path("src/loushang/harness/work").exists()


def test_channel_adapter_delegates_operation_lifecycle_to_work_runtime() -> None:
    source = Path("src/loushang/coding/mode/channel_mode.py").read_text(
        encoding="utf-8"
    )

    assert "WorkRuntime" in source
    assert "self._session.prompt(" not in source
    assert "self._session.abort(" not in source
    assert "self._active_operation_id" not in source
    assert "self._tasks" not in source
