from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import (
    CursorDeclaration,
    RenderConstraints,
    RenderLine,
    RenderResult,
)
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
        kind = getattr(event, "kind", "")
        if kind == "text" and self._focus_slot == "actions" and getattr(event, "text", "") == " ":
            return self._activate_action()
        if kind != "key":
            return self._delegate_body_input(event)
        key = normalize_key_id(getattr(event, "key", ""))
        if key in {"escape", "ctrl+c"}:
            return self._cancel()
        if key in {"tab", "shift+tab"}:
            return self._focus_body() if self._focus_slot == "actions" else self._focus_actions()
        if self._focus_slot == "actions":
            if key in {"left", "right"}:
                return self._toggle_action()
            if key in {"enter", "space"}:
                return self._activate_action()
            return None
        return self._delegate_body_input(event)

    def editor_input_target(self) -> object | None:
        if self._focus_slot != "body":
            return None
        return self._text_area.editor_input_target()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = autowrap_safe_width(constraints.width)
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)

        lines = [self._title_line(width)]
        if self.question and len(lines) < constraints.max_height:
            lines.append(self._question_line(width))

        cursor: CursorDeclaration | None = None
        remaining = constraints.max_height - len(lines)
        reserve_action = remaining >= 2
        body_height = remaining - (1 if reserve_action else 0)

        if body_height > 0:
            self._sync_text_area_detail()
            body = self._text_area.render(RenderConstraints(width=constraints.width, max_height=body_height))
            body_start = len(lines)
            lines.extend(body.lines[:body_height])
            if body.cursor is not None:
                cursor = CursorDeclaration(row=body_start + body.cursor.row, column=body.cursor.column)

        if reserve_action and len(lines) < constraints.max_height:
            lines.append(self._action_line(width))

        return RenderResult.from_lines(
            lines[: constraints.max_height],
            constraints=constraints,
            cursor=cursor,
        )

    def _title_line(self, width: int) -> RenderLine:
        text = truncate_to_width(self.title, max_width=width, ellipsis="")
        return RenderLine(style_text(text, self.theme, "widget.question.title"))

    def _question_line(self, width: int) -> RenderLine:
        text = truncate_to_width(self.question, max_width=width, ellipsis="")
        return RenderLine(style_text(text, self.theme, "widget.question.text"))

    def _action_text(self) -> str:
        if self._focus_slot != "actions":
            return f"  [{self.confirm_label}]  [{self.cancel_label}]"
        if self._active_action == "submit":
            return f"> [{self.confirm_label}]  [{self.cancel_label}]"
        return f"  [{self.confirm_label}]  > [{self.cancel_label}]"

    def _action_line(self, width: int) -> RenderLine:
        token = "widget.question.focus" if self._focus_slot == "actions" else "widget.question.action"
        text = truncate_to_width(self._action_text(), max_width=width, ellipsis="")
        return RenderLine(style_text(text, self.theme, token))

    def _mark_pending_submit(self, _value: str) -> None:
        self._pending_submit = True

    def _focus_actions(self) -> bool:
        self._focus_slot = "actions"
        self._active_action = "submit"
        self._text_area.blur()
        return True

    def _focus_body(self) -> bool:
        self._focus_slot = "body"
        self._text_area.focus()
        return True

    def _toggle_action(self) -> bool:
        self._active_action = "cancel" if self._active_action == "submit" else "submit"
        return True

    def _activate_action(self) -> object:
        if self._active_action == "cancel":
            return self._cancel()
        return self._submit_current_value()

    def _submit_current_value(self) -> object:
        from loushang.tui.input import InputIntent

        error = self._validation_error()
        if error is not None:
            self.error = error
            self._sync_text_area_detail()
            return True
        self.error = ""
        self._sync_text_area_detail()
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

    def _validation_error(self) -> str | None:
        value = self.value
        if self.required and not value.strip():
            return self.required_message
        if self.validator is not None:
            return self.validator(value)
        return None

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
