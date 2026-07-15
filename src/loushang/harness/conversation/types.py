from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def _require_text(value: str, *, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


class _FrozenMetadata(Mapping[str, object]):
    __slots__ = ("_data",)

    def __init__(self, value: Mapping[str, object]) -> None:
        self._data = deepcopy(dict(value))

    def __getitem__(self, key: str) -> object:
        return deepcopy(self._data[key])

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __deepcopy__(self, memo: dict[int, object]) -> dict[str, object]:
        return deepcopy(self._data, memo)

    def __repr__(self) -> str:
        return repr(self._data)


def _freeze_metadata(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("metadata must be a mapping")
    return _FrozenMetadata(value)


@dataclass(frozen=True)
class ConversationHeader:
    """Product-neutral identity and lineage for a persisted conversation."""

    conversation_id: str
    version: int
    created_at: str
    parent_conversation_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        _require_text(self.conversation_id, name="conversation id")
        _require_text(self.created_at, name="conversation creation time")
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise TypeError("conversation version must be an integer")
        if self.version < 1:
            raise ValueError("conversation version must be positive")
        if self.parent_conversation_id is not None:
            _require_text(
                self.parent_conversation_id,
                name="parent conversation id",
            )
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


@dataclass(frozen=True)
class ConversationRecord(Generic[T]):
    """Parent-linked record envelope whose payload is owned by a product adapter."""

    record_id: str
    parent_id: str | None
    kind: str
    created_at: str
    payload: T
    metadata: Mapping[str, object] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        _require_text(self.record_id, name="conversation record id")
        _require_text(self.kind, name="conversation record kind")
        _require_text(self.created_at, name="conversation record creation time")
        if self.parent_id is not None:
            _require_text(self.parent_id, name="conversation record parent id")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


@dataclass(frozen=True)
class ConversationTreeNode(Generic[R]):
    record: R
    children: tuple[ConversationTreeNode[R], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "children", tuple(self.children))


@dataclass(frozen=True)
class BranchDelta(Generic[R]):
    """Records unique to ``from_id`` after its common ancestor with ``target_id``."""

    from_id: str
    target_id: str
    common_ancestor_id: str | None
    divergent_records: tuple[R, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.from_id, name="branch delta source id")
        _require_text(self.target_id, name="branch delta target id")
        if self.common_ancestor_id is not None:
            _require_text(self.common_ancestor_id, name="branch delta ancestor id")
        object.__setattr__(self, "divergent_records", tuple(self.divergent_records))


@dataclass(frozen=True)
class CommandExecutionRecord:
    """Portable command result independent of a shell, UI, or model projection."""

    command: str
    output: str
    exit_code: int | None
    cancelled: bool = False
    truncated: bool = False
    full_output_path: str | None = None
    exclude_from_context: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        if not isinstance(self.command, str):
            raise TypeError("command must be a string")
        if not isinstance(self.output, str):
            raise TypeError("command output must be a string")
        if self.exit_code is not None and (
            isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int)
        ):
            raise TypeError("command exit code must be an integer or None")
        for name, value in (
            ("cancelled", self.cancelled),
            ("truncated", self.truncated),
            ("exclude_from_context", self.exclude_from_context),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"command {name} must be a boolean")
        if self.full_output_path is not None and not isinstance(
            self.full_output_path, str
        ):
            raise TypeError("command output path must be a string or None")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @property
    def output_path(self) -> str | None:
        return self.full_output_path


__all__ = [
    "BranchDelta",
    "CommandExecutionRecord",
    "ConversationHeader",
    "ConversationRecord",
    "ConversationTreeNode",
]
