from __future__ import annotations

import importlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from loushang.harness.journal.jsonl import LockMode, journal_file_lock


@contextmanager
def session_file_lock(path: Path, mode: LockMode) -> Iterator[None]:
    with journal_file_lock(
        path,
        mode,
        is_windows=_is_windows,
        load_fcntl=_load_fcntl,
        load_msvcrt=_load_msvcrt,
    ):
        yield


def _is_windows() -> bool:
    return os.name == "nt"


def _load_fcntl() -> Any:
    return importlib.import_module("fcntl")


def _load_msvcrt() -> Any:
    return importlib.import_module("msvcrt")


__all__ = ["LockMode", "session_file_lock"]
