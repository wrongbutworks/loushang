from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.keybindings import normalize_key_id
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import style_text
from loushang.tui.ui_parts.widgets.textarea import TextArea

__all__ = ["QuestionDialog"]

_FocusSlot = Literal["body", "actions"]
_Action = Literal["submit", "cancel"]


@dataclass(init=False, slots=True)
class QuestionDialog:
    title: str
    question: str
    placeholder: str
    help_text: str
    error: str
    height: int
    confirm_label: str
    cancel_label: str
    required: bool
    required_message: str
    validator: Callable[[str], str | None] | None
    close_on_submit: bool
    close_on_cancel: bool
    submit_key: str
    theme: ThemeResolver | None
    focused: bool
    _reserved_submit_keys: ClassVar[frozenset[str]] = frozenset(
        {"enter", "shift+enter", "alt+enter", "ctrl+j", "escape", "ctrl+c", "tab", "shift+tab"}
    )
    _text_area: TextArea = field(init=False, repr=False)
    _focus_slot: _FocusSlot = field(default="body", init=False, repr=False)
    _active_action: _Action = field(default="submit", init=False, repr=False)
    _pending_submit: bool = field(default=False, init=False, repr=False)

    def __init__(
        self,
        title: str,
        question: str = "",
        value: str = "",
        placeholder: str = "",
        help_text: str = "",
        error: str = "",
        height: int = 4,
        confirm_label: str = "Submit",
        cancel_label: str = "Cancel",
        required: bool = False,
        required_message: str = "Answer required",
        validator: Callable[[str], str | None] | None = None,
        close_on_submit: bool = True,
        close_on_cancel: bool = True,
        submit_key: str = "ctrl+enter",
        theme: ThemeResolver | None = None,
        focused: bool = False,
    ) -> None:
        normalized_submit = normalize_key_id(submit_key)
        if normalized_submit in self._reserved_submit_keys:
            raise ValueError(f"submit_key is reserved for QuestionDialog: {submit_key!r}")
        self.title = title
        self.question = question
        self.placeholder = placeholder
        self.help_text = help_text
        self.error = error
        self.height = max(1, height)
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label
        self.required = required
        self.required_message = required_message
        self.validator = validator
        self.close_on_submit = close_on_submit
        self.close_on_cancel = close_on_cancel
        self.submit_key = normalized_submit
        self.theme = theme
        self.focused = focused
        self._focus_slot = "body"
        self._active_action = "submit"
        self._pending_submit = False
        self._text_area = TextArea(
            value=value,
            placeholder=placeholder,
            help_text=help_text,
            error=error,
            height=self.height,
            on_submit=self._mark_pending_submit,
            theme=theme,
            focused=focused,
        )

    @property
    def value(self) -> str:
        return self._text_area.value

    def set_text(self, text: str) -> None:
        self.error = ""
        self._text_area.set_text(text)
        self._sync_text_area_detail()

    def clear(self) -> None:
        self.error = ""
        self._text_area.clear()
        self._sync_text_area_detail()

    def focus(self) -> None:
        self.focused = True
        self._focus_slot = "body"
        self._text_area.focus()

    def blur(self) -> None:
        self.focused = False
        self._text_area.blur()

    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") != "key":
            return self._delegate_body_input(event)
        key = normalize_key_id(getattr(event, "key", ""))
        if key in {"escape", "ctrl+c"}:
            return self._cancel()
        return self._delegate_body_input(event)

    def editor_input_target(self) -> object | None:
        if self._focus_slot != "body":
            return None
        return self._text_area.editor_input_target()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        title = truncate_to_width(self.title, max_width=autowrap_safe_width(constraints.width), ellipsis="")
        return RenderResult.from_lines(
            [RenderLine(style_text(title, self.theme, "widget.question.title"))],
            constraints=constraints,
        )

    def _mark_pending_submit(self, _value: str) -> None:
        self._pending_submit = True

    def _submit_current_value(self) -> object:
        from loushang.tui.input import InputIntent

        submit = InputIntent(kind="question_submit", text=self.value)
        if not self.close_on_submit:
            return submit
        return (submit, InputIntent(kind="surface_close"))

    def _cancel(self) -> object:
        from loushang.tui.input import InputIntent

        cancel = InputIntent(kind="question_cancel")
        if not self.close_on_cancel:
            return cancel
        return (cancel, InputIntent(kind="surface_close"))

    def _sync_text_area_detail(self) -> None:
        self._text_area.error = self.error
        self._text_area.help_text = "" if self.error else self.help_text

    def _delegate_body_input(self, event: object) -> object:
        if self._focus_slot != "body":
            return None
        self._pending_submit = False
        consumed = self._text_area.handle_input(event, keybindings={"tui.input.submit": (self.submit_key,)})
        if self._pending_submit:
            return self._submit_current_value()
        if consumed:
            return True
        return None
