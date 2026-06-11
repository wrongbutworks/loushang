# TUI Widgets P1C QuestionDialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable `QuestionDialog` widget that asks a human-readable question, collects a multi-line answer, and returns structured submit/cancel intents without touching `Composer`.

**Architecture:** Implement `QuestionDialog` as one focused widget module that composes the existing `TextArea`. The dialog owns local focus between body and actions, catches cancel keys before body delegation, captures submit through `TextArea(on_submit=...)`, validates synchronously, and renders bounded title/question/body/action rows with stable theme tokens.

**Tech Stack:** Python 3.11+, dataclasses with slots, existing `TextArea`, `InputIntent`, `normalize_key_id`, `RenderResult`, `cell_width` helpers, widget theme helpers, pytest, Ruff.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-11-tui-widgets-p1c-question-dialog-design.md`
- Existing patterns:
  - `src/loushang/tui/ui_parts/widgets/dialog.py`
  - `src/loushang/tui/ui_parts/widgets/textarea.py`
  - `src/loushang/tui/ui_parts/widgets/form.py`
  - `src/loushang/tui/input.py`
  - `src/loushang/tui/keybindings.py`
  - `tests/tui/test_widgets_foundation.py`
  - `tests/tui/test_widgets_textarea.py`
  - `tests/tui/test_widgets_hardening.py`
  - `examples/tui/47_widgets_textarea.py`

## File Structure

Create:

- `src/loushang/tui/ui_parts/widgets/question_dialog.py`
  - Owns the public `QuestionDialog` class.
  - Owns body/action focus state, active action state, submit-key validation, pending-submit capture, validation, intent construction, cursor offsetting, and bounded rendering.
- `tests/tui/test_widgets_question_dialog.py`
  - Focused tests for public exports, value ownership, input handling, validation, editor target routing, rendering, theme tokens, docs example importability.
- `examples/tui/48_widgets_question_dialog.py`
  - Small runnable modal-style question dialog example.

Modify:

- `src/loushang/tui/input.py`
  - Add `question_submit` and `question_cancel` to `InputIntentKind`.
- `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export `QuestionDialog`.
- `src/loushang/tui/ui_parts/__init__.py`
  - Re-export `QuestionDialog`.
- `src/loushang/tui/__init__.py`
  - Re-export `QuestionDialog`.
- `tests/tui/test_widgets_hardening.py`
  - Add `QuestionDialog` to small-constraint coverage only if the focused render tests do not already cover the same constraints clearly.
- `docs/en/reference/tui-widgets.md`
  - Add P1C QuestionDialog entry, usage snippet, theme tokens, planned catalog rename, and example link.
- `docs/zh-CN/reference/tui-widgets.md`
  - Mirror the English reference update.

Do not modify:

- `InputRouter`, `SurfaceHost`, `Composer`, `Dialog`, `ConfirmDialog`, `Form`, `TextArea`, or global `DEFAULT_KEYBINDINGS`.

---

### Task 1: Add Failing API, Export, And Intent Tests

**Files:**
- Create: `tests/tui/test_widgets_question_dialog.py`
- Modify later: `src/loushang/tui/input.py`
- Modify later: public export modules

- [ ] **Step 1: Create the focused test file with helpers**

Use the same helper style as adjacent widget tests:

```python
from __future__ import annotations

import runpy
from typing import Any

import pytest

from loushang.tui import (
    InputEvent,
    QuestionDialog,
    RenderConstraints,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import QuestionDialog as UiQuestionDialog
from loushang.tui.ui_parts.widgets import QuestionDialog as WidgetQuestionDialog


def render_result(part: Any, *, width: int = 40, height: int = 8):
    return part.render(RenderConstraints(width=width, max_height=height))


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(line.text for line in render_result(part, width=width, height=height).lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def intent_tuple(intent: object) -> tuple[str, str, str]:
    return (getattr(intent, "kind", ""), getattr(intent, "text", ""), getattr(intent, "note", ""))


def intent_tuples(intents: object) -> tuple[tuple[str, str, str], ...]:
    if isinstance(intents, tuple):
        return tuple(intent_tuple(intent) for intent in intents)
    return (intent_tuple(intents),)
```

- [ ] **Step 2: Add failing export and value ownership tests**

```python
def test_question_dialog_is_reexported_from_public_modules() -> None:
    assert QuestionDialog is UiQuestionDialog
    assert QuestionDialog is WidgetQuestionDialog


def test_question_dialog_accepts_initial_value_but_value_is_text_area_backed() -> None:
    dialog = QuestionDialog(title="Ask", question="Details?", value="alpha\nbeta")

    assert dialog.value == "alpha\nbeta"
    with pytest.raises(AttributeError):
        dialog.value = "changed"  # type: ignore[misc]

    dialog.set_text("changed")
    assert dialog.value == "changed"

    dialog.clear()
    assert dialog.value == ""
```

- [ ] **Step 3: Add failing basic intent tests**

```python
def test_question_dialog_body_submit_returns_answer_and_close_intents() -> None:
    dialog = QuestionDialog(title="Ask", value="ship it")
    dialog.focus()

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="ctrl+enter"))) == (
        ("question_submit", "ship it", ""),
        ("surface_close", "", ""),
    )


def test_question_dialog_cancel_returns_cancel_and_close_intents() -> None:
    dialog = QuestionDialog(title="Ask")
    dialog.focus()

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="escape"))) == (
        ("question_cancel", "", ""),
        ("surface_close", "", ""),
    )
```

- [ ] **Step 4: Run the focused tests to verify they fail**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py -q
```

Expected: FAIL during import because `QuestionDialog` does not exist.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/tui/test_widgets_question_dialog.py
git commit -m "test(tui): add question dialog api tests"
```

---

### Task 2: Implement Skeleton, Public Exports, And Intent Kinds

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/question_dialog.py`
- Modify: `src/loushang/tui/input.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_question_dialog.py`

- [ ] **Step 1: Add `question_submit` and `question_cancel` to `InputIntentKind`**

In `src/loushang/tui/input.py`, extend the literal:

```python
InputIntentKind = Literal[
    ...
    "dialog_confirm",
    "dialog_cancel",
    "question_submit",
    "question_cancel",
    "consumed",
]
```

- [ ] **Step 2: Create `question_dialog.py` with the initial public API**

Use `init=False` so `value` can be an initializer argument while remaining a read-only property:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import CursorDeclaration, RenderConstraints, RenderLine, RenderResult
from loushang.tui.input import InputIntent
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
```

- [ ] **Step 3: Implement initializer, text methods, focus methods, and minimal intent helpers**

```python
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

    def _mark_pending_submit(self, _value: str) -> None:
        self._pending_submit = True

    def _submit_current_value(self) -> object:
        submit = InputIntent(kind="question_submit", text=self.value)
        if not self.close_on_submit:
            return submit
        return (submit, InputIntent(kind="surface_close"))

    def _cancel(self) -> object:
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
```

These helpers are intentionally validation-free in Task 2 so the first API and
intent tests can pass. Task 4 replaces `_submit_current_value()` with the
validation-aware version.

- [ ] **Step 4: Implement minimal `handle_input()`, `editor_input_target()`, and render placeholder**

Minimal behavior can return intents and enough render output for object usability; Task 4 will harden rendering:

```python
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
        return RenderResult.from_lines([RenderLine(style_text(title, self.theme, "widget.question.title"))], constraints=constraints)
```

- [ ] **Step 5: Add public exports**

Update all three export layers with the import pattern each file already uses.

In `src/loushang/tui/ui_parts/widgets/__init__.py`:

```python
from .question_dialog import QuestionDialog as QuestionDialog
```

Add `"QuestionDialog"` to `widgets.__all__`.

In `src/loushang/tui/ui_parts/__init__.py`:

```python
from .widgets import QuestionDialog as QuestionDialog
```

Add `"QuestionDialog"` to `ui_parts.__all__`.

In `src/loushang/tui/__init__.py`, add `QuestionDialog` to the existing
`from loushang.tui.ui_parts import (...)` block and add `"QuestionDialog"` to
top-level `__all__`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py -q
```

Expected: Task 1 tests PASS; later behavior/render tests not yet written.

- [ ] **Step 7: Commit**

```bash
git add src/loushang/tui/input.py src/loushang/tui/ui_parts/widgets/question_dialog.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
git commit -m "feat(tui): add question dialog skeleton"
```

---

### Task 3: Add Failing Input, Focus, Submit-Key, And Validation Tests

**Files:**
- Modify: `tests/tui/test_widgets_question_dialog.py`

- [ ] **Step 1: Add body submit, newline, and close behavior tests**

```python
def test_question_dialog_body_submit_can_keep_surface_open() -> None:
    dialog = QuestionDialog(title="Ask", value="draft", close_on_submit=False)
    dialog.focus()

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="ctrl+enter"))) == (
        ("question_submit", "draft", ""),
    )


def test_question_dialog_enter_inserts_newline_and_does_not_submit() -> None:
    dialog = QuestionDialog(title="Ask", value="alpha")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="enter")) is True

    assert dialog.value == "alpha\n"


def test_question_dialog_cancel_can_keep_surface_open_and_bypasses_text_area() -> None:
    dialog = QuestionDialog(title="Ask", value="draft", close_on_cancel=False)
    dialog.focus()

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="ctrl+c"))) == (
        ("question_cancel", "", ""),
    )
    assert dialog.value == "draft"
```

- [ ] **Step 2: Add focus traversal and action row tests**

```python
def test_question_dialog_tab_moves_between_body_and_actions_editor_target() -> None:
    dialog = QuestionDialog(title="Ask", value="")
    dialog.focus()

    assert dialog.editor_input_target() is not None
    assert dialog.handle_input(InputEvent(kind="key", key="tab")) is True
    assert dialog.editor_input_target() is None
    assert dialog.handle_input(InputEvent(kind="key", key="shift+tab")) is True
    assert dialog.editor_input_target() is not None


def test_question_dialog_action_row_defaults_to_submit_and_can_toggle_to_cancel() -> None:
    dialog = QuestionDialog(title="Ask", value="done")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="tab")) is True
    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="enter"))) == (
        ("question_submit", "done", ""),
        ("surface_close", "", ""),
    )

    dialog = QuestionDialog(title="Ask", value="done")
    dialog.focus()
    dialog.handle_input(InputEvent(kind="key", key="tab"))
    assert dialog.handle_input(InputEvent(kind="key", key="right")) is True
    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="space"))) == (
        ("question_cancel", "", ""),
        ("surface_close", "", ""),
    )


def test_question_dialog_action_row_printable_space_activates_active_action() -> None:
    dialog = QuestionDialog(title="Ask", value="done")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="tab")) is True
    assert intent_tuples(dialog.handle_input(InputEvent(kind="text", text=" "))) == (
        ("question_submit", "done", ""),
        ("surface_close", "", ""),
    )
```

- [ ] **Step 3: Add submit-key validation tests**

```python
@pytest.mark.parametrize("key", ["enter", "shift+enter", "alt+enter", "ctrl+j", "escape", "esc", "ctrl+c", "tab", "shift+tab"])
def test_question_dialog_rejects_reserved_submit_keys(key: str) -> None:
    with pytest.raises(ValueError):
        QuestionDialog(title="Ask", submit_key=key)


@pytest.mark.parametrize("key", ["s", "space", " "])
def test_question_dialog_rejects_text_event_submit_keys(key: str) -> None:
    with pytest.raises(ValueError):
        QuestionDialog(title="Ask", submit_key=key)


def test_question_dialog_accepts_custom_non_reserved_submit_key() -> None:
    dialog = QuestionDialog(title="Ask", value="ok", submit_key="ctrl+s")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="ctrl+enter")) is None
    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="ctrl+s"))) == (
        ("question_submit", "ok", ""),
        ("surface_close", "", ""),
    )
```

- [ ] **Step 4: Add validation tests**

```python
def test_question_dialog_required_validation_keeps_open_and_renders_error() -> None:
    dialog = QuestionDialog(title="Ask", required=True, required_message="Tell me")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="ctrl+enter")) is True

    assert "Tell me" in plain_lines(dialog, width=30, height=6)


def test_question_dialog_custom_validator_error_then_success() -> None:
    dialog = QuestionDialog(title="Ask", value="no", validator=lambda value: "Too short" if len(value) < 3 else None)
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="ctrl+enter")) is True
    assert "Too short" in plain_lines(dialog, width=30, height=6)

    dialog.set_text("yes")

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="ctrl+enter"))) == (
        ("question_submit", "yes", ""),
        ("surface_close", "", ""),
    )
    assert "Too short" not in plain_lines(dialog, width=30, height=6)
```

- [ ] **Step 5: Run focused tests to verify failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py -q
```

Expected: FAIL on unimplemented focus/action/validation behavior.

- [ ] **Step 6: Commit the failing tests**

```bash
git add tests/tui/test_widgets_question_dialog.py
git commit -m "test(tui): cover question dialog input behavior"
```

---

### Task 4: Implement Input, Focus, Submit Capture, And Validation

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/question_dialog.py`
- Test: `tests/tui/test_widgets_question_dialog.py`

- [ ] **Step 1: Implement focus traversal and action activation**

Add helpers:

```python
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
```

- [ ] **Step 2: Implement deterministic submit/cancel intent construction**

```python
    def _submit_current_value(self) -> object:
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
```

- [ ] **Step 3: Implement body delegation with pending-submit capture**

```python
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
```

- [ ] **Step 4: Replace `handle_input()` with full key handling**

```python
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
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py -q
```

Expected: all current question dialog tests PASS.

- [ ] **Step 6: Run adjacent input/editor tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py tests/tui/test_widgets_foundation.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/question_dialog.py
git commit -m "feat(tui): handle question dialog input"
```

---

### Task 5: Add Failing Render, Cursor, Constraint, And Theme Tests

**Files:**
- Modify: `tests/tui/test_widgets_question_dialog.py`
- Optionally modify later: `tests/tui/test_widgets_hardening.py`

- [ ] **Step 1: Add render structure and cursor offset tests**

```python
def test_question_dialog_renders_title_question_body_actions_and_cursor_offset() -> None:
    dialog = QuestionDialog(title="Ask", question="Why?", value="alpha\nbeta", height=3)
    dialog.focus()

    result = render_result(dialog, width=30, height=7)

    assert tuple(strip_control_sequences(line.text) for line in result.lines) == (
        "Ask",
        "Why?",
        "alpha",
        "beta",
        "",
        "  [Submit]  [Cancel]",
    )
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (3, len("beta"))
```

- [ ] **Step 2: Add action-row focus render tests**

```python
def test_question_dialog_action_row_marks_active_action_without_layout_shift() -> None:
    dialog = QuestionDialog(title="Ask", value="ok")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="tab")) is True
    assert plain_lines(dialog, width=30, height=6)[-1] == "> [Submit]  [Cancel]"

    assert dialog.handle_input(InputEvent(kind="key", key="right")) is True
    assert plain_lines(dialog, width=30, height=6)[-1] == "  [Submit]> [Cancel]"
```

- [ ] **Step 3: Add height and width constraint tests**

```python
def test_question_dialog_respects_width_and_height_constraints() -> None:
    dialog = QuestionDialog(
        title="Very long title",
        question="Very long question",
        value="Very long answer",
        help_text="Very long help",
    )
    dialog.focus()

    lines = render_lines(dialog, width=8, height=4)

    assert len(lines) <= 4
    assert_widths_within(lines, 8)
    assert plain_lines(dialog, width=8, height=1) == ("Very lo",)
```

- [ ] **Step 4: Add action omission and cursor omission tests for tight height**

```python
def test_question_dialog_omits_actions_when_body_needs_final_row() -> None:
    dialog = QuestionDialog(title="Ask", question="Why?", value="answer", height=3)
    dialog.focus()

    assert plain_lines(dialog, width=20, height=3) == ("Ask", "Why?", "answer")


def test_question_dialog_omits_cursor_when_body_cannot_render() -> None:
    dialog = QuestionDialog(title="Ask", question="Why?", value="answer")
    dialog.focus()

    result = render_result(dialog, width=20, height=2)

    assert tuple(strip_control_sequences(line.text) for line in result.lines) == ("Ask", "Why?")
    assert result.cursor is None
```

- [ ] **Step 5: Add theme token tests**

```python
def test_question_dialog_themes_title_question_and_action_rows() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.question.title": {"bold": True},
            "widget.question.text": {"color": "cyan"},
            "widget.question.action": {"color": "yellow"},
            "widget.question.focus": {"color": "green"},
            "widget.textArea.text": {"color": "magenta"},
        }
    )
    dialog = QuestionDialog(title="Ask", question="Why?", value="ok", theme=theme)

    raw = render_lines(dialog, width=30, height=6)

    assert raw[0].startswith("\x1b[1m")
    assert raw[1].startswith("\x1b[36m")
    assert raw[2].startswith("\x1b[35m")
    assert raw[-1].startswith("\x1b[33m")

    dialog.focus()
    dialog.handle_input(InputEvent(kind="key", key="tab"))
    focused = render_lines(dialog, width=30, height=6)
    assert focused[-1].startswith("\x1b[32m")
```

- [ ] **Step 6: Run focused tests to verify failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py -q
```

Expected: FAIL on incomplete render behavior.

- [ ] **Step 7: Commit the failing tests**

```bash
git add tests/tui/test_widgets_question_dialog.py
git commit -m "test(tui): cover question dialog rendering"
```

---

### Task 6: Implement Deterministic Rendering

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/question_dialog.py`
- Test: `tests/tui/test_widgets_question_dialog.py`

- [ ] **Step 1: Add row rendering helpers**

```python
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
        return RenderLine(style_text(truncate_to_width(self._action_text(), max_width=width, ellipsis=""), self.theme, token))
```

- [ ] **Step 2: Implement height-budgeted render**

Follow the spec ordering:

```python
    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = autowrap_safe_width(constraints.width)
        lines: list[RenderLine] = []
        cursor: CursorDeclaration | None = None

        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)

        lines.append(self._title_line(width))
        if self.question and len(lines) < constraints.max_height:
            lines.append(self._question_line(width))

        remaining = constraints.max_height - len(lines)
        if remaining <= 0:
            return RenderResult.from_lines(lines[: constraints.max_height], constraints=constraints)

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

        return RenderResult.from_lines(lines[: constraints.max_height], constraints=constraints, cursor=cursor)
```

If tight-height tests require title/question/body to win over actions, adjust only `reserve_action` and `body_height`; do not add a general layout engine.

- [ ] **Step 3: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py -q
```

Expected: PASS.

- [ ] **Step 4: Run adjacent hardening tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/question_dialog.py tests/tui/test_widgets_question_dialog.py tests/tui/test_widgets_hardening.py
git commit -m "feat(tui): render question dialog"
```

---

### Task 7: Add Docs, Example, And Import Coverage

**Files:**
- Create: `examples/tui/48_widgets_question_dialog.py`
- Modify: `tests/tui/test_widgets_question_dialog.py`
- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`

- [ ] **Step 1: Add example import test**

```python
def test_widgets_question_dialog_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/48_widgets_question_dialog.py", run_name="__test__")

    assert callable(namespace["build_app"])
```

- [ ] **Step 2: Create the runnable example**

Base it on `examples/tui/47_widgets_textarea.py`, but route the dialog directly:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    FocusableMixin,
    InputEvent,
    QuestionDialog,
    RenderConstraints,
    RenderLine,
    RenderResult,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class QuestionDialogApp(FocusableMixin):
    dialog: QuestionDialog = field(
        default_factory=lambda: QuestionDialog(
            title="Add note",
            question="What should be remembered?",
            placeholder="Write a multi-line answer",
            help_text="Enter adds a line. Ctrl+Enter submits.",
            required=True,
        )
    )
    message: str = "Escape cancels. Press q to quit."

    def __post_init__(self) -> None:
        super().__init__()
        self.dialog.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        body = self.dialog.render(RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 2)))
        rows = [
            *body.lines,
            RenderLine(""),
            RenderLine(truncate_to_width(self.message, max_width=constraints.width, ellipsis="")),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=body.cursor)

    def handle_input(self, event: Any) -> object:
        result = self.dialog.handle_input(event)
        intents = result if isinstance(result, tuple) else (() if result is None else (result,))
        for intent in intents:
            if getattr(intent, "kind", "") == "question_submit":
                self.message = f"Submitted: {getattr(intent, 'text', '')}"
            elif getattr(intent, "kind", "") == "question_cancel":
                self.message = "Cancelled"
        return result


def build_app() -> Tui:
    tui = Tui()
    app = QuestionDialogApp()
    tui.add_child(app)
    tui.set_focus(app)
    return tui


async def main() -> int:
    tui = build_app()

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if event.kind == "text" and "q" in event.text.lower():
            return context.stop(0)
        context.tui.handle_input(event)
        return TuiInputResult()

    return await TuiRunner(tui).run(on_input=on_input)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 3: Update English docs**

In `docs/en/reference/tui-widgets.md`:

- Add a `P1C Dialog Inputs` section after P1B.
- Add `QuestionDialog` to the widget table.
- Document `enter` newline, `ctrl+enter` submit, `escape` / `ctrl+c` cancel, and intent-only behavior.
- Add theme tokens `widget.question.title`, `widget.question.text`, `widget.question.action`, and `widget.question.focus`.
- Replace planned `PromptDialog` mention with `QuestionDialog` now implemented; leave `Popover`, `TreeView`, `Toast` planned.
- Add the example link.

Use this snippet:

```python
from loushang.tui import QuestionDialog

dialog = QuestionDialog(
    title="Add note",
    question="What should be remembered?",
    placeholder="Write a multi-line answer",
    required=True,
)
dialog.focus()
```

- [ ] **Step 4: Update Chinese docs**

Mirror the English content in `docs/zh-CN/reference/tui-widgets.md`. Use `QuestionDialog` literally and avoid reintroducing `PromptDialog`.

- [ ] **Step 5: Run docs/example import test**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py::test_widgets_question_dialog_example_imports -q
```

Expected: PASS.

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add examples/tui/48_widgets_question_dialog.py tests/tui/test_widgets_question_dialog.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md
git commit -m "docs(tui): document question dialog widget"
```

---

### Task 8: Final Verification And Cleanup

**Files:**
- Review all changed files.

- [ ] **Step 1: Run focused QuestionDialog tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full TUI tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS.

- [ ] **Step 4: Run Ruff on touched surfaces**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/48_widgets_question_dialog.py docs
```

Expected: PASS.

- [ ] **Step 5: Inspect git diff**

Run:

```bash
git diff --stat origin/main...HEAD
git diff --check
```

Expected: no whitespace errors; diff contains only spec/plan, QuestionDialog widget, exports, tests, docs, and example.

- [ ] **Step 6: Commit any final fixes**

If verification required small fixes:

```bash
git add <fixed-files>
git commit -m "fix(tui): finalize question dialog widget"
```

If no fixes were needed, do not create an empty commit.

---

## Success Criteria

- `QuestionDialog` is exported from `loushang.tui`, `loushang.tui.ui_parts`, and `loushang.tui.ui_parts.widgets`.
- `QuestionDialog` owns a multi-line internal `TextArea`; `value` is read-only and backed by that text area.
- `enter` inserts newline; default `ctrl+enter` submits; custom non-reserved `submit_key` works.
- Reserved submit keys raise `ValueError`.
- `escape` and `ctrl+c` cancel before body delegation.
- `tab` / `shift+tab` traverse body/actions; action row defaults to submit and can toggle to cancel.
- Required and custom validation keep the dialog open and render visible error text.
- Submit and cancel return structured `InputIntent` values with optional `surface_close`.
- `editor_input_target()` returns the text area target only while body focus is active.
- Rendering obeys width/height constraints, preserves cursor row offsets, and styles question tokens deterministically.
- Docs and example import tests pass.
- Focused, adjacent, full TUI, and Ruff verification pass.
