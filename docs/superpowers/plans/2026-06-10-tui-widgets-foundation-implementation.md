# TUI Widgets Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first reusable `loushang.tui` widget batch: buttons, choices, fields, selection lists, forms, and modal dialogs.

**Architecture:** Keep widgets as ordinary `Renderable`/`Focusable` UI parts under a focused `ui_parts/widgets/` package. Reuse `TextInput`, `SelectionSurface`, `SurfaceHost`, `InputIntent`, `ThemeResolver`, and cell-width helpers instead of adding a new UI framework or global focus manager.

**Tech Stack:** Python 3.11+, dataclasses with slots, existing TUI render/input protocols, pytest, ruff, `uv --cache-dir .uv-cache run --extra dev`.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-10-tui-widgets-foundation-design.md`
- Framework: `src/loushang/tui/framework.py`
- Text input: `src/loushang/tui/ui_parts/text_input.py`
- Selection surface: `src/loushang/tui/surfaces.py`
- Existing basic UI parts: `src/loushang/tui/basic.py`
- Public UI part exports: `src/loushang/tui/ui_parts/__init__.py`
- Top-level TUI exports: `src/loushang/tui/__init__.py`
- Existing tests: `tests/tui/test_text_input.py`, `tests/tui/test_surfaces.py`, `tests/tui/test_render_framework.py`

## File Structure

- Create `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export P0A widget classes and helper dataclasses.
- Create `src/loushang/tui/ui_parts/widgets/_utils.py`
  - Shared width-safe rendering helpers, activation detection, callback return normalization, and focus/disabled styling helpers.
- Create `src/loushang/tui/ui_parts/widgets/button.py`
  - `Button`, `IconButton`, and `ButtonKind`.
- Create `src/loushang/tui/ui_parts/widgets/choice.py`
  - `Choice`, `Checkbox`, `Toggle`, and `RadioGroup`.
- Create `src/loushang/tui/ui_parts/widgets/field.py`
  - `TextField` wrapper around `TextInput`.
- Create `src/loushang/tui/ui_parts/widgets/selection.py`
  - `SelectList` adapter around `SelectionSurface`.
- Create `src/loushang/tui/ui_parts/widgets/form.py`
  - `FormRow`, `FormValidationResult`, and `Form`.
- Create `src/loushang/tui/ui_parts/widgets/dialog.py`
  - `Dialog`, `ConfirmDialog`, and `DialogAction`.
- Modify `src/loushang/tui/ui_parts/__init__.py`
  - Re-export stable P0A widget API.
- Modify `src/loushang/tui/__init__.py`
  - Re-export stable P0A widget API.
- Create `tests/tui/test_widgets_foundation.py`
  - P0A behavior tests. Write tests before implementation for each task.
- Create `docs/en/reference/tui-widgets.md`
  - English reference docs for P0A widgets and planned P1 catalog.
- Create `docs/zh-CN/reference/tui-widgets.md`
  - Chinese reference docs matching the English page.
- Modify `docs/en/reference/README.md`
  - Link widgets reference.
- Modify `docs/zh-CN/reference/README.md`
  - Link widgets reference.
- Create `examples/tui/43_widgets_foundation.py`
  - Keyboard-only showcase of form, fields, choices, select list, and confirm dialog.

## Shared Implementation Decisions

- Use ASCII-first rendering:
  - Focus prefix: `"> "` when focused or active, `"  "` otherwise.
  - Checkbox: `[x] Label` and `[ ] Label`.
  - Toggle: `[on ] Label` and `[off] Label`.
  - Radio: `(x) Label` and `( ) Label`.
- Focus indicators must have stable width.
- `handle_input()` may return a callback value, an `InputIntent`, a tuple of `InputIntent` values, `True`, or `None`.
- Non-editor controls activate on `InputEvent(kind="key", key="enter")`, `InputEvent(kind="key", key="space")`, or `InputEvent(kind="text", text=" ")`.
- Editable controls keep printable space as text insertion.
- `Form.editor_input_target()` delegates to the active child when that child implements `EditorInputTargetProvider`.
- `Dialog.editor_input_target()` delegates to the active body/form child when the dialog body owns active editable focus.
- Do not add new `InputIntentKind` values in this slice.

## Task 1: Widget Package Skeleton And Public Exports

**Files:**
- Create: `tests/tui/test_widgets_foundation.py`
- Create: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Create: `src/loushang/tui/ui_parts/widgets/_utils.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`

- [ ] **Step 1: Write failing import tests**

Add imports for the full P0A API and existing shared data types:

```python
from loushang.tui import Button, Checkbox, Choice, ConfirmDialog, Dialog, Form, FormRow, IconButton, InputEvent, InputIntent, RadioGroup, RenderConstraints, RenderLine, RenderResult, SelectItem, SelectList, TextField, Toggle
from loushang.tui.ui_parts import Button as UiButton
from loushang.tui.ui_parts.widgets import Button as WidgetButton
```

Add:

```python
def test_widgets_are_reexported_from_public_modules() -> None:
    assert Button is UiButton
    assert Button is WidgetButton
    assert Choice("fast", "Fast").value == "fast"
    assert callable(IconButton)
```

- [ ] **Step 2: Run red test**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_widgets_are_reexported_from_public_modules -q
```

Expected: fail with import errors for missing widget modules/classes.

- [ ] **Step 3: Add minimal skeleton classes and exports**

Create temporary minimal dataclasses with `focused`, `focus()`, `blur()`, `render()`, and `handle_input()` stubs only where needed to satisfy imports. Keep behavior minimal; later tasks add real behavior after focused tests fail.

Create `_utils.py` with:

```python
def is_activation_event(event: object) -> bool:
    return (
        (getattr(event, "kind", "") == "key" and getattr(event, "key", "") in {"enter", "space"})
        or (getattr(event, "kind", "") == "text" and getattr(event, "text", "") == " ")
    )


def callback_result(result: object) -> object:
    return True if result is None else result
```

Use `RenderResult.from_lines([], constraints=constraints)` for temporary render stubs.

- [ ] **Step 4: Run green test**

Run the same focused pytest command. Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/loushang/tui/ui_parts/__init__.py src/loushang/tui/ui_parts/widgets src/loushang/tui/__init__.py tests/tui/test_widgets_foundation.py
git commit -m "feat(tui): add widgets package exports"
```

## Task 2: Button, Checkbox, Toggle, And RadioGroup

**Files:**
- Modify: `tests/tui/test_widgets_foundation.py`
- Modify: `src/loushang/tui/ui_parts/widgets/_utils.py`
- Modify: `src/loushang/tui/ui_parts/widgets/button.py`
- Modify: `src/loushang/tui/ui_parts/widgets/choice.py`

- [ ] **Step 1: Write failing tests for buttons**

Add helpers:

```python
from loushang.tui import InputEvent, RenderConstraints, strip_control_sequences


def rendered_text(part: object, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text) for line in result.lines)
```

Add tests:

```python
def test_button_activates_from_enter_and_space_without_layout_shift() -> None:
    calls: list[str] = []
    button = Button("Save", on_press=lambda: calls.append("save"))

    assert rendered_text(button, width=12) == ("  [Save]",)
    button.focus()
    assert rendered_text(button, width=12) == ("> [Save]",)
    assert button.handle_input(InputEvent(kind="key", key="enter")) is True
    assert button.handle_input(InputEvent(kind="text", text=" ")) is True
    assert calls == ["save", "save"]


def test_button_returns_callback_value_and_ignores_disabled_activation() -> None:
    button = Button("Delete", disabled=True, on_press=lambda: "deleted")

    assert button.handle_input(InputEvent(kind="key", key="enter")) is None

    active = Button("Delete", on_press=lambda: "deleted")
    assert active.handle_input(InputEvent(kind="key", key="space")) == "deleted"
```

- [ ] **Step 2: Run button red tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_button_activates_from_enter_and_space_without_layout_shift tests/tui/test_widgets_foundation.py::test_button_returns_callback_value_and_ignores_disabled_activation -q
```

Expected: fail because `Button` render/input behavior is not implemented.

- [ ] **Step 3: Implement minimal button behavior**

In `button.py`, implement:

- `ButtonKind = Literal["default", "primary", "danger", "ghost"]`
- `Button(label: str, icon: str = "", kind: ButtonKind = "default", disabled: bool = False, on_press: Callable[[], object] | None = None, theme: ThemeResolver | None = None, theme_token: str | None = None, focused: bool = False)`
- `IconButton(icon: str, *, label: str = "", **kwargs: object) -> Button`
- width-safe one-line render using `truncate_to_width()`
- `handle_input()` using `is_activation_event()`

- [ ] **Step 4: Run button green tests**

Run the same focused pytest command. Expected: pass.

- [ ] **Step 5: Write failing tests for checkbox and toggle**

Add:

```python
def test_checkbox_toggles_from_enter_and_printable_space() -> None:
    seen: list[bool] = []
    checkbox = Checkbox("Enable cache", checked=False, on_change=seen.append)

    assert rendered_text(checkbox) == ("  [ ] Enable cache",)
    checkbox.focus()
    assert checkbox.handle_input(InputEvent(kind="key", key="enter")) is True
    assert checkbox.checked is True
    assert rendered_text(checkbox) == ("> [x] Enable cache",)
    assert checkbox.handle_input(InputEvent(kind="text", text=" ")) is True
    assert checkbox.checked is False
    assert seen == [True, False]


def test_toggle_renders_distinct_state_and_ignores_disabled_activation() -> None:
    toggle = Toggle("Auto approve", value=False)

    assert rendered_text(toggle) == ("  [off] Auto approve",)
    assert toggle.handle_input(InputEvent(kind="key", key="space")) is True
    assert toggle.value is True
    assert rendered_text(toggle) == ("  [on ] Auto approve",)

    disabled = Toggle("Auto approve", value=False, disabled=True)
    assert disabled.handle_input(InputEvent(kind="text", text=" ")) is None
    assert disabled.value is False
```

- [ ] **Step 6: Run checkbox/toggle red tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_checkbox_toggles_from_enter_and_printable_space tests/tui/test_widgets_foundation.py::test_toggle_renders_distinct_state_and_ignores_disabled_activation -q
```

Expected: fail because behavior is not implemented.

- [ ] **Step 7: Implement checkbox and toggle**

In `choice.py`, implement `Checkbox` and `Toggle` with stable one-line rendering, disabled checks, `set_checked()` for checkbox, and callback result normalization.

- [ ] **Step 8: Run checkbox/toggle green tests**

Run the same focused pytest command. Expected: pass.

- [ ] **Step 9: Write failing tests for RadioGroup**

Add:

```python
def test_radio_group_moves_active_option_and_commits_selection() -> None:
    seen: list[str] = []
    group = RadioGroup(
        [Choice("fast", "Fast"), Choice("safe", "Safe"), Choice("slow", "Slow", disabled=True)],
        value="fast",
        on_change=seen.append,
    )

    group.focus()
    assert rendered_text(group, width=20, height=4)[:2] == ("> (x) Fast", "  ( ) Safe")
    assert group.handle_input(InputEvent(kind="key", key="down")) is True
    assert group.value == "fast"
    assert rendered_text(group, width=20, height=4)[:2] == ("  (x) Fast", "> ( ) Safe")
    assert group.handle_input(InputEvent(kind="key", key="enter")) is True
    assert group.value == "safe"
    assert seen == ["safe"]
    assert group.handle_input(InputEvent(kind="key", key="down")) is True
    assert group.active_value == "fast"
```

- [ ] **Step 10: Run RadioGroup red test**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_radio_group_moves_active_option_and_commits_selection -q
```

Expected: fail because `RadioGroup` behavior is not implemented.

- [ ] **Step 11: Implement RadioGroup**

Implement `Choice` and `RadioGroup`:

- `Choice(value: str, label: str, description: str = "", disabled: bool = False)`
- track `_active_index`
- move up/down among enabled choices, wrapping
- commit on activation
- render one row per visible choice, truncating descriptions if present

- [ ] **Step 12: Run task tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py -q
```

Expected: all current widget tests pass.

- [ ] **Step 13: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/_utils.py src/loushang/tui/ui_parts/widgets/button.py src/loushang/tui/ui_parts/widgets/choice.py tests/tui/test_widgets_foundation.py
git commit -m "feat(tui): add basic choice widgets"
```

## Task 3: TextField And SelectList

**Files:**
- Modify: `tests/tui/test_widgets_foundation.py`
- Modify: `src/loushang/tui/ui_parts/widgets/field.py`
- Modify: `src/loushang/tui/ui_parts/widgets/selection.py`

- [ ] **Step 1: Write failing TextField tests**

Add:

```python
def test_text_field_delegates_editing_and_cursor_to_text_input() -> None:
    field = TextField(label="Name", value="tower", help_text="Required")
    field.focus()

    assert field.handle_input(InputEvent(kind="text", text="!")) is True
    assert field.value == "tower!"

    result = field.render(RenderConstraints(width=24, max_height=4))
    lines = tuple(strip_control_sequences(line.text) for line in result.lines)
    assert lines == ("Name", "tower!", "Required")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, len("tower!"))


def test_text_field_editor_input_target_preserves_text_input_undo() -> None:
    field = TextField(value="")
    target = field.editor_input_target()

    target.insert_text("abc")
    target.delete_backward()

    assert field.value == "ab"
    assert field.undo()
    assert field.value == "abc"


def test_text_field_inserts_printable_space_as_text() -> None:
    field = TextField(value="a")

    assert field.handle_input(InputEvent(kind="text", text=" ")) is True

    assert field.value == "a "
```

- [ ] **Step 2: Run TextField red tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_text_field_delegates_editing_and_cursor_to_text_input tests/tui/test_widgets_foundation.py::test_text_field_editor_input_target_preserves_text_input_undo tests/tui/test_widgets_foundation.py::test_text_field_inserts_printable_space_as_text -q
```

Expected: fail because `TextField` does not delegate.

- [ ] **Step 3: Implement TextField**

Wrap an inner `TextInput` and delegate:

- `value`, `set_text()`, `clear()`, `undo()`, `redo()`
- `focus()`, `blur()`
- `handle_input()`
- `editor_input_target()`
- cursor row offset by rendered label rows

- [ ] **Step 4: Run TextField green tests**

Run the same focused pytest command. Expected: pass.

- [ ] **Step 5: Write failing SelectList tests**

Add:

```python
def test_select_list_delegates_navigation_and_selection_without_default_escape_close() -> None:
    select = SelectList([SelectItem("Kimi"), SelectItem("Qwen")], max_visible=2)

    assert select.handle_input(InputEvent(kind="key", key="down")) is True
    assert select.selected_value == "Qwen"
    assert select.handle_input(InputEvent(kind="key", key="enter")) == InputIntent(kind="select", text="Qwen")
    assert select.handle_input(InputEvent(kind="key", key="escape")) is None


def test_select_list_can_emit_surface_close_for_popup_usage() -> None:
    select = SelectList([SelectItem("Kimi")], close_on_escape=True)

    assert select.handle_input(InputEvent(kind="key", key="escape")) == InputIntent(kind="surface_close")
```

- [ ] **Step 6: Run SelectList red tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_select_list_delegates_navigation_and_selection_without_default_escape_close tests/tui/test_widgets_foundation.py::test_select_list_can_emit_surface_close_for_popup_usage -q
```

Expected: fail because `SelectList` behavior is not implemented.

- [ ] **Step 7: Implement SelectList**

Implement a thin adapter that owns an internal `SelectionSurface` and delegates render, focus, blur, selected helpers, search/filter, and most input. Intercept escape when `close_on_escape=False`.

- [ ] **Step 8: Run task tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py tests/tui/test_text_input.py tests/tui/test_surfaces.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/field.py src/loushang/tui/ui_parts/widgets/selection.py tests/tui/test_widgets_foundation.py
git commit -m "feat(tui): add field and select widgets"
```

## Task 4: Form, FormRow, Validation, And Local Focus

**Files:**
- Modify: `tests/tui/test_widgets_foundation.py`
- Modify: `src/loushang/tui/ui_parts/widgets/form.py`

- [ ] **Step 1: Write failing Form tests**

Add:

```python
def test_form_tabs_between_focusable_rows_and_delegates_input() -> None:
    name = TextField(value="")
    enabled = Checkbox("Enabled")
    form = Form([FormRow("name", name), FormRow("enabled", enabled)])

    form.focus()
    assert name.focused is True
    assert form.handle_input(InputEvent(kind="text", text="a")) is True
    assert name.value == "a"
    assert form.handle_input(InputEvent(kind="key", key="tab")) is True
    assert enabled.focused is True
    assert form.handle_input(InputEvent(kind="text", text=" ")) is True
    assert enabled.checked is True


def test_form_validation_uses_field_ids_and_value_getters() -> None:
    name = TextField(value="")
    form = Form([
        FormRow("name", name, validator=lambda value: "Name required" if not value else None),
        FormRow("enabled", Checkbox("Enabled", checked=True), value_getter=lambda control: control.checked),
    ])

    result = form.validate()

    assert result.valid is False
    assert result.errors == {"name": "Name required"}
    assert form.values() == {"name": "", "enabled": True}
```

- [ ] **Step 2: Run Form red tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_form_tabs_between_focusable_rows_and_delegates_input tests/tui/test_widgets_foundation.py::test_form_validation_uses_field_ids_and_value_getters -q
```

Expected: fail because `Form` behavior is not implemented.

- [ ] **Step 3: Implement Form and validation**

Implement:

- `FormRow(field_id, control, validator=None, value_getter=None, error="")`
- `FormValidationResult(errors: dict[str, str])` with `valid` property
- `Form.focus()`, `blur()`, `focus_next(wrap=True)`, `focus_previous(wrap=True)`
- `Form.handle_input()` for tab/shift+tab and child delegation
- `Form.values()`, `Form.validate()`
- bounded render by concatenating row control render output and error lines

- [ ] **Step 4: Run Form green tests**

Run the same focused pytest command. Expected: pass.

- [ ] **Step 5: Write failing editor target delegation test**

Add:

```python
def test_form_exposes_active_editable_child_target() -> None:
    field = TextField(value="")
    form = Form([FormRow("name", field), FormRow("enabled", Checkbox("Enabled"))])
    form.focus()

    target = form.editor_input_target()
    assert target is not None
    target.insert_text("abc")
    assert field.value == "abc"

    form.focus_next()
    assert form.editor_input_target() is None
```

- [ ] **Step 6: Run editor target red test**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_form_exposes_active_editable_child_target -q
```

Expected: fail because `Form.editor_input_target()` is not implemented.

- [ ] **Step 7: Implement active editor target delegation**

Use `isinstance(active_control, EditorInputTargetProvider)` from `loushang.tui.framework` and return the active child's target when available.

- [ ] **Step 8: Run task tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/form.py tests/tui/test_widgets_foundation.py
git commit -m "feat(tui): add form widget focus scope"
```

## Task 5: Dialog And ConfirmDialog

**Files:**
- Modify: `tests/tui/test_widgets_foundation.py`
- Modify: `src/loushang/tui/ui_parts/widgets/dialog.py`

- [ ] **Step 1: Write failing confirm/cancel tests**

Add:

```python
def test_confirm_dialog_returns_confirm_and_close_intents_by_default() -> None:
    dialog = ConfirmDialog(title="Delete session?")

    assert dialog.handle_input(InputEvent(kind="key", key="enter")) == (
        InputIntent(kind="dialog_confirm"),
        InputIntent(kind="surface_close"),
    )
    assert dialog.handle_input(InputEvent(kind="key", key="escape")) == InputIntent(kind="dialog_cancel")


def test_confirm_dialog_can_keep_open_after_confirm() -> None:
    dialog = ConfirmDialog(title="Validate", close_on_confirm=False)

    assert dialog.handle_input(InputEvent(kind="key", key="enter")) == InputIntent(kind="dialog_confirm")
```

- [ ] **Step 2: Run confirm/cancel red tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_confirm_dialog_returns_confirm_and_close_intents_by_default tests/tui/test_widgets_foundation.py::test_confirm_dialog_can_keep_open_after_confirm -q
```

Expected: fail because dialog behavior is not implemented.

- [ ] **Step 3: Implement DialogAction and ConfirmDialog activation**

Implement `DialogAction(label, intent, kind="default")`, basic action buttons, confirm/cancel behavior, and bounded rendering with title/body/actions.

- [ ] **Step 4: Run confirm/cancel green tests**

Run the same focused pytest command. Expected: pass.

- [ ] **Step 5: Write failing modal focus tests**

Add:

```python
class RecordingBody:
    def __init__(self) -> None:
        self.focused = False
        self.events: list[str] = []

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: InputEvent) -> object:
        if event.kind == "key":
            self.events.append(event.key)
        return True

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([RenderLine("body")], constraints=constraints)


def test_dialog_cancels_before_body_handles_cancel_keys() -> None:
    body = RecordingBody()
    dialog = Dialog(title="Edit", body=body)
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="escape")) == InputIntent(kind="dialog_cancel")
    assert dialog.handle_input(InputEvent(kind="key", key="ctrl+c")) == InputIntent(kind="dialog_cancel")
    assert body.events == []


def test_dialog_tabs_from_form_edge_to_actions_and_delegates_editor_target() -> None:
    field = TextField(value="")
    form = Form([FormRow("name", field)])
    dialog = ConfirmDialog(title="Edit", body=form)
    dialog.focus()

    target = dialog.editor_input_target()
    assert target is not None
    target.insert_text("abc")
    assert field.value == "abc"

    assert dialog.handle_input(InputEvent(kind="key", key="tab")) is True
    assert dialog.editor_input_target() is None
    assert dialog.handle_input(InputEvent(kind="key", key="enter")) == (
        InputIntent(kind="dialog_confirm"),
        InputIntent(kind="surface_close"),
    )
```

- [ ] **Step 6: Run modal focus red tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_dialog_cancels_before_body_handles_cancel_keys tests/tui/test_widgets_foundation.py::test_dialog_tabs_from_form_edge_to_actions_and_delegates_editor_target -q
```

Expected: fail because modal focus coordination is not implemented.

- [ ] **Step 7: Implement modal focus contract**

Implement:

- `Dialog` as `Focusable`
- top-level focus slots: body, actions
- dialog-level `escape` and `ctrl+c` cancel before delegation
- tab/shift+tab behavior with `Form.focus_next(wrap=False)` / `focus_previous(wrap=False)`
- `Dialog.editor_input_target()` delegation to body/form only when body slot is active

- [ ] **Step 8: Run dialog and framework integration tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py tests/tui/test_render_framework.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/dialog.py tests/tui/test_widgets_foundation.py
git commit -m "feat(tui): add modal dialog widgets"
```

## Task 6: Documentation And Example

**Files:**
- Create: `docs/en/reference/tui-widgets.md`
- Create: `docs/zh-CN/reference/tui-widgets.md`
- Modify: `docs/en/reference/README.md`
- Modify: `docs/zh-CN/reference/README.md`
- Create: `examples/tui/43_widgets_foundation.py`
- Modify: `tests/tui/test_widgets_foundation.py`

- [ ] **Step 1: Write failing docs/example smoke test**

Add:

```python
def test_widgets_foundation_example_imports() -> None:
    import runpy

    namespace = runpy.run_path("examples/tui/43_widgets_foundation.py", run_name="__test__")

    assert "build_app" in namespace
```

- [ ] **Step 2: Run docs/example red test**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py::test_widgets_foundation_example_imports -q
```

Expected: fail because the example does not exist.

- [ ] **Step 3: Add reference docs and example**

Docs must include:

- P0A implemented widgets with short code examples
- note that P0B/P1 catalog entries are planned only
- modal focus pattern: `Surface(renderable=dialog, focus_target=dialog, presentation="modal")`
- `SelectList(close_on_escape=False)` default for embedded usage

Example should expose `build_app()` and avoid running `TuiRunner` unless `__name__ == "__main__"`.

- [ ] **Step 4: Run docs/example green test**

Run the same focused pytest command. Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add docs/en/reference/README.md docs/en/reference/tui-widgets.md docs/zh-CN/reference/README.md docs/zh-CN/reference/tui-widgets.md examples/tui/43_widgets_foundation.py tests/tui/test_widgets_foundation.py
git commit -m "docs(tui): document widgets foundation"
```

## Task 7: Final Verification

**Files:**
- All touched widget, doc, example, and test files.

- [ ] **Step 1: Run focused widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py -q
```

Expected: pass.

- [ ] **Step 2: Run adjacent TUI tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_text_input.py tests/tui/test_surfaces.py tests/tui/test_render_framework.py tests/tui/test_input_routing.py -q
```

Expected: pass.

- [ ] **Step 3: Run all TUI tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: pass.

- [ ] **Step 4: Run ruff on TUI source and tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/43_widgets_foundation.py
```

Expected: pass.

- [ ] **Step 5: Inspect git status**

Run:

```bash
git status --short --branch
```

Expected: branch is `feature/tui-widgets-foundation` with only intentional committed work.
