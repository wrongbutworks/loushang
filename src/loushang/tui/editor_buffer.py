from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from loushang.tui.cell_width import grapheme_clusters
from loushang.tui.undo_stack import UndoStack
from loushang.tui.word_navigation import cluster_kind, word_left_index, word_right_index

__all__ = ["EditorBuffer", "EditorSnapshot"]


@dataclass(frozen=True, slots=True)
class EditorSnapshot:
    clusters: tuple[str, ...]
    cursor: int


@dataclass(slots=True)
class EditorBuffer:
    max_undo_depth: int | None = None
    _clusters: list[str] = field(default_factory=list, repr=False)
    _cursor: int = 0
    _undo_stack: UndoStack[EditorSnapshot] = field(init=False, repr=False)
    _redo_stack: UndoStack[EditorSnapshot] = field(default_factory=UndoStack, repr=False)

    def __post_init__(self) -> None:
        if self.max_undo_depth is not None and self.max_undo_depth <= 0:
            raise ValueError("max_undo_depth must be positive or None")
        self._undo_stack = UndoStack(max_depth=self.max_undo_depth)

    def __len__(self) -> int:
        return len(self._clusters)

    @property
    def value(self) -> str:
        return "".join(self._clusters)

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def text_before_cursor(self) -> str:
        return "".join(self._clusters[: self._cursor])

    @property
    def text_after_cursor(self) -> str:
        return "".join(self._clusters[self._cursor :])

    def set_text(self, text: str) -> None:
        self._clusters = list(grapheme_clusters(text))
        self._cursor = len(self._clusters)
        self._undo_stack.clear()
        self._redo_stack.clear()

    def clear(self) -> None:
        self._clusters.clear()
        self._cursor = 0
        self._undo_stack.clear()
        self._redo_stack.clear()

    def insert_text(self, text: str, *, record: bool = True) -> None:
        inserted = list(grapheme_clusters(text))
        if not inserted:
            return
        if record:
            self._push_undo()
        self._clusters[self._cursor : self._cursor] = inserted
        self._cursor += len(inserted)

    def insert_newline(self, *, record: bool = True) -> None:
        self.insert_text("\n", record=record)

    def delete_backward(self, *, record: bool = True) -> bool:
        if self._cursor <= 0:
            return False
        if record:
            self._push_undo()
        del self._clusters[self._cursor - 1]
        self._cursor -= 1
        return True

    def delete_forward(self, *, record: bool = True) -> bool:
        if self._cursor >= len(self._clusters):
            return False
        if record:
            self._push_undo()
        del self._clusters[self._cursor]
        return True

    def delete_range(self, start: int, end: int, *, record: bool = True) -> str:
        start, end = self._clamp_range(start, end)
        if start == end:
            return ""
        removed = self._clusters[start:end]
        if record:
            self._push_undo()
        del self._clusters[start:end]
        self._cursor = start
        return "".join(removed)

    def replace_range(self, start: int, end: int, text: str, *, record: bool = True) -> str:
        start, end = self._clamp_range(start, end)
        removed = self._clusters[start:end]
        inserted = list(grapheme_clusters(text))
        if not removed and not inserted:
            return ""
        if removed == inserted:
            self._cursor = start + len(inserted)
            return "".join(removed)
        if record:
            self._push_undo()
        self._clusters[start:end] = inserted
        self._cursor = start + len(inserted)
        return "".join(removed)

    def move_left(self) -> bool:
        if self._cursor <= 0:
            return False
        self._cursor -= 1
        return True

    def move_right(self) -> bool:
        if self._cursor >= len(self._clusters):
            return False
        self._cursor += 1
        return True

    def move_to_start(self) -> bool:
        if self._cursor == 0:
            return False
        self._cursor = 0
        return True

    def move_to_end(self) -> bool:
        end = len(self._clusters)
        if self._cursor == end:
            return False
        self._cursor = end
        return True

    def move_to_line_start(self) -> bool:
        target = self._line_start_index()
        if target == self._cursor:
            return False
        self._cursor = target
        return True

    def move_to_line_end(self) -> bool:
        target = self._line_end_index()
        if target == self._cursor:
            return False
        self._cursor = target
        return True

    def move_word_left(self) -> bool:
        target = self._word_left_index()
        if target == self._cursor:
            return False
        self._cursor = target
        return True

    def move_word_right(self) -> bool:
        target = self._word_right_index()
        if target == self._cursor:
            return False
        self._cursor = target
        return True

    def word_left_index(self) -> int:
        return self._word_left_index()

    def word_right_index(self) -> int:
        return self._word_right_index()

    def undo(self) -> bool:
        snapshot = self._undo_stack.pop()
        if snapshot is None:
            return False
        self._redo_stack.push(self._snapshot())
        self._restore(snapshot)
        return True

    def redo(self) -> bool:
        snapshot = self._redo_stack.pop()
        if snapshot is None:
            return False
        self._undo_stack.push(self._snapshot())
        self._restore(snapshot)
        return True

    def apply_edit(self, edit: Callable[[], object]) -> bool:
        """Record a composite edit as one undo step.

        The callback should use edit methods with ``record=False`` so nested
        operations do not create separate undo entries.
        """
        snapshot = self._snapshot()
        edit()
        if self._snapshot() == snapshot:
            return False
        self._push_undo(snapshot)
        return True

    def _clamp_range(self, start: int, end: int) -> tuple[int, int]:
        length = len(self._clusters)
        start = max(0, min(start, length))
        end = max(0, min(end, length))
        if end < start:
            end = start
        return start, end

    def _line_start_index(self) -> int:
        index = self._cursor
        while index > 0 and self._clusters[index - 1] != "\n":
            index -= 1
        return index

    def _line_end_index(self) -> int:
        index = self._cursor
        while index < len(self._clusters) and self._clusters[index] != "\n":
            index += 1
        return index

    def _word_left_index(self) -> int:
        return word_left_index(self._clusters, self._cursor, cluster_kind)

    def _word_right_index(self) -> int:
        return word_right_index(self._clusters, self._cursor, cluster_kind)

    def _push_undo(self, snapshot: EditorSnapshot | None = None) -> None:
        self._undo_stack.push(snapshot if snapshot is not None else self._snapshot())
        self._redo_stack.clear()

    def _snapshot(self) -> EditorSnapshot:
        return EditorSnapshot(tuple(self._clusters), self._cursor)

    def _restore(self, snapshot: EditorSnapshot) -> None:
        self._clusters = list(snapshot.clusters)
        self._cursor = max(0, min(snapshot.cursor, len(self._clusters)))
