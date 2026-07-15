from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

T = TypeVar("T")
PackingOrder = Literal["insertion", "recent", "priority"]
OverflowBehavior = Literal["report_overflow", "raise"]
FailureBehavior = Literal["keep_original", "raise"]
CompactionOutcome = Literal["completed", "overflow", "aborted", "failed"]


@dataclass(frozen=True)
class ContextDiagnostic:
    code: str
    message: str
    item_ids: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextItem(Generic[T]):
    item_id: str
    kind: str
    content: T
    estimated_tokens: int
    group_id: str | None = None
    priority: int = 0
    pinned: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise ValueError("context item id must be a non-empty string")
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("context item kind must be a non-empty string")
        if self.group_id is not None and (
            not isinstance(self.group_id, str) or not self.group_id.strip()
        ):
            raise ValueError("context item group id must be a non-empty string")
        object.__setattr__(self, "estimated_tokens", max(0, int(self.estimated_tokens)))
        object.__setattr__(self, "priority", int(self.priority))


@dataclass(frozen=True)
class ContextBundle(Generic[T]):
    items: tuple[ContextItem[T], ...]
    metadata: Mapping[str, object] = field(default_factory=dict)
    source_tokens: int = field(init=False)

    def __post_init__(self) -> None:
        items = tuple(self.items)
        ids = [item.item_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("context item ids must be unique within a bundle")
        object.__setattr__(self, "items", items)
        object.__setattr__(
            self,
            "source_tokens",
            sum(item.estimated_tokens for item in items),
        )


@dataclass(frozen=True)
class PackingRequest(Generic[T]):
    bundle: ContextBundle[T]
    target_tokens: int
    order: PackingOrder = "insertion"


@dataclass(frozen=True)
class PackingResult(Generic[T]):
    bundle: ContextBundle[T]
    selected_item_ids: tuple[str, ...]
    omitted_item_ids: tuple[str, ...]
    target_tokens: int
    overflow_tokens: int = 0
    diagnostics: tuple[ContextDiagnostic, ...] = ()


@dataclass(frozen=True)
class CompactionRequest(Generic[T]):
    bundle: ContextBundle[T]
    target_tokens: int
    summary_reserve_tokens: int = 0
    previous_summary: ContextItem[T] | None = None
    instructions: Mapping[str, object] = field(default_factory=dict)
    packing_order: PackingOrder = "recent"
    overflow_behavior: OverflowBehavior = "report_overflow"
    failure_behavior: FailureBehavior = "raise"
    cancellation: object | None = None


@dataclass(frozen=True)
class CompactionPlan(Generic[T]):
    retained_items: tuple[ContextItem[T], ...]
    reduction_items: tuple[ContextItem[T], ...] = ()
    omitted_item_ids: tuple[str, ...] = ()
    diagnostics: tuple[ContextDiagnostic, ...] = ()


@dataclass(frozen=True)
class ReductionRequest(Generic[T]):
    items: tuple[ContextItem[T], ...]
    max_output_tokens: int
    instructions: Mapping[str, object] = field(default_factory=dict)
    cancellation: object | None = None


@dataclass(frozen=True)
class CompactionArtifact(Generic[T]):
    summary: ContextItem[T]
    summarized_item_ids: tuple[str, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CompactionResult(Generic[T]):
    outcome: CompactionOutcome
    bundle: ContextBundle[T]
    plan: CompactionPlan[T] | None
    source_tokens: int
    output_tokens: int
    overflow_tokens: int = 0
    artifact: CompactionArtifact[T] | None = None
    diagnostics: tuple[ContextDiagnostic, ...] = ()
    error: str | None = None


R = TypeVar("R")


@dataclass(frozen=True)
class CompactionStatus(Generic[R]):
    is_compacting: bool
    last_reason: str | None = None
    last_result: R | None = None
    last_error: str | None = None
    aborted: bool = False


__all__ = [
    "CompactionArtifact",
    "CompactionOutcome",
    "CompactionPlan",
    "CompactionRequest",
    "CompactionResult",
    "CompactionStatus",
    "ContextBundle",
    "ContextDiagnostic",
    "ContextItem",
    "FailureBehavior",
    "OverflowBehavior",
    "PackingOrder",
    "PackingRequest",
    "PackingResult",
    "ReductionRequest",
]
