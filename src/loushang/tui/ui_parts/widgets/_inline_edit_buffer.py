from __future__ import annotations

from dataclasses import dataclass

from loushang.tui.cell_width import grapheme_clusters


@dataclass(slots=True)
class InlineEditBuffer:
    text: str = ""
    cursor: int = 0
    selected: bool = False

    @classmethod
    def from_value(cls, value: object | None) -> InlineEditBuffer:
        text = "" if value is None else str(value)
        return cls(text=text, cursor=_grapheme_len(text), selected=True)

    def insert_text(self, text: str) -> bool:
        inserted = list(grapheme_clusters(text))
        if self.selected:
            self.replace(text)
            return True
        if not inserted:
            return False
        clusters = self._clusters()
        cursor = self._clamped_cursor()
        clusters[cursor:cursor] = inserted
        self.text = "".join(clusters)
        self.cursor = cursor + len(inserted)
        return True

    def replace(self, text: str) -> None:
        self.text = text
        self.cursor = _grapheme_len(text)
        self.selected = False

    def delete_backward(self) -> bool:
        if self.selected:
            self.replace("")
            return True
        clusters = self._clusters()
        cursor = self._clamped_cursor()
        if cursor <= 0:
            return False
        del clusters[cursor - 1]
        self.text = "".join(clusters)
        self.cursor = cursor - 1
        return True

    def delete_forward(self) -> bool:
        if self.selected:
            self.replace("")
            return True
        clusters = self._clusters()
        cursor = self._clamped_cursor()
        if cursor >= len(clusters):
            return False
        del clusters[cursor]
        self.text = "".join(clusters)
        self.cursor = cursor
        return True

    def move_left(self) -> bool:
        return self.move(-1)

    def move_right(self) -> bool:
        return self.move(1)

    def move(self, delta: int) -> bool:
        if self.selected:
            self.selected = False
            self.cursor = 0 if delta < 0 else _grapheme_len(self.text)
            return True
        next_cursor = max(0, min(_grapheme_len(self.text), self.cursor + delta))
        if next_cursor == self.cursor:
            return False
        self.cursor = next_cursor
        return True

    def move_home(self) -> bool:
        self.selected = False
        if self.cursor == 0:
            return False
        self.cursor = 0
        return True

    def move_end(self) -> bool:
        self.selected = False
        end = _grapheme_len(self.text)
        if self.cursor == end:
            return False
        self.cursor = end
        return True

    def text_before_cursor(self) -> str:
        clusters = self._clusters()
        return "".join(clusters[: self._clamped_cursor()])

    def _clusters(self) -> list[str]:
        return list(grapheme_clusters(self.text))

    def _clamped_cursor(self) -> int:
        return max(0, min(self.cursor, _grapheme_len(self.text)))


def _grapheme_len(text: str) -> int:
    return len(tuple(grapheme_clusters(text)))
