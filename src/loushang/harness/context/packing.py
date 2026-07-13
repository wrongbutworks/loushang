from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from loushang.harness.context.types import (
    ContextBundle,
    ContextDiagnostic,
    ContextItem,
    PackingRequest,
    PackingResult,
)

T = TypeVar("T")


@dataclass(frozen=True)
class _PackingUnit(Generic[T]):
    key: str
    items: tuple[ContextItem[T], ...]
    indexes: tuple[int, ...]
    tokens: int
    priority: int
    pinned: bool

    @property
    def first_index(self) -> int:
        return self.indexes[0]


class ContextPacker:
    def pack(self, request: PackingRequest[T]) -> PackingResult[T]:
        target_tokens = max(0, int(request.target_tokens))
        units, diagnostics = _build_units(request.bundle.items)
        pinned = [unit for unit in units if unit.pinned]
        candidates = [unit for unit in units if not unit.pinned]

        if request.order == "recent":
            candidates.reverse()
        elif request.order == "priority":
            candidates.sort(key=lambda unit: (-unit.priority, unit.first_index))
        elif request.order != "insertion":
            raise ValueError(f"unsupported packing order: {request.order}")

        selected_keys = {unit.key for unit in pinned}
        selected_tokens = sum(unit.tokens for unit in pinned)
        for unit in candidates:
            if selected_tokens + unit.tokens > target_tokens:
                continue
            selected_keys.add(unit.key)
            selected_tokens += unit.tokens

        selected_items = tuple(
            item
            for item in request.bundle.items
            if _unit_key(item) in selected_keys
        )
        selected_ids = tuple(item.item_id for item in selected_items)
        selected_id_set = set(selected_ids)
        omitted_ids = tuple(
            item.item_id
            for item in request.bundle.items
            if item.item_id not in selected_id_set
        )
        overflow = max(0, selected_tokens - target_tokens)
        if overflow:
            diagnostics.append(
                ContextDiagnostic(
                    code="pinned_context_overflow",
                    message="Pinned context groups exceed the target token budget.",
                    item_ids=tuple(
                        item.item_id for unit in pinned for item in unit.items
                    ),
                    details={
                        "target_tokens": target_tokens,
                        "selected_tokens": selected_tokens,
                        "overflow_tokens": overflow,
                    },
                )
            )
        return PackingResult(
            bundle=ContextBundle(
                items=selected_items,
                metadata=request.bundle.metadata,
            ),
            selected_item_ids=selected_ids,
            omitted_item_ids=omitted_ids,
            target_tokens=target_tokens,
            overflow_tokens=overflow,
            diagnostics=tuple(diagnostics),
        )


def _unit_key(item: ContextItem[Any]) -> str:
    if item.group_id is None:
        return f"item:{item.item_id}"
    return f"group:{item.group_id}"


def _build_units(
    items: tuple[ContextItem[T], ...],
) -> tuple[list[_PackingUnit[T]], list[ContextDiagnostic]]:
    grouped: dict[str, list[tuple[int, ContextItem[T]]]] = {}
    for index, item in enumerate(items):
        grouped.setdefault(_unit_key(item), []).append((index, item))

    diagnostics: list[ContextDiagnostic] = []
    units: list[_PackingUnit[T]] = []
    for key, indexed_items in grouped.items():
        indexes = tuple(index for index, _item in indexed_items)
        unit_items = tuple(item for _index, item in indexed_items)
        if len(indexes) > 1 and indexes[-1] - indexes[0] + 1 != len(indexes):
            diagnostics.append(
                ContextDiagnostic(
                    code="non_contiguous_context_group",
                    message="Context group members are not contiguous in source order.",
                    item_ids=tuple(item.item_id for item in unit_items),
                    details={"group_id": unit_items[0].group_id or ""},
                )
            )
        units.append(
            _PackingUnit(
                key=key,
                items=unit_items,
                indexes=indexes,
                tokens=sum(item.estimated_tokens for item in unit_items),
                priority=max(item.priority for item in unit_items),
                pinned=any(item.pinned for item in unit_items),
            )
        )
    units.sort(key=lambda unit: unit.first_index)
    return units, diagnostics


__all__ = ["ContextPacker"]
