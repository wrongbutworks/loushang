"""Stable Session ports backed by workspace Capability Consumers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from loushang.harness.session.session_capability_consumer import (
    SessionWorkspaceProcessCapabilityConsumer,
    SessionWorkspaceToolCapabilityConsumer,
)
from loushang.harness.tools.workspace.factory import ToolsOptions
from loushang.harness.workspace.operations import (
    EditOperations,
    FindOperations,
    GrepOperations,
    LsOperations,
    ReadOperations,
    WriteOperations,
    resolve_operation,
)
from loushang.harness.workspace.process import (
    AuthorizedProcessLauncher,
    ProcessHandle,
    ProcessLaunchRequest,
)

EnsureWorkspaceMounted = Callable[[], Awaitable[object]]


class SessionWorkspaceCapabilityPorts:
    """Route long-lived callers through the current typed facet leases."""

    def __init__(self, ensure_mounted: EnsureWorkspaceMounted) -> None:
        self._ensure_mounted = ensure_mounted
        self._tool_options: ToolsOptions | None = None
        self._process_consumer: SessionWorkspaceProcessCapabilityConsumer | None = None
        self._invalidated = False
        read = _ReadOperations(self)
        listing = _ListOperations(self)
        search = _SearchOperations(self)
        write = _WriteOperations(self)
        edit = _EditOperations(self)
        self._operation_bindings: Mapping[str, object] = MappingProxyType(
            {
                "read_operations": read,
                "ls_operations": listing,
                "find_operations": search,
                "grep_operations": search,
                "write_operations": write,
                "edit_operations": edit,
            }
        )
        self._process_launcher: AuthorizedProcessLauncher = _ProcessLauncher(self)

    @property
    def operation_bindings(self) -> Mapping[str, object]:
        return self._operation_bindings

    @property
    def process_launcher(self) -> AuthorizedProcessLauncher:
        return self._process_launcher

    def install(
        self,
        *,
        tools: SessionWorkspaceToolCapabilityConsumer,
        process: SessionWorkspaceProcessCapabilityConsumer,
    ) -> None:
        if self._invalidated:
            raise RuntimeError("Session workspace Capability ports are disposed")
        if self._tool_options is not None or self._process_consumer is not None:
            raise RuntimeError("Session workspace Capability ports are already mounted")
        self._tool_options = tools.apply()
        self._process_consumer = process

    def invalidate(self) -> None:
        self._invalidated = True
        self._tool_options = None
        self._process_consumer = None

    async def _tools(self) -> ToolsOptions:
        self._require_live()
        options = self._tool_options
        if options is None:
            await self._ensure_mounted()
            self._require_live()
            options = self._tool_options
        if options is None:
            raise RuntimeError("Session workspace Capability was not mounted")
        return options

    async def _process(self) -> SessionWorkspaceProcessCapabilityConsumer:
        self._require_live()
        consumer = self._process_consumer
        if consumer is None:
            await self._ensure_mounted()
            self._require_live()
            consumer = self._process_consumer
        if consumer is None:
            raise RuntimeError("Session workspace process Capability was not mounted")
        return consumer

    def _require_live(self) -> None:
        if self._invalidated:
            raise RuntimeError("Session workspace Capability ports are disposed")


@dataclass(frozen=True, slots=True)
class _ReadOperations:
    owner: SessionWorkspaceCapabilityPorts

    async def _operations(self) -> ReadOperations:
        options = await self.owner._tools()
        if options.read_operations is None:
            raise RuntimeError("workspace read operations are unavailable")
        return options.read_operations

    async def exists(self, path: Path) -> bool:
        return await resolve_operation((await self._operations()).exists(path))

    async def is_file(self, path: Path) -> bool:
        return await resolve_operation((await self._operations()).is_file(path))

    async def read_bytes(self, path: Path) -> bytes:
        return await resolve_operation((await self._operations()).read_bytes(path))


@dataclass(frozen=True, slots=True)
class _ListOperations:
    owner: SessionWorkspaceCapabilityPorts

    async def _operations(self) -> LsOperations:
        options = await self.owner._tools()
        if options.ls_operations is None:
            raise RuntimeError("workspace list operations are unavailable")
        return options.ls_operations

    async def exists(self, path: Path) -> bool:
        return await resolve_operation((await self._operations()).exists(path))

    async def is_dir(self, path: Path) -> bool:
        return await resolve_operation((await self._operations()).is_dir(path))

    async def iterdir(self, path: Path) -> Iterable[Path]:
        return await resolve_operation((await self._operations()).iterdir(path))


@dataclass(frozen=True, slots=True)
class _SearchOperations:
    owner: SessionWorkspaceCapabilityPorts

    async def _find_operations(self) -> FindOperations:
        options = await self.owner._tools()
        if options.find_operations is None:
            raise RuntimeError("workspace find operations are unavailable")
        return options.find_operations

    async def _grep_operations(self) -> GrepOperations:
        options = await self.owner._tools()
        if options.grep_operations is None:
            raise RuntimeError("workspace grep operations are unavailable")
        return options.grep_operations

    async def exists(self, path: Path) -> bool:
        return await resolve_operation((await self._find_operations()).exists(path))

    async def is_file(self, path: Path) -> bool:
        return await resolve_operation((await self._grep_operations()).is_file(path))

    async def is_dir(self, path: Path) -> bool:
        return await resolve_operation((await self._find_operations()).is_dir(path))

    async def read_text(self, path: Path, *, newline: str | None = None) -> str:
        return await resolve_operation(
            (await self._grep_operations()).read_text(path, newline=newline)
        )

    async def walk_files(self, path: Path) -> Iterable[Path]:
        return await resolve_operation((await self._find_operations()).walk_files(path))


@dataclass(frozen=True, slots=True)
class _WriteOperations:
    owner: SessionWorkspaceCapabilityPorts

    async def _operations(self) -> WriteOperations:
        options = await self.owner._tools()
        if options.write_operations is None:
            raise RuntimeError("workspace write operations are unavailable")
        return options.write_operations

    async def exists(self, path: Path) -> bool:
        return await resolve_operation((await self._operations()).exists(path))

    async def is_file(self, path: Path) -> bool:
        return await resolve_operation((await self._operations()).is_file(path))

    async def mkdir(
        self,
        path: Path,
        *,
        parents: bool,
        exist_ok: bool,
    ) -> None:
        await resolve_operation(
            (await self._operations()).mkdir(
                path,
                parents=parents,
                exist_ok=exist_ok,
            )
        )

    async def write_text(
        self,
        path: Path,
        content: str,
        *,
        newline: str | None = None,
    ) -> None:
        await resolve_operation(
            (await self._operations()).write_text(
                path,
                content,
                newline=newline,
            )
        )


@dataclass(frozen=True, slots=True)
class _EditOperations:
    owner: SessionWorkspaceCapabilityPorts

    async def _operations(self) -> EditOperations:
        options = await self.owner._tools()
        if options.edit_operations is None:
            raise RuntimeError("workspace edit operations are unavailable")
        return options.edit_operations

    async def exists(self, path: Path) -> bool:
        return await resolve_operation((await self._operations()).exists(path))

    async def is_file(self, path: Path) -> bool:
        return await resolve_operation((await self._operations()).is_file(path))

    async def read_text(self, path: Path, *, newline: str | None = None) -> str:
        return await resolve_operation(
            (await self._operations()).read_text(path, newline=newline)
        )

    async def write_text(
        self,
        path: Path,
        content: str,
        *,
        newline: str | None = None,
    ) -> None:
        await resolve_operation(
            (await self._operations()).write_text(
                path,
                content,
                newline=newline,
            )
        )


@dataclass(frozen=True, slots=True)
class _ProcessLauncher:
    owner: SessionWorkspaceCapabilityPorts

    async def start(
        self,
        request: ProcessLaunchRequest,
        *,
        correlation_id: str,
        signal: object | None = None,
    ) -> ProcessHandle:
        consumer = await self.owner._process()
        return await consumer.process_launcher.start(
            request,
            correlation_id=correlation_id,
            signal=signal,
        )


__all__ = ["SessionWorkspaceCapabilityPorts"]
