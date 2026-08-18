"""Coding-owned admission wrapper for neutral workspace operations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from loushang.harness.authorization import EffectiveExecutionProfile
from loushang.harness.workspace.operations import (
    OperationResult,
    ToolOperations,
)


@dataclass(frozen=True, slots=True)
class CodingWorkspaceOperations:
    """Constrain filesystem operations to one admitted Coding workspace."""

    root: Path
    operations: ToolOperations
    execution_profile: EffectiveExecutionProfile

    def __post_init__(self) -> None:
        root = self.root.expanduser().resolve()
        object.__setattr__(self, "root", root)
        if not isinstance(self.execution_profile, EffectiveExecutionProfile):
            raise TypeError(
                "Coding workspace operations require an EffectiveExecutionProfile"
            )

    def exists(self, path: Path) -> OperationResult[bool]:
        return self.operations.exists(self._read_path(path))

    def is_file(self, path: Path) -> OperationResult[bool]:
        return self.operations.is_file(self._read_path(path))

    def is_dir(self, path: Path) -> OperationResult[bool]:
        return self.operations.is_dir(self._read_path(path))

    def read_bytes(self, path: Path) -> OperationResult[bytes]:
        return self.operations.read_bytes(self._read_path(path))

    def read_text(
        self,
        path: Path,
        *,
        newline: str | None = None,
    ) -> OperationResult[str]:
        return self.operations.read_text(self._read_path(path), newline=newline)

    def mkdir(
        self,
        path: Path,
        *,
        parents: bool,
        exist_ok: bool,
    ) -> OperationResult[None]:
        return self.operations.mkdir(
            self._write_path(path),
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
        return self.operations.write_text(
            self._write_path(path),
            content,
            newline=newline,
        )

    def iterdir(self, path: Path) -> OperationResult[Iterable[Path]]:
        return self.operations.iterdir(self._read_path(path))

    def walk_files(self, path: Path) -> OperationResult[Iterable[Path]]:
        return self.operations.walk_files(self._read_path(path))

    def _read_path(self, path: Path) -> Path:
        candidate = path.expanduser().resolve()
        if not (candidate == self.root or candidate.is_relative_to(self.root)):
            raise PermissionError(
                f"workspace operation path is outside the admitted root: {path}"
            )
        if _covered(candidate, self.execution_profile.denied_roots):
            raise PermissionError(f"workspace operation path is denied: {path}")
        if not _covered(candidate, self.execution_profile.readable_roots):
            raise PermissionError(
                f"workspace operation path is outside the admitted readable roots: {path}"
            )
        return candidate

    def _write_path(self, path: Path) -> Path:
        candidate = self._read_path(path)
        if not _covered(candidate, self.execution_profile.writable_roots):
            raise PermissionError(
                "workspace operation path is outside the admitted writable roots"
            )
        return candidate


def _covered(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


__all__ = ["CodingWorkspaceOperations"]
