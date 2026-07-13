from __future__ import annotations

from typing import Generic, TypeVar

from loushang.harness.context.packing import ContextPacker
from loushang.harness.context.types import (
    CompactionPlan,
    CompactionRequest,
    ContextItem,
    PackingRequest,
)

T = TypeVar("T")


class RecentWindowStrategy(Generic[T]):
    def __init__(self, packer: ContextPacker | None = None) -> None:
        self._packer = packer or ContextPacker()

    def plan(self, request: CompactionRequest[T]) -> CompactionPlan[T]:
        packed = self._packer.pack(
            PackingRequest(
                bundle=request.bundle,
                target_tokens=request.target_tokens,
                order="recent",
            )
        )
        return CompactionPlan(
            retained_items=packed.bundle.items,
            omitted_item_ids=packed.omitted_item_ids,
            diagnostics=packed.diagnostics,
        )


class RollingSummaryStrategy(Generic[T]):
    def __init__(self, packer: ContextPacker | None = None) -> None:
        self._packer = packer or ContextPacker()

    def plan(self, request: CompactionRequest[T]) -> CompactionPlan[T]:
        reserve = max(0, int(request.summary_reserve_tokens))
        if reserve <= 0:
            raise ValueError(
                "RollingSummaryStrategy requires summary_reserve_tokens greater than zero"
            )
        retained_budget = max(0, int(request.target_tokens) - reserve)
        packed = self._packer.pack(
            PackingRequest(
                bundle=request.bundle,
                target_tokens=retained_budget,
                order="recent",
            )
        )
        omitted = set(packed.omitted_item_ids)
        reduction_items: tuple[ContextItem[T], ...] = tuple(
            item for item in request.bundle.items if item.item_id in omitted
        )
        if reduction_items and request.previous_summary is not None:
            reduction_items = (request.previous_summary, *reduction_items)
        retained_items = packed.bundle.items
        if not reduction_items and request.previous_summary is not None:
            retained_items = (request.previous_summary, *retained_items)
        return CompactionPlan(
            retained_items=retained_items,
            reduction_items=reduction_items,
            omitted_item_ids=packed.omitted_item_ids,
            diagnostics=packed.diagnostics,
        )


__all__ = ["RecentWindowStrategy", "RollingSummaryStrategy"]
