from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

from .runtime import MaybeAwaitable, is_tool_aborted, raise_if_tool_aborted, resolve_maybe_awaitable

T = TypeVar("T")


async def resolve_operation(value: MaybeAwaitable[T]) -> T:
    return await resolve_maybe_awaitable(value)


def is_operation_aborted(signal: object | None) -> bool:
    return is_tool_aborted(signal)


def raise_if_operation_aborted(signal: object | None) -> None:
    raise_if_tool_aborted(signal)


class ReadOperations(Protocol):
    def exists(self, path: Path) -> MaybeAwaitable[bool]: ...

    def is_file(self, path: Path) -> MaybeAwaitable[bool]: ...

    def read_bytes(self, path: Path) -> MaybeAwaitable[bytes]: ...


class WriteOperations(Protocol):
    def exists(self, path: Path) -> MaybeAwaitable[bool]: ...

    def is_file(self, path: Path) -> MaybeAwaitable[bool]: ...

    def mkdir(self, path: Path, *, parents: bool, exist_ok: bool) -> MaybeAwaitable[None]: ...

    def write_text(self, path: Path, content: str, *, newline: str | None = None) -> MaybeAwaitable[None]: ...


class EditOperations(Protocol):
    def exists(self, path: Path) -> MaybeAwaitable[bool]: ...

    def is_file(self, path: Path) -> MaybeAwaitable[bool]: ...

    def read_text(self, path: Path, *, newline: str | None = None) -> MaybeAwaitable[str]: ...

    def write_text(self, path: Path, content: str, *, newline: str | None = None) -> MaybeAwaitable[None]: ...


class LsOperations(Protocol):
    def exists(self, path: Path) -> MaybeAwaitable[bool]: ...

    def is_dir(self, path: Path) -> MaybeAwaitable[bool]: ...

    def iterdir(self, path: Path) -> MaybeAwaitable[Iterable[Path]]: ...


class FindOperations(Protocol):
    def exists(self, path: Path) -> MaybeAwaitable[bool]: ...

    def is_dir(self, path: Path) -> MaybeAwaitable[bool]: ...

    def walk_files(self, path: Path) -> MaybeAwaitable[Iterable[Path]]: ...


class GrepOperations(Protocol):
    def exists(self, path: Path) -> MaybeAwaitable[bool]: ...

    def is_file(self, path: Path) -> MaybeAwaitable[bool]: ...

    def is_dir(self, path: Path) -> MaybeAwaitable[bool]: ...

    def read_text(self, path: Path, *, newline: str | None = None) -> MaybeAwaitable[str]: ...

    def walk_files(self, path: Path) -> MaybeAwaitable[Iterable[Path]]: ...


class ToolOperations(
    ReadOperations,
    WriteOperations,
    EditOperations,
    LsOperations,
    FindOperations,
    GrepOperations,
    Protocol,
):
    pass


@dataclass(frozen=True)
class LocalToolOperations:
    def exists(self, path: Path) -> bool:
        return path.exists()

    def is_file(self, path: Path) -> bool:
        return path.is_file()

    def is_dir(self, path: Path) -> bool:
        return path.is_dir()

    def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    def read_text(self, path: Path, *, newline: str | None = None) -> str:
        with path.open("r", encoding="utf-8", newline=newline) as handle:
            return handle.read()

    def write_text(self, path: Path, content: str, *, newline: str | None = None) -> None:
        with path.open("w", encoding="utf-8", newline=newline) as handle:
            handle.write(content)

    def mkdir(self, path: Path, *, parents: bool, exist_ok: bool) -> None:
        path.mkdir(parents=parents, exist_ok=exist_ok)

    def iterdir(self, path: Path) -> Iterable[Path]:
        return path.iterdir()

    def walk_files(self, path: Path) -> Iterable[Path]:
        return (candidate for candidate in sorted(path.rglob("*")) if candidate.is_file())


LOCAL_TOOL_OPERATIONS = LocalToolOperations()


def normalize_read_operations(operations: object | None) -> ReadOperations:
    if operations is None:
        return LOCAL_TOOL_OPERATIONS
    if _has_method(operations, "read_bytes"):
        return operations  # type: ignore[return-value]
    if _has_method(operations, "readFile") and _has_method(operations, "access"):
        return _PiReadOperationsAdapter(operations)
    return operations  # type: ignore[return-value]


def normalize_write_operations(operations: object | None) -> WriteOperations:
    if operations is None:
        return LOCAL_TOOL_OPERATIONS
    if _has_method(operations, "write_text"):
        return operations  # type: ignore[return-value]
    if _has_method(operations, "writeFile") and _has_method(operations, "mkdir"):
        return _PiWriteOperationsAdapter(operations)
    return operations  # type: ignore[return-value]


def normalize_edit_operations(operations: object | None) -> EditOperations:
    if operations is None:
        return LOCAL_TOOL_OPERATIONS
    if _has_method(operations, "read_text") and _has_method(operations, "write_text"):
        return operations  # type: ignore[return-value]
    if _has_method(operations, "readFile") and _has_method(operations, "writeFile") and _has_method(operations, "access"):
        return _PiEditOperationsAdapter(operations)
    return operations  # type: ignore[return-value]


def normalize_ls_operations(operations: object | None) -> LsOperations:
    if operations is None:
        return LOCAL_TOOL_OPERATIONS
    if _has_method(operations, "iterdir") and _has_method(operations, "is_dir"):
        return operations  # type: ignore[return-value]
    if _has_method(operations, "stat") and _has_method(operations, "readdir"):
        return _PiLsOperationsAdapter(operations)
    return operations  # type: ignore[return-value]


def normalize_find_operations(operations: object | None) -> FindOperations:
    if operations is None:
        return LOCAL_TOOL_OPERATIONS
    if _has_method(operations, "walk_files") and _has_method(operations, "is_dir"):
        return operations  # type: ignore[return-value]
    if _has_method(operations, "glob") and _has_method(operations, "exists"):
        return _PiFindOperationsAdapter(operations)
    return operations  # type: ignore[return-value]


def normalize_grep_operations(operations: object | None) -> GrepOperations:
    if operations is None:
        return LOCAL_TOOL_OPERATIONS
    if _has_method(operations, "read_text") and _has_method(operations, "is_dir"):
        return operations  # type: ignore[return-value]
    if _has_method(operations, "readFile") and _has_method(operations, "isDirectory"):
        return _PiGrepOperationsAdapter(operations)
    return operations  # type: ignore[return-value]


def _has_method(value: object, name: str) -> bool:
    return callable(getattr(value, name, None))


def _decode_text_payload(path: Path, payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes | bytearray | memoryview):
        return bytes(payload).decode("utf-8")
    raise TypeError(f"readFile returned unsupported payload for {path}: {type(payload).__name__}")


def _bytes_payload(path: Path, payload: object) -> bytes:
    if isinstance(payload, bytes | bytearray | memoryview):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise TypeError(f"readFile returned unsupported payload for {path}: {type(payload).__name__}")


def _stat_is_directory(stat: object) -> bool:
    method = getattr(stat, "isDirectory", None)
    if callable(method):
        return bool(method())
    method = getattr(stat, "is_dir", None)
    if callable(method):
        return bool(method())
    if isinstance(stat, dict):
        value = stat.get("isDirectory")
        if callable(value):
            return bool(value())
        if isinstance(value, bool):
            return value
        value = stat.get("is_dir")
        if callable(value):
            return bool(value())
        if isinstance(value, bool):
            return value
    raise TypeError("stat result must expose isDirectory()")


@dataclass(frozen=True)
class _PiReadOperationsAdapter:
    operations: object

    async def exists(self, path: Path) -> bool:
        try:
            await resolve_operation(self.operations.access(str(path)))  # type: ignore[attr-defined]
        except OSError:
            return False
        return True

    def is_file(self, path: Path) -> bool:
        del path
        return True

    async def read_bytes(self, path: Path) -> bytes:
        payload = await resolve_operation(self.operations.readFile(str(path)))  # type: ignore[attr-defined]
        return _bytes_payload(path, payload)

    async def detect_image_mime_type(self, path: Path) -> str | None:
        detector = getattr(self.operations, "detectImageMimeType", None)
        if detector is None:
            return None
        value = await resolve_operation(detector(str(path)))
        return value if isinstance(value, str) and value else None


@dataclass(frozen=True)
class _PiWriteOperationsAdapter:
    operations: object

    def exists(self, path: Path) -> bool:
        del path
        return False

    def is_file(self, path: Path) -> bool:
        del path
        return True

    async def mkdir(self, path: Path, *, parents: bool, exist_ok: bool) -> None:
        del parents, exist_ok
        await resolve_operation(self.operations.mkdir(str(path)))  # type: ignore[attr-defined]

    async def write_text(self, path: Path, content: str, *, newline: str | None = None) -> None:
        del newline
        await resolve_operation(self.operations.writeFile(str(path), content))  # type: ignore[attr-defined]


@dataclass(frozen=True)
class _PiEditOperationsAdapter:
    operations: object

    async def exists(self, path: Path) -> bool:
        try:
            await resolve_operation(self.operations.access(str(path)))  # type: ignore[attr-defined]
        except OSError:
            return False
        return True

    def is_file(self, path: Path) -> bool:
        del path
        return True

    async def read_text(self, path: Path, *, newline: str | None = None) -> str:
        del newline
        payload = await resolve_operation(self.operations.readFile(str(path)))  # type: ignore[attr-defined]
        return _decode_text_payload(path, payload)

    async def write_text(self, path: Path, content: str, *, newline: str | None = None) -> None:
        del newline
        await resolve_operation(self.operations.writeFile(str(path), content))  # type: ignore[attr-defined]


@dataclass(frozen=True)
class _PiLsOperationsAdapter:
    operations: object

    async def exists(self, path: Path) -> bool:
        value = await resolve_operation(self.operations.exists(str(path)))  # type: ignore[attr-defined]
        return bool(value)

    async def is_dir(self, path: Path) -> bool:
        stat = await resolve_operation(self.operations.stat(str(path)))  # type: ignore[attr-defined]
        return _stat_is_directory(stat)

    async def iterdir(self, path: Path) -> Iterable[Path]:
        entries = await resolve_operation(self.operations.readdir(str(path)))  # type: ignore[attr-defined]
        return [path / entry for entry in entries]


@dataclass(frozen=True)
class _PiFindOperationsAdapter:
    operations: object

    async def exists(self, path: Path) -> bool:
        value = await resolve_operation(self.operations.exists(str(path)))  # type: ignore[attr-defined]
        return bool(value)

    def is_dir(self, path: Path) -> bool:
        del path
        return True

    async def walk_files(self, path: Path) -> Iterable[Path]:
        entries = await resolve_operation(
            self.operations.glob("**/*", str(path), {"ignore": [], "limit": 1_000_000})  # type: ignore[attr-defined]
        )
        return [_path_from_pi_entry(path, entry) for entry in entries]

    async def glob_paths(self, path: Path, *, pattern: str, limit: int) -> Iterable[Path]:
        entries = await resolve_operation(
            self.operations.glob(  # type: ignore[attr-defined]
                pattern,
                str(path),
                {"ignore": ["**/node_modules/**", "**/.git/**"], "limit": limit},
            )
        )
        return [_path_from_pi_entry(path, entry) for entry in entries]


@dataclass(frozen=True)
class _PiGrepOperationsAdapter:
    operations: object

    async def exists(self, path: Path) -> bool:
        try:
            await self.is_dir(path)
        except OSError:
            return False
        return True

    async def is_file(self, path: Path) -> bool:
        return not await self.is_dir(path)

    async def is_dir(self, path: Path) -> bool:
        value = await resolve_operation(self.operations.isDirectory(str(path)))  # type: ignore[attr-defined]
        return bool(value)

    async def read_text(self, path: Path, *, newline: str | None = None) -> str:
        del newline
        payload = await resolve_operation(self.operations.readFile(str(path)))  # type: ignore[attr-defined]
        return _decode_text_payload(path, payload)

    def walk_files(self, path: Path) -> Iterable[Path]:
        return (candidate for candidate in sorted(path.rglob("*")) if candidate.is_file())


def _path_from_pi_entry(root: Path, entry: Any) -> Path:
    if isinstance(entry, Path):
        return entry if entry.is_absolute() else root / entry
    if not isinstance(entry, str):
        raise TypeError("glob entries must be strings or paths")
    path = Path(entry)
    return path if path.is_absolute() else root / path
