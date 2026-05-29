from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class CompletionItem:
    value: str
    label: str = ""
    description: str = ""

    def display_label(self) -> str:
        return self.label or self.value


@dataclass(frozen=True, slots=True)
class CompletionSuggestions:
    prefix: str
    items: tuple[CompletionItem, ...]
    group: str = ""
    exclusive: bool = False


@dataclass(frozen=True, slots=True)
class CompletionApplication:
    lines: tuple[str, ...]
    cursor_line: int
    cursor_col: int


@dataclass(frozen=True, slots=True)
class CompletionProvider:
    items: tuple[CompletionItem, ...] = ()

    def complete(self, prefix: str) -> tuple[CompletionItem, ...]:
        needle = prefix.lower().strip()
        if not needle:
            return self.items
        return tuple(item for item in self.items if _completion_matches(item, needle))

    def get_suggestions(
        self,
        lines: tuple[str, ...],
        cursor_line: int,
        cursor_col: int,
        *,
        force: bool = False,
    ) -> CompletionSuggestions | None:
        del force
        if cursor_line < 0 or cursor_line >= len(lines):
            return None
        prefix = _completion_prefix_from_line(lines[cursor_line], cursor_col)
        if not prefix:
            return None
        items = self.complete(prefix)
        if not items:
            return None
        return CompletionSuggestions(prefix=prefix, items=items)

    def apply_completion(
        self,
        lines: tuple[str, ...],
        cursor_line: int,
        cursor_col: int,
        item: CompletionItem,
        prefix: str,
    ) -> CompletionApplication:
        line = lines[cursor_line]
        before = line[: max(0, cursor_col - len(prefix))]
        after = line[cursor_col:]
        suffix = " " if _is_slash_command_completion(before, prefix, item.value) else ""
        if suffix and after[:1].isspace():
            suffix = ""
        new_lines = list(lines)
        new_lines[cursor_line] = f"{before}{item.value}{suffix}{after}"
        return CompletionApplication(
            lines=tuple(new_lines),
            cursor_line=cursor_line,
            cursor_col=len(before) + len(item.value) + len(suffix),
        )


@dataclass(frozen=True, slots=True)
class CommandPaletteItem:
    value: str
    label: str = ""
    description: str = ""

    def display_label(self) -> str:
        return self.label or self.value


@dataclass(frozen=True, slots=True)
class CommandPalette:
    items: tuple[CommandPaletteItem, ...]
    title: str = "Commands"

    @classmethod
    def from_completion_provider(cls, provider: CompletionProvider, *, title: str = "Commands") -> CommandPalette:
        return cls(
            tuple(
                CommandPaletteItem(value=item.value, label=item.display_label(), description=item.description)
                for item in provider.items
            ),
            title=title,
        )


@dataclass(frozen=True, slots=True)
class InfoPanel:
    title: str
    text: str
    footer: str = ""

    @classmethod
    def from_text(cls, *, title: str, text: str, footer: str = "") -> InfoPanel:
        return cls(title=title, text=text, footer=footer)

    @property
    def lines(self) -> tuple[str, ...]:
        return tuple(self.text.splitlines())

    def plain_text(self) -> str:
        parts = [self.title, self.text]
        if self.footer:
            parts.append(self.footer)
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class SettingItem:
    id: str
    label: str
    enabled: bool = False
    description: str = ""
    current_value: str = ""
    values: tuple[str, ...] = ()
    submenu: Callable[[str, Callable[[str | None], None]], Any] | None = None


@dataclass(frozen=True, slots=True)
class SettingsList:
    items: tuple[SettingItem, ...]

    def set_enabled(self, item_id: str, enabled: bool) -> SettingsList:
        return SettingsList(tuple(replace(item, enabled=enabled) if item.id == item_id else item for item in self.items))

    def toggle(self, item_id: str) -> SettingsList:
        for item in self.items:
            if item.id == item_id:
                return self.set_enabled(item_id, not item.enabled)
        return self


@dataclass(frozen=True, slots=True)
class SettingsListRenderer:
    title: str = "Settings"

    def render(self, settings: SettingsList) -> tuple[tuple[str, str], ...]:
        lines = [self.title]
        for index, item in enumerate(settings.items):
            prefix = ">" if index == 0 else " "
            check = "[x]" if item.enabled else "[ ]"
            suffix = f" - {item.description}" if item.description else ""
            lines.append(f"{prefix} {check} {item.label}{suffix}")
        return tuple(("", line + ("\n" if index < len(lines) - 1 else "")) for index, line in enumerate(lines))


def _completion_matches(item: CompletionItem, needle: str) -> bool:
    if " " in needle:
        command, argument = needle.split(None, 1)
        return _command_argument_matches(item, command, argument.strip())

    haystacks = (item.value.lower(), item.display_label().lower(), item.description.lower())
    if needle.startswith("/"):
        return any(haystack.startswith(needle) for haystack in haystacks[:2])
    if any(needle in haystack for haystack in haystacks):
        return True
    words = [word for word in needle.split() if word]
    return bool(words) and all(any(word in haystack for haystack in haystacks) for word in words)


def _completion_prefix_from_line(line: str, cursor_col: int) -> str:
    text_before_cursor = line[:cursor_col]
    if text_before_cursor.startswith("/"):
        return text_before_cursor
    start = len(text_before_cursor)
    while start > 0:
        value = text_before_cursor[start - 1]
        if value.isspace():
            break
        start -= 1
    return text_before_cursor[start:]


def _is_slash_command_completion(before: str, prefix: str, value: str) -> bool:
    return not before.strip() and prefix.startswith("/") and value.startswith("/") and " " not in value


def _command_argument_matches(item: CompletionItem, command: str, argument: str) -> bool:
    value = item.value.lower()
    normalized_command = command.lower()
    if not value.startswith(f"{normalized_command} "):
        return False
    if not argument:
        return True
    argument = argument.lower()
    tail = value[len(normalized_command) :].strip()
    label = item.display_label().lower()
    return _argument_matches_text(argument, tail) or _argument_matches_text(argument, label)


def _argument_matches_text(argument: str, text: str) -> bool:
    segments = [segment for segment in text.replace("/", " ").split() if segment]
    if any(segment.startswith(argument) for segment in segments):
        return True
    return len(argument) >= 3 and any(argument in segment for segment in segments)
