from __future__ import annotations

from dataclasses import dataclass, field

from loushang.tui.cell_width import grapheme_clusters

__all__ = ["EditorBuffer", "EditorSnapshot"]


@dataclass(frozen=True, slots=True)
class EditorSnapshot:
    clusters: tuple[str, ...]
    cursor: int


@dataclass(slots=True)
class EditorBuffer:
    _clusters: list[str] = field(default_factory=list)
    _cursor: int = 0
    _undo_stack: list[EditorSnapshot] = field(default_factory=list)
    _redo_stack: list[EditorSnapshot] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self._clusters)

    @property
    def value(self) -> str:
        return "".join(self._clusters)

    @property
    def cursor(self) -> int:
        return self._cursor

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

    def insert_text(self, text: str) -> None:
        inserted = list(grapheme_clusters(text))
        if not inserted:
            return
        self._push_undo()
        self._clusters[self._cursor : self._cursor] = inserted
        self._cursor += len(inserted)

    def insert_newline(self) -> None:
        self.insert_text("\n")

    def delete_backward(self) -> bool:
        if self._cursor <= 0:
            return False
        self._push_undo()
        del self._clusters[self._cursor - 1]
        self._cursor -= 1
        return True

    def delete_forward(self) -> bool:
        if self._cursor >= len(self._clusters):
            return False
        self._push_undo()
        del self._clusters[self._cursor]
        return True

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

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())
        return True

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

    def _push_undo(self) -> None:
        self._undo_stack.append(self._snapshot())
        self._redo_stack.clear()

    def _snapshot(self) -> EditorSnapshot:
        return EditorSnapshot(tuple(self._clusters), self._cursor)

    def _restore(self, snapshot: EditorSnapshot) -> None:
        self._clusters = list(snapshot.clusters)
        self._cursor = max(0, min(snapshot.cursor, len(self._clusters)))
