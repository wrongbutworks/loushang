from __future__ import annotations

from pathlib import Path


def test_work_package_has_no_coding_compatibility_module() -> None:
    assert not Path("src/loushang/work/coding.py").exists()


def test_work_standard_projection_does_not_depend_on_coding() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/loushang/work").glob("*.py")
    )

    assert "loushang.coding" not in sources


def test_work_runtime_is_product_neutral_and_harness_does_not_import_work() -> None:
    work_runtime = Path("src/loushang/work/runtime.py").read_text(encoding="utf-8")
    session_runtime = Path("src/loushang/work/session.py").read_text(
        encoding="utf-8"
    )
    coding_binding = Path("src/loushang/coding/domain/work.py").read_text(
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

    assert "loushang.coding" not in session_runtime
    assert "loushang.harness" not in session_runtime
    assert "loushang.agent" not in session_runtime
    assert "class SessionWorkRuntime" in session_runtime
    assert "WorkRuntime(" in session_runtime
    assert "class CodingWorkRuntime" not in coding_binding
    assert "class CodingWorkShell" not in coding_binding
    assert "SessionWorkProfile(" in coding_binding

    assert "loushang.work" not in harness_source
    assert not Path("src/loushang/harness/work").exists()


def test_channel_adapter_delegates_operation_lifecycle_to_work_runtime() -> None:
    source = Path("src/loushang/coding/mode/channel_mode.py").read_text(
        encoding="utf-8"
    )

    assert "SessionWorkRuntime" in source
    assert "self._session.prompt(" not in source
    assert "self._session.abort(" not in source
    assert "self._active_operation_id" not in source
    assert "self._tasks" not in source
