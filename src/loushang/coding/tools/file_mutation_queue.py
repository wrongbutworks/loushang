from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import Lock
from typing import TypeVar

from .path_utils import canonicalize_tool_path
from .runtime import MaybeAwaitable, resolve_maybe_awaitable


T = TypeVar("T")


@dataclass
class _QueueEntry:
    lock: asyncio.Lock
    holders: int = 0


_registry_lock = Lock()
_mutation_locks: dict[str, _QueueEntry] = {}


def _canonical_queue_key(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise TypeError("path must be a non-empty string")
    return canonicalize_tool_path(path)


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
async def with_file_mutation_queue(path: str) -> AsyncIterator[None]:
    canonical_path = _canonical_queue_key(path)
    entry = _acquire_queue_entry(canonical_path)
    try:
        async with entry.lock:
            yield
    finally:
        _release_queue_entry(canonical_path, entry)


async def run_with_file_mutation_queue(path: str, fn: Callable[[], MaybeAwaitable[T]]) -> T:
    async with with_file_mutation_queue(path):
        return await resolve_maybe_awaitable(fn())


withFileMutationQueue = run_with_file_mutation_queue
