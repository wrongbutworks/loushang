from __future__ import annotations

import importlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

LockMode = Literal["exclusive", "shared"]


@contextmanager
def session_file_lock(path: Path, mode: LockMode) -> Iterator[None]:
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        _prepare_lock_byte(handle)
        if _is_windows():
            msvcrt = _load_msvcrt()
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        fcntl = _load_fcntl()
        operation = fcntl.LOCK_EX if mode == "exclusive" else fcntl.LOCK_SH
        fcntl.flock(handle.fileno(), operation)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _prepare_lock_byte(handle) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)


def _is_windows() -> bool:
    return os.name == "nt"


def _load_fcntl():
    return importlib.import_module("fcntl")


def _load_msvcrt():
    return importlib.import_module("msvcrt")


__all__ = ["LockMode", "session_file_lock"]
