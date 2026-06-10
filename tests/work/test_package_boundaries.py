from __future__ import annotations

from pathlib import Path


def test_work_package_does_not_own_coding_work_shell_implementation() -> None:
    text = Path("src/loushang/work/coding.py").read_text(encoding="utf-8")

    assert "class CodingWorkShell" not in text
    assert "SubmitCodingTurn" not in text
