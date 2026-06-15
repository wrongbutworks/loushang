from __future__ import annotations

from dataclasses import dataclass

from loushang.tui.completion_models import CompletionProvider


@dataclass(frozen=True, slots=True)
class CommandPaletteItem:
    value: str
    label: str = ""
    description: str = ""
    disabled: bool = False

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
