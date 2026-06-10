from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from loushang.tui.core import RenderConstraints, RenderResult


@dataclass(frozen=True, slots=True)
class FormValidationResult:
    errors: dict[str, str]

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class FormRow:
    field_id: str
    control: object
    validator: Callable[[object], str | None] | None = None
    value_getter: Callable[[object], object] | None = None
    error: str = ""


@dataclass(slots=True)
class Form:
    rows: list[FormRow] | tuple[FormRow, ...]
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def focus_next(self, wrap: bool = True) -> bool:
        return False

    def focus_previous(self, wrap: bool = True) -> bool:
        return False

    def handle_input(self, event: object) -> object:
        return None

    def editor_input_target(self) -> object | None:
        return None

    def values(self) -> dict[str, object]:
        return {}

    def validate(self) -> FormValidationResult:
        return FormValidationResult(errors={})

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([], constraints=constraints)
