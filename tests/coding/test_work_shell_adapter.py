from __future__ import annotations

from pathlib import Path


def test_coding_binds_product_vocabulary_to_shared_session_work_runtime() -> None:
    from loushang.coding.domain.work import (
        CODING_WORK_PROFILE,
        create_coding_work_runtime,
    )
    from loushang.work.session import SessionWorkRuntime

    assert CODING_WORK_PROFILE.domain == "coding"
    assert CODING_WORK_PROFILE.operation_kind == "SubmitCodingTurn"
    assert create_coding_work_runtime.__module__ == "loushang.coding.domain.work"
    assert SessionWorkRuntime.__module__ == "loushang.work.session"
    assert not Path("src/loushang/coding/work_shell.py").exists()
    assert not Path("src/loushang/work/coding.py").exists()
