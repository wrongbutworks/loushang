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
    max_undo_depth: int | None = None
    _clusters: list[str] = field(default_factory=list, repr=False)
    _cursor: int = 0
    _undo_stack: list[EditorSnapshot] = field(default_factory=list, repr=False)
    _redo_stack: list[EditorSnapshot] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self.max_undo_depth is not None and self.max_undo_depth <= 0:
            raise ValueError("max_undo_depth must be positive or None")

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

    def delete_range(self, start: int, end: int) -> str:
        start, end = self._clamp_range(start, end)
        if start == end:
            return ""
        removed = self._clusters[start:end]
        self._push_undo()
        del self._clusters[start:end]
        self._cursor = start
        return "".join(removed)

    def replace_range(self, start: int, end: int, text: str) -> str:
        start, end = self._clamp_range(start, end)
        removed = self._clusters[start:end]
        inserted = list(grapheme_clusters(text))
        if not removed and not inserted:
            return ""
        if removed == inserted:
            self._cursor = start + len(inserted)
            return "".join(removed)
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
        index = self._cursor
        while index > 0 and _cluster_kind(self._clusters[index - 1]) == "space":
            index -= 1
        if index == 0:
            return index
        kind = _cluster_kind(self._clusters[index - 1])
        while index > 0 and _cluster_kind(self._clusters[index - 1]) == kind:
            index -= 1
        return index

    def _word_right_index(self) -> int:
        index = self._cursor
        while index < len(self._clusters) and _cluster_kind(self._clusters[index]) == "space":
            index += 1
        if index >= len(self._clusters):
            return index
        kind = _cluster_kind(self._clusters[index])
        while index < len(self._clusters) and _cluster_kind(self._clusters[index]) == kind:
            index += 1
        return index

    def _push_undo(self) -> None:
        self._undo_stack.append(self._snapshot())
        if self.max_undo_depth is not None:
            del self._undo_stack[:-self.max_undo_depth]
        self._redo_stack.clear()

    def _snapshot(self) -> EditorSnapshot:
        return EditorSnapshot(tuple(self._clusters), self._cursor)

    def _restore(self, snapshot: EditorSnapshot) -> None:
        self._clusters = list(snapshot.clusters)
        self._cursor = max(0, min(snapshot.cursor, len(self._clusters)))


def _cluster_kind(cluster: str) -> str:
    if cluster == "\n":
        return "newline"
    if cluster.isspace():
        return "space"
    if cluster.isalnum() or cluster == "_":
        return "word"
    return "punctuation"
