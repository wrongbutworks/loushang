from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import TypeVar

from loushang.harness.workspace.operations import OperationResult, resolve_operation
from loushang.harness.workspace.paths import canonicalize_workspace_path

T = TypeVar("T")


@dataclass
class _QueueEntry:
    lock: asyncio.Lock
    holders: int = 0


_registry_lock = Lock()
_mutation_locks: dict[str, _QueueEntry] = {}


def _canonical_queue_key(path: str | Path) -> str:
    if isinstance(path, str) and not path:
        raise TypeError("path must be a non-empty string")
    if not isinstance(path, str | Path):
        raise TypeError("path must be a string or Path")
    return str(canonicalize_workspace_path(path))


def _acquire_queue_entry(canonical_path: str) -> _QueueEntry:
    with _registry_lock:
        entry = _mutation_locks.get(canonical_path)
        if entry is None:
            entry = _QueueEntry(lock=asyncio.Lock())
            _mutation_locks[canonical_path] = entry
        entry.holders += 1
        return entry


def _release_queue_entry(canonical_path: str, entry: _QueueEntry) -> None:
    with _registry_lock:
        current = _mutation_locks.get(canonical_path)
        if current is not entry:
            return
        entry.holders -= 1
        if entry.holders == 0:
            del _mutation_locks[canonical_path]


@asynccontextmanager
async def with_file_mutation_queue(path: str | Path) -> AsyncIterator[None]:
    canonical_path = _canonical_queue_key(path)
    entry = _acquire_queue_entry(canonical_path)
    try:
        async with entry.lock:
            yield
    finally:
        _release_queue_entry(canonical_path, entry)


async def run_with_file_mutation_queue(
    path: str | Path,
    fn: Callable[[], OperationResult[T]],
) -> T:
    async with with_file_mutation_queue(path):
        return await resolve_operation(fn())
