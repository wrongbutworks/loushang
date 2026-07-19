"""Product-neutral dispatch from conversation records to transcript records."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from loushang.harness.conversation.types import ConversationRecord
from loushang.tui.transcript import ContextCompactionRecord, DisplayRecord

HistoryRecordDisposition = Literal[
    "render",
    "state-only",
    "hidden",
    "metadata-only",
]
HistoryPayloadProjector = Callable[[object], DisplayRecord | None]


@dataclass(frozen=True, slots=True)
class ConversationHistoryProjector:
    """Filter and dispatch ordered conversation items to display records."""

    dispositions: Mapping[str, HistoryRecordDisposition]
    payload_projectors: Mapping[str, HistoryPayloadProjector]
    fallback_projector: HistoryPayloadProjector

    def project_item(self, item: object) -> DisplayRecord | None:
        if not isinstance(item, ConversationRecord):
            return self.fallback_projector(item)
        if self.dispositions.get(item.kind) != "render":
            return None
        projector = self.payload_projectors.get(item.kind)
        return projector(item.payload) if projector is not None else None

    def project_items(
        self,
        items: Iterable[object],
    ) -> tuple[DisplayRecord, ...]:
        """Project renderable items in source order, omitting empty sections."""

        records: list[DisplayRecord] = []
        for item in items:
            record = self.project_item(item)
            if record is not None:
                records.append(record)
        return tuple(records)


def project_context_compaction_payload(
    payload: object,
) -> ContextCompactionRecord | None:
    """Project the neutral summary/token shape of a compaction checkpoint."""

    summary = getattr(payload, "summary", None)
    tokens_before = getattr(payload, "tokens_before", None)
    if not isinstance(summary, str):
        return None
    if tokens_before is not None and not isinstance(tokens_before, int):
        return None
    return ContextCompactionRecord(
        summary=summary,
        tokens_before=tokens_before,
    )


def project_context_branch_summary_payload(
    payload: object,
) -> ContextCompactionRecord | None:
    """Project the neutral summary shape of a branch context section."""

    summary = getattr(payload, "summary", None)
    if not isinstance(summary, str):
        return None
    return ContextCompactionRecord(summary=summary)


__all__ = [
    "ConversationHistoryProjector",
    "HistoryPayloadProjector",
    "HistoryRecordDisposition",
    "project_context_branch_summary_payload",
    "project_context_compaction_payload",
]
