from __future__ import annotations

from dataclasses import dataclass


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
