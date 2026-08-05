"""Session-scoped lazy LSP runtime ownership and startup single-flight."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass

from loushang.coding.lsp.catalog import LspCatalog
from loushang.coding.lsp.client import LspClient
from loushang.coding.lsp.model import (
    LspProtocolError,
    LspServerKey,
    LspServerSelection,
)
from loushang.coding.lsp.ports import (
    AuthorizedProcessLauncher,
    ProcessHandle,
    ProcessLaunchRequest,
)


@dataclass(frozen=True, slots=True)
class LspRuntimeHandle:
    key: LspServerKey
    runtime_id: int
    client: LspClient


class LspServerSupervisor:
    """Own every LSP runtime created by one Coding capability binding."""

    def __init__(
        self,
        *,
        catalog: LspCatalog,
        launcher: AuthorizedProcessLauncher,
        baseline_environment: Mapping[str, str],
    ) -> None:
        self._catalog = catalog
        self._launcher = launcher
        self._baseline_environment = dict(baseline_environment)
        self._runtimes: dict[LspServerKey, LspRuntimeHandle] = {}
        self._starts: dict[LspServerKey, asyncio.Task[LspRuntimeHandle]] = {}
        self._lock = asyncio.Lock()
        self._next_runtime_id = 1
        self._disposed = False
        self._dispose_task: asyncio.Task[None] | None = None

    async def ensure_runtime(
        self,
        selection: LspServerSelection,
        *,
        correlation_id: str,
        signal: object | None = None,
    ) -> LspRuntimeHandle:
        key = LspServerKey(selection.definition_id, selection.workspace_root)
        async with self._lock:
            if self._disposed:
                raise LspProtocolError("LSP supervisor is disposed")
            current = self._runtimes.get(key)
            if current is not None and not current.client.is_closed:
                return current
            if current is not None:
                self._runtimes.pop(key, None)
            task = self._starts.get(key)
            if task is None:
                runtime_id = self._next_runtime_id
                self._next_runtime_id += 1
                task = asyncio.create_task(
                    self._start_runtime(
                        key,
                        runtime_id=runtime_id,
                        correlation_id=correlation_id,
                        signal=signal,
                    ),
                    name=f"coding-lsp-start:{selection.definition_id}",
                )
                self._starts[key] = task

        try:
            return await asyncio.shield(task)
        finally:
            if task.done():
                async with self._lock:
                    if self._starts.get(key) is task:
                        self._starts.pop(key, None)

    async def stop(self, key: LspServerKey) -> None:
        async with self._lock:
            runtime = self._runtimes.pop(key, None)
            start = self._starts.pop(key, None)
        if start is not None:
            start.cancel()
            await asyncio.gather(start, return_exceptions=True)
        if runtime is not None:
            await runtime.client.shutdown()

    async def dispose(self) -> None:
        async with self._lock:
            task = self._dispose_task
            if task is None:
                self._disposed = True
                task = asyncio.create_task(
                    self._dispose_all(),
                    name="coding-lsp-dispose",
                )
                self._dispose_task = task
        await asyncio.shield(task)

    async def _dispose_all(self) -> None:
        async with self._lock:
            starts = tuple(self._starts.values())
            runtimes = tuple(self._runtimes.values())
            self._starts.clear()
            self._runtimes.clear()
        for task in starts:
            task.cancel()
        if starts:
            await asyncio.gather(*starts, return_exceptions=True)
        if runtimes:
            await asyncio.gather(
                *(runtime.client.shutdown() for runtime in runtimes),
                return_exceptions=False,
            )

    async def _start_runtime(
        self,
        key: LspServerKey,
        *,
        runtime_id: int,
        correlation_id: str,
        signal: object | None,
    ) -> LspRuntimeHandle:
        definition = self._catalog.definition(key.definition_id)
        environment = dict(self._baseline_environment)
        environment.update(definition.environment)
        handle: ProcessHandle | None = None
        client: LspClient | None = None
        try:
            handle = await self._launcher.start(
                ProcessLaunchRequest(
                    command=definition.command,
                    cwd=str(key.workspace_root),
                    effective_environment=tuple(sorted(environment.items())),
                ),
                correlation_id=correlation_id,
                signal=signal,
            )
            client = LspClient(
                handle,
                request_timeout_seconds=definition.request_timeout_seconds,
                shutdown_timeout_seconds=definition.shutdown_timeout_seconds,
                settings=definition.settings,
            )
            await client.initialize(
                root_uri=key.workspace_root.as_uri(),
                initialization_options=definition.initialization_options,
                timeout_seconds=definition.startup_timeout_seconds,
            )
            runtime = LspRuntimeHandle(
                key=key,
                runtime_id=runtime_id,
                client=client,
            )
            async with self._lock:
                if self._disposed:
                    raise LspProtocolError("LSP supervisor was disposed during startup")
                self._runtimes[key] = runtime
            return runtime
        except BaseException:
            with suppress(BaseException):
                if client is not None:
                    await client.abort()
                elif handle is not None:
                    await handle.close()
            raise


__all__ = ["LspRuntimeHandle", "LspServerSupervisor"]
