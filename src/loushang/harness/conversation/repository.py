from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Generic, TypeVar

from loushang.harness.conversation.ports import ConversationFolder
from loushang.harness.conversation.types import BranchDelta, ConversationTreeNode
from loushang.harness.journal import (
    BranchMode,
    JournalDiagnostic,
    JsonlJournal,
    TranscriptRepository,
)

H = TypeVar("H")
R = TypeVar("R")
S = TypeVar("S")


class ConversationRepository(Generic[H, R]):
    """Conversation semantics over the generic parent-linked journal repository."""

    def __init__(
        self,
        transcript: TranscriptRepository[H, R],
        *,
        record_id: Callable[[R], str],
        parent_id: Callable[[R], str | None],
    ) -> None:
        self._transcript = transcript
        self._record_id = record_id
        self._parent_id = parent_id

    @classmethod
    def create(
        cls,
        *,
        header: H,
        records: Sequence[R] = (),
        record_id: Callable[[R], str],
        parent_id: Callable[[R], str | None],
        journal: JsonlJournal[H, R] | None = None,
        mode: BranchMode = "strict",
        leaf_id: str | None = None,
    ) -> ConversationRepository[H, R]:
        return cls(
            TranscriptRepository.create(
                header=header,
                records=records,
                record_id=record_id,
                parent_id=parent_id,
                journal=journal,
                mode=mode,
                leaf_id=leaf_id,
            ),
            record_id=record_id,
            parent_id=parent_id,
        )

    @classmethod
    def load(
        cls,
        journal: JsonlJournal[H, R],
        *,
        record_id: Callable[[R], str],
        parent_id: Callable[[R], str | None],
        mode: BranchMode = "strict",
        writable: bool = True,
    ) -> ConversationRepository[H, R]:
        return cls(
            TranscriptRepository.load(
                journal,
                record_id=record_id,
                parent_id=parent_id,
                mode=mode,
                writable=writable,
            ),
            record_id=record_id,
            parent_id=parent_id,
        )

    @property
    def transcript(self) -> TranscriptRepository[H, R]:
        return self._transcript

    @property
    def header(self) -> H:
        return self._transcript.header

    @property
    def records(self) -> tuple[R, ...]:
        return self._transcript.records

    @property
    def path(self) -> Path | None:
        return self._transcript.path

    @property
    def leaf_id(self) -> str | None:
        return self._transcript.leaf_id

    @property
    def diagnostics(self) -> tuple[JournalDiagnostic, ...]:
        return self._transcript.diagnostics

    def append(self, record: R) -> str:
        return self._transcript.append(record)

    def set_header(self, header: H, *, rewrite: bool = False) -> None:
        self._transcript.set_header(header, rewrite=rewrite)

    def rewrite(self) -> None:
        self._transcript.rewrite()

    def get(self, record_id: str) -> R | None:
        return self._transcript.get(record_id)

    def leaf(self) -> R | None:
        return self._transcript.leaf()

    def children(self, record_id: str) -> tuple[R, ...]:
        return self._transcript.children(record_id)

    def branch(self, record_id: str) -> None:
        self._transcript.select_leaf(record_id)

    def reset_branch(self) -> None:
        self._transcript.reset_leaf()

    def active_records(self) -> tuple[R, ...]:
        return self._transcript.path_to()

    def records_to(self, record_id: str) -> tuple[R, ...]:
        return self._transcript.path_to(record_id)

    def lowest_common_ancestor(self, left_id: str, right_id: str) -> R | None:
        return self._transcript.lowest_common_ancestor(left_id, right_id)

    def branch_delta(self, from_id: str, target_id: str) -> BranchDelta[R]:
        ancestor = self.lowest_common_ancestor(from_id, target_id)
        ancestor_id = self._record_id(ancestor) if ancestor is not None else None
        path = self.records_to(from_id)
        divergent_records = path
        if ancestor_id is not None:
            ancestor_position = next(
                index
                for index, record in enumerate(path)
                if self._record_id(record) == ancestor_id
            )
            divergent_records = path[ancestor_position + 1 :]
        return BranchDelta(
            from_id=from_id,
            target_id=target_id,
            common_ancestor_id=ancestor_id,
            divergent_records=divergent_records,
        )

    def tree(self) -> tuple[ConversationTreeNode[R], ...]:
        roots = self._transcript.roots()
        nodes: dict[str, ConversationTreeNode[R]] = {}
        stack = [(root, False) for root in reversed(roots)]
        while stack:
            record, expanded = stack.pop()
            record_id = self._record_id(record)
            children = self._transcript.children(record_id)
            if expanded:
                nodes[record_id] = ConversationTreeNode(
                    record=record,
                    children=tuple(nodes[self._record_id(child)] for child in children),
                )
                continue
            stack.append((record, True))
            stack.extend((child, False) for child in reversed(children))
        return tuple(nodes[self._record_id(root)] for root in roots)

    def fold_active(self, folder: ConversationFolder[R, S]) -> S:
        return fold_records(self.active_records(), folder)

    def fold_all(self, folder: ConversationFolder[R, S]) -> S:
        return fold_records(self.records, folder)

    def fork(
        self,
        *,
        header: H,
        journal: JsonlJournal[H, R] | None,
        leaf_id: str | None = None,
    ) -> ConversationRepository[H, R]:
        return type(self)(
            self._transcript.fork(
                header=header,
                journal=journal,
                leaf_id=leaf_id,
            ),
            record_id=self._record_id,
            parent_id=self._parent_id,
        )


def fold_records(
    records: Sequence[R],
    folder: ConversationFolder[R, S],
) -> S:
    state = folder.initial()
    for record in records:
        state = folder.apply(state, record)
    return state


__all__ = ["ConversationRepository", "fold_records"]
