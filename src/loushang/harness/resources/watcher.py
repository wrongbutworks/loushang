from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

ResourceWatchPathGetter: TypeAlias = Callable[[], Iterable[str | Path]]
ResourceWatchCallback: TypeAlias = Callable[[], object | Awaitable[object]]
ResourceSnapshot: TypeAlias = dict[str, tuple[int, int] | None]

_SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
}


@dataclass
class ResourceChangeWatcher:
    """Poll product-neutral resource roots and report snapshot changes."""

    get_paths: ResourceWatchPathGetter
    on_change: ResourceWatchCallback
    interval_seconds: float = 1.0
    _snapshot: ResourceSnapshot | None = None
    _task: asyncio.Task[None] | None = None
    _stopped: asyncio.Event | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def poll_once(self) -> bool:
        next_snapshot = snapshot_resource_paths(self.get_paths())
        if self._snapshot is None:
            self._snapshot = next_snapshot
            return False
        if next_snapshot == self._snapshot:
            return False
        self._snapshot = next_snapshot
        result = self.on_change()
        if inspect.isawaitable(result):
            await result
        return True

    def start(self, *, interval_seconds: float | None = None) -> None:
        if interval_seconds is not None:
            self.interval_seconds = interval_seconds
        if self.is_running:
            return
        self._stopped = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        stopped = self._stopped
        task = self._task
        if stopped is not None:
            stopped.set()
        if task is not None:
            await task
        self._task = None
        self._stopped = None

    async def _run_loop(self) -> None:
        stopped = self._stopped
        while stopped is not None and not stopped.is_set():
            await self.poll_once()
            try:
                await asyncio.wait_for(stopped.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue


def snapshot_resource_paths(paths: Iterable[str | Path]) -> ResourceSnapshot:
    snapshot: ResourceSnapshot = {}
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        _snapshot_path(path, snapshot)
    return snapshot


def _snapshot_path(path: Path, snapshot: ResourceSnapshot) -> None:
    key = path.resolve().as_posix() if path.exists() else path.expanduser().as_posix()
    try:
        stat = path.stat()
    except OSError:
        snapshot[key] = None
        return
    snapshot[key] = (stat.st_mtime_ns, stat.st_size)
    if not path.is_dir():
        return
    try:
        entries = sorted(path.iterdir(), key=lambda item: item.name)
    except OSError:
        return
    for entry in entries:
        if entry.is_dir() and entry.name in _SKIP_DIR_NAMES:
            continue
        _snapshot_path(entry, snapshot)


__all__ = ["ResourceChangeWatcher", "ResourceSnapshot", "snapshot_resource_paths"]
