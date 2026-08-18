"""Tool-facing Consumer of the narrow workspace Capability facet lease."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from loushang.harness.capabilities.graph_runtime import CapabilityFacetSet
from loushang.harness.capabilities.workspace_contracts import (
    WORKSPACE_EDIT_FACET,
    WORKSPACE_LIST_FACET,
    WORKSPACE_READ_FACET,
    WORKSPACE_SEARCH_FACET,
    WORKSPACE_TOOL_REQUIREMENT,
    WORKSPACE_WRITE_FACET,
)
from loushang.harness.tools.workspace.factory import ToolsOptions
from loushang.harness.workspace.operations import (
    EditOperations,
    FindOperations,
    GrepOperations,
    LsOperations,
    OperationResult,
    ReadOperations,
    WriteOperations,
)


@dataclass(frozen=True, slots=True)
class _ReadLeaseOperations:
    facets: CapabilityFacetSet

    def _operations(self) -> ReadOperations:
        return cast(ReadOperations, self.facets.require(WORKSPACE_READ_FACET))

    def exists(self, path: Path) -> OperationResult[bool]:
        return self._operations().exists(path)

    def is_file(self, path: Path) -> OperationResult[bool]:
        return self._operations().is_file(path)

    def read_bytes(self, path: Path) -> OperationResult[bytes]:
        return self._operations().read_bytes(path)


@dataclass(frozen=True, slots=True)
class _ListLeaseOperations:
    facets: CapabilityFacetSet

    def _operations(self) -> LsOperations:
        return cast(LsOperations, self.facets.require(WORKSPACE_LIST_FACET))

    def exists(self, path: Path) -> OperationResult[bool]:
        return self._operations().exists(path)

    def is_dir(self, path: Path) -> OperationResult[bool]:
        return self._operations().is_dir(path)

    def iterdir(self, path: Path) -> OperationResult[Iterable[Path]]:
        return self._operations().iterdir(path)


@dataclass(frozen=True, slots=True)
class _SearchLeaseOperations:
    facets: CapabilityFacetSet

    def _operations(self) -> object:
        return self.facets.require(WORKSPACE_SEARCH_FACET)

    def exists(self, path: Path) -> OperationResult[bool]:
        return cast(FindOperations, self._operations()).exists(path)

    def is_file(self, path: Path) -> OperationResult[bool]:
        return cast(GrepOperations, self._operations()).is_file(path)

    def is_dir(self, path: Path) -> OperationResult[bool]:
        return cast(FindOperations, self._operations()).is_dir(path)

    def read_text(
        self,
        path: Path,
        *,
        newline: str | None = None,
    ) -> OperationResult[str]:
        return cast(GrepOperations, self._operations()).read_text(
            path,
            newline=newline,
        )

    def walk_files(self, path: Path) -> OperationResult[Iterable[Path]]:
        return cast(FindOperations, self._operations()).walk_files(path)


@dataclass(frozen=True, slots=True)
class _WriteLeaseOperations:
    facets: CapabilityFacetSet

    def _operations(self) -> WriteOperations:
        return cast(WriteOperations, self.facets.require(WORKSPACE_WRITE_FACET))

    def exists(self, path: Path) -> OperationResult[bool]:
        return self._operations().exists(path)

    def is_file(self, path: Path) -> OperationResult[bool]:
        return self._operations().is_file(path)

    def mkdir(
        self,
        path: Path,
        *,
        parents: bool,
        exist_ok: bool,
    ) -> OperationResult[None]:
        return self._operations().mkdir(
            path,
            parents=parents,
            exist_ok=exist_ok,
        )

    def write_text(
        self,
        path: Path,
        content: str,
        *,
        newline: str | None = None,
    ) -> OperationResult[None]:
        return self._operations().write_text(path, content, newline=newline)


@dataclass(frozen=True, slots=True)
class _EditLeaseOperations:
    facets: CapabilityFacetSet

    def _operations(self) -> EditOperations:
        return cast(EditOperations, self.facets.require(WORKSPACE_EDIT_FACET))

    def exists(self, path: Path) -> OperationResult[bool]:
        return self._operations().exists(path)

    def is_file(self, path: Path) -> OperationResult[bool]:
        return self._operations().is_file(path)

    def read_text(
        self,
        path: Path,
        *,
        newline: str | None = None,
    ) -> OperationResult[str]:
        return self._operations().read_text(path, newline=newline)

    def write_text(
        self,
        path: Path,
        content: str,
        *,
        newline: str | None = None,
    ) -> OperationResult[None]:
        return self._operations().write_text(path, content, newline=newline)


@dataclass(frozen=True)
class WorkspaceToolCapabilityConsumer:
    """Adapt declared filesystem facets without receiving the graph runtime."""

    facets: CapabilityFacetSet

    def __post_init__(self) -> None:
        if self.facets.requirement != WORKSPACE_TOOL_REQUIREMENT:
            raise ValueError("workspace Tool Consumer received the wrong facet view")

    def apply(self, options: ToolsOptions = ToolsOptions()) -> ToolsOptions:
        search = _SearchLeaseOperations(self.facets)
        return replace(
            options,
            read_operations=_ReadLeaseOperations(self.facets),
            ls_operations=_ListLeaseOperations(self.facets),
            find_operations=search,
            grep_operations=search,
            write_operations=_WriteLeaseOperations(self.facets),
            edit_operations=_EditLeaseOperations(self.facets),
        )


__all__ = ["WorkspaceToolCapabilityConsumer"]
