from __future__ import annotations

from dataclasses import dataclass

from loushang.tui.core import RenderConstraints, RenderResult


@dataclass(frozen=True, slots=True)
class DialogAction:
    label: str
    intent: object
    kind: str = "default"


@dataclass(slots=True)
class Dialog:
    title: str
    body: object | str | None = None
    actions: list[DialogAction] | tuple[DialogAction, ...] = ()
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        return None

    def editor_input_target(self) -> object | None:
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([], constraints=constraints)


@dataclass(slots=True)
class ConfirmDialog(Dialog):
    confirm_label: str = "Confirm"
    cancel_label: str = "Cancel"
    close_on_confirm: bool = True
