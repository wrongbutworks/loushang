# TUI Widgets P0A Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing P0A TUI widgets by locking down theme, render-constraint, and modal routing behavior.

**Architecture:** Keep widgets as plain `Renderable`/`Focusable` UI parts. Add shared styling helpers in `widgets/_utils.py`, apply them narrowly inside existing widget render paths, and verify behavior through focused headless tests. `SelectList` continues delegating to `SelectionSurface`; modal behavior stays owned by `SurfaceHost` and `Dialog`.

**Tech Stack:** Python 3.11 dataclasses, `pytest`, `uv`, Ruff, existing `loushang.tui` render/input/theme primitives.

---

## File Structure

- Modify `src/loushang/tui/ui_parts/widgets/_utils.py`
  - Add shared theme resolution helpers used only by P0A widgets.
  - Keep input helpers (`is_activation_event`, `callback_result`) unchanged.
- Modify `src/loushang/tui/ui_parts/widgets/button.py`
  - Apply `widget.button.<kind>`, optional `theme_token`, `widget.focus`, and `widget.disabled` styles without changing visible text.
- Modify `src/loushang/tui/ui_parts/widgets/choice.py`
  - Apply focus and disabled styles for `Checkbox`, `Toggle`, and `RadioGroup`.
- Modify `src/loushang/tui/ui_parts/widgets/field.py`
  - Apply `widget.field.label`, `widget.field.help`, and `widget.error`.
  - Preserve all editing behavior through `TextInput`.
- Modify `src/loushang/tui/ui_parts/widgets/form.py`
  - Add `theme: ThemeResolver | None = None`.
  - Apply `widget.error` to rendered `FormRow.error`.
- Modify `src/loushang/tui/ui_parts/widgets/dialog.py`
  - Add `theme: ThemeResolver | None = None` to `Dialog` and inherited `ConfirmDialog`.
  - Apply `widget.dialog.title` and `widget.dialog.action`.
- Add `tests/tui/test_widgets_hardening.py`
  - Keep hardening tests separate from the foundation behavior tests.
- Modify `docs/en/reference/tui-widgets.md`
  - Document initial widget theme tokens and modal focus reminder.
- Modify `docs/zh-CN/reference/tui-widgets.md`
  - Mirror the English reference update.

Do not modify public exports unless a test proves a new export is required. Do
not add P0B/P1 widgets in this plan.

## Task 1: Add Hardening Test Helpers And Button Theme Red Tests

**Files:**
- Create: `tests/tui/test_widgets_hardening.py`
- Modify: none
- Test: `tests/tui/test_widgets_hardening.py`

- [ ] **Step 1: Write the failing test module skeleton**

Add helpers and the first button tests:

```python
from __future__ import annotations

from typing import Any

from loushang.tui import (
    Button,
    InputEvent,
    RenderConstraints,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def test_button_kind_focus_and_disabled_theme_tokens_preserve_visible_width() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.button.primary": {"color": "green"},
            "widget.focus": {"bold": True},
            "widget.disabled": {"dim": True},
        }
    )
    button = Button("Save", kind="primary", theme=theme)

    raw = render_lines(button, width=12)
    assert raw[0].startswith("\x1b[32m")
    assert strip_control_sequences(raw[0]) == "  [Save]"
    assert visible_width(raw[0]) == len("  [Save]")

    button.focus()
    focused = render_lines(button, width=12)
    assert focused[0].startswith("\x1b[1;32m")
    assert strip_control_sequences(focused[0]) == "> [Save]"
    assert visible_width(focused[0]) == len("> [Save]")

    disabled = Button("Save", kind="primary", disabled=True, theme=theme)
    disabled.focus()
    disabled_raw = render_lines(disabled, width=12)
    assert disabled_raw[0].startswith("\x1b[2;32m")
    assert strip_control_sequences(disabled_raw[0]) == "> [Save]"
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None
```

- [ ] **Step 2: Add button override precedence test**

Append:

```python
def test_button_theme_token_overrides_kind_before_focus_style() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.button.danger": {"color": "red"},
            "custom.button": {"color": "cyan"},
            "widget.focus": {"underline": True},
        }
    )
    button = Button("Delete", kind="danger", theme=theme, theme_token="custom.button", focused=True)

    raw = render_lines(button, width=16)

    assert raw[0].startswith("\x1b[4;36m")
    assert strip_control_sequences(raw[0]) == "> [Delete]"
```

- [ ] **Step 3: Run tests to verify red**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_hardening.py -q
```

Expected: FAIL because `Button.render()` does not yet apply theme styles.

- [ ] **Step 4: Commit red tests**

Do not commit red tests by themselves. Continue to Task 2 and commit once green.

## Task 2: Implement Shared Widget Theme Helpers And Button Styling

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/_utils.py`
- Modify: `src/loushang/tui/ui_parts/widgets/button.py`
- Test: `tests/tui/test_widgets_hardening.py`

- [ ] **Step 1: Add theme helper functions**

In `widgets/_utils.py`, keep existing helpers and add:

```python
from loushang.tui.theme import ThemeResolver, ThemeStyle, apply_theme_style


def merge_theme_styles(*styles: ThemeStyle | None) -> ThemeStyle | None:
    merged: ThemeStyle = {}
    for style in styles:
        if style:
            merged.update(style)
    return merged or None


def resolve_theme_style(theme: ThemeResolver | None, token: str | None) -> ThemeStyle | None:
    if theme is None or not token:
        return None
    return theme.resolve(token)


def style_text(text: str, theme: ThemeResolver | None, *tokens: str | None) -> str:
    style = merge_theme_styles(*(resolve_theme_style(theme, token) for token in tokens))
    return apply_theme_style(text, style)
```

- [ ] **Step 2: Apply button styles**

In `button.py`:

```python
from loushang.tui.ui_parts.widgets._utils import (
    callback_result,
    is_activation_event,
    style_text,
)


def _button_base_token(kind: ButtonKind) -> str:
    return f"widget.button.{kind}"
```

Update `render()` after truncation:

```python
base_token = self.theme_token or _button_base_token(self.kind)
state_token = "widget.disabled" if self.disabled else "widget.focus" if self.focused else None
rendered = style_text(rendered, self.theme, base_token, state_token)
```

- [ ] **Step 3: Run focused hardening tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_hardening.py -q
```

Expected: PASS for the current two tests.

- [ ] **Step 4: Run existing widget foundation tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/tui/test_widgets_hardening.py src/loushang/tui/ui_parts/widgets/_utils.py src/loushang/tui/ui_parts/widgets/button.py
git commit -m "test(tui): harden button widget theming"
```

## Task 3: Add Choice Widget Theme And Constraint Tests

**Files:**
- Modify: `tests/tui/test_widgets_hardening.py`
- Modify: `src/loushang/tui/ui_parts/widgets/choice.py`
- Test: `tests/tui/test_widgets_hardening.py`

- [ ] **Step 1: Write failing tests for checkbox, toggle, radio group, and constraints**

Append to `test_widgets_hardening.py` imports:

```python
    Checkbox,
    Choice,
    ConfirmDialog,
    Dialog,
    Form,
    FormRow,
    IconButton,
    RadioGroup,
    SelectItem,
    SelectList,
    TextField,
    Toggle,
```

Append tests:

```python
def test_choice_widgets_apply_focus_and_disabled_theme_without_text_changes() -> None:
    theme = ThemeResolver(defaults={"widget.focus": {"bold": True}, "widget.disabled": {"dim": True}})

    checkbox = Checkbox("Enabled", checked=True, focused=True, theme=theme)
    toggle = Toggle("Auto", value=False, disabled=True, focused=True, theme=theme)
    radio = RadioGroup(
        [Choice("fast", "Fast"), Choice("slow", "Slow", disabled=True)],
        value="fast",
        theme=theme,
        focused=True,
    )

    assert render_lines(checkbox)[0].startswith("\x1b[1m")
    assert plain_lines(checkbox) == ("> [x] Enabled",)
    assert render_lines(toggle)[0].startswith("\x1b[2m")
    assert plain_lines(toggle) == ("> [off] Auto",)

    radio_lines = render_lines(radio, width=20, height=3)
    assert radio_lines[0].startswith("\x1b[1m")
    assert radio_lines[1].startswith("\x1b[2m")
    assert tuple(strip_control_sequences(line) for line in radio_lines) == ("> (x) Fast", "  ( ) Slow")


def p0a_constraint_cases() -> list[object]:
    return [
        Button("Very long label", focused=True),
        IconButton("*", label="Very long label", focused=True),
        Checkbox("Very long label", focused=True),
        Toggle("Very long label", focused=True),
        RadioGroup([Choice("a", "Very long label")], value="a", focused=True),
        TextField(label="Very long label", value="Very long value", help_text="Very long help"),
        SelectList([SelectItem("Very long label")], max_visible=1),
        Form([FormRow("name", TextField(label="Very long label", value="Very long value"))]),
        Dialog(title="Very long dialog title", body="Very long dialog body"),
        ConfirmDialog(title="Very long confirm title", body="Very long confirm body"),
    ]


def test_all_p0a_widgets_respect_small_valid_render_constraints() -> None:
    for control in p0a_constraint_cases():
        lines = render_lines(control, width=1, height=1)
        assert len(lines) <= 1
        assert_widths_within(lines, 1)


def test_all_p0a_widgets_respect_narrow_short_render_constraints() -> None:
    for control in p0a_constraint_cases():
        lines = render_lines(control, width=6, height=2)
        assert len(lines) <= 2
        assert_widths_within(lines, 6)
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_hardening.py -q
```

Expected: FAIL because `choice.py` does not apply theme styles yet.

- [ ] **Step 3: Apply styles in choice widgets**

In `choice.py`, import `style_text`:

```python
from loushang.tui.ui_parts.widgets._utils import callback_result, is_activation_event, style_text
```

For `Checkbox.render()` and `Toggle.render()`, style the truncated line:

```python
rendered = truncate_to_width(line, max_width=target_width, ellipsis="")
state_token = "widget.disabled" if self.disabled else "widget.focus" if self.focused else None
rendered = style_text(rendered, self.theme, state_token)
return RenderResult.from_lines([RenderLine(rendered)][: constraints.max_height], constraints=constraints)
```

For `RadioGroup.render()`, after truncating each row:

```python
state_token = "widget.disabled" if option.disabled else "widget.focus" if self.focused and index == self._active_index else None
lines.append(RenderLine(style_text(rendered, self.theme, state_token)))
```

Keep `_single_line_result()` unthemed or replace it with a helper that accepts
`theme` and `state_token`; avoid duplicating truncation logic more than needed.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_hardening.py tests/tui/test_widgets_foundation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/tui/test_widgets_hardening.py src/loushang/tui/ui_parts/widgets/choice.py
git commit -m "test(tui): harden choice widget rendering"
```

## Task 4: Add TextField And Form Theme Tests And Implementation

**Files:**
- Modify: `tests/tui/test_widgets_hardening.py`
- Modify: `src/loushang/tui/ui_parts/widgets/field.py`
- Modify: `src/loushang/tui/ui_parts/widgets/form.py`
- Test: `tests/tui/test_widgets_hardening.py`

- [ ] **Step 1: Write failing TextField and Form tests**

`Form`, `FormRow`, and `TextField` were imported in Task 3 for full P0A
constraint coverage. If this task is run independently, add those imports before
adding these tests.

Append tests:

```python
def test_text_field_themes_label_help_and_error_with_error_precedence() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.field.label": {"color": "cyan"},
            "widget.field.help": {"dim": True},
            "widget.error": {"color": "red"},
        }
    )
    field = TextField(label="Name", value="tower", help_text="Helpful", error="Required", theme=theme)
    field.focus()

    raw = render_lines(field, width=24, height=4)

    assert raw[0].startswith("\x1b[36m")
    assert raw[2].startswith("\x1b[31m")
    assert tuple(strip_control_sequences(line) for line in raw) == ("Name", "tower", "Required")
    assert all(visible_width(line) <= 24 for line in raw)


def test_text_field_cursor_row_stays_on_input_when_height_truncates_detail() -> None:
    field = TextField(label="Name", value="tower", help_text="Helpful")
    field.focus()

    result = field.render(RenderConstraints(width=24, max_height=2))

    assert tuple(strip_control_sequences(line.text) for line in result.lines) == ("Name", "tower")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, len("tower"))


def test_form_themes_validation_errors_without_changing_values() -> None:
    theme = ThemeResolver(defaults={"widget.error": {"color": "red"}})
    form = Form(
        [FormRow("name", TextField(value=""), validator=lambda value: "Name required" if not value else None)],
        theme=theme,
    )

    result = form.validate()
    raw = render_lines(form, width=24, height=4)

    assert result.errors == {"name": "Name required"}
    assert raw[-1].startswith("\x1b[31m")
    assert strip_control_sequences(raw[-1]) == "Name required"
    assert form.values() == {"name": ""}
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_hardening.py -q
```

Expected: FAIL because `TextField` detail lines and `FormRow.error` are not yet themed, and `Form` lacks a `theme` parameter.

- [ ] **Step 3: Theme TextField lines**

In `field.py`, import `style_text`:

```python
from loushang.tui.ui_parts.widgets._utils import style_text
```

Apply label and detail styles after truncation:

```python
label = truncate_to_width(self.label, max_width=target_width, ellipsis="")
lines.append(RenderLine(style_text(label, self.theme, "widget.field.label")))
```

For `detail`:

```python
detail_token = "widget.error" if self.error else "widget.field.help"
rendered_detail = truncate_to_width(detail, max_width=target_width, ellipsis="")
lines.append(RenderLine(style_text(rendered_detail, self.theme, detail_token)))
```

- [ ] **Step 4: Add Form theme field and style row errors**

In `form.py`, import `ThemeResolver` and `style_text`:

```python
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import style_text
```

Add a dataclass field:

```python
theme: ThemeResolver | None = None
```

When rendering `row.error`:

```python
error = truncate_to_width(row.error, max_width=target_width, ellipsis="")
lines.append(RenderLine(style_text(error, self.theme, "widget.error")))
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_hardening.py tests/tui/test_widgets_foundation.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/tui/test_widgets_hardening.py src/loushang/tui/ui_parts/widgets/field.py src/loushang/tui/ui_parts/widgets/form.py
git commit -m "test(tui): harden field and form rendering"
```

## Task 5: Add Dialog Theme And SurfaceHost Modal Integration Tests

**Files:**
- Modify: `tests/tui/test_widgets_hardening.py`
- Modify: `src/loushang/tui/ui_parts/widgets/dialog.py`
- Test: `tests/tui/test_widgets_hardening.py`

- [ ] **Step 1: Write failing dialog theme test**

Append imports:

```python
    Surface,
    SurfaceHost,
```

`ConfirmDialog` was imported in Task 3 for full P0A constraint coverage. If this
task is run independently, add it here too.

Append:

```python
def intent_tuple(intent: object) -> tuple[str, str, str]:
    return (getattr(intent, "kind", ""), getattr(intent, "text", ""), getattr(intent, "note", ""))


def test_dialog_themes_title_and_actions() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.dialog.title": {"bold": True},
            "widget.dialog.action": {"color": "cyan"},
        }
    )
    dialog = ConfirmDialog(title="Apply?", body="Changes", theme=theme)

    raw = render_lines(dialog, width=30, height=4)

    assert raw[0].startswith("\x1b[1m")
    assert raw[-1].startswith("\x1b[36m")
    assert tuple(strip_control_sequences(line) for line in raw) == ("Apply?", "Changes", "[Confirm]  [Cancel]")
```

- [ ] **Step 2: Write modal integration tests**

Append:

```python
def test_confirm_dialog_modal_routes_editor_target_and_confirm_closes_surface() -> None:
    field = TextField(value="")
    form = Form([FormRow("name", field)])
    dialog = ConfirmDialog(title="Edit", body=form)
    host = SurfaceHost()

    host.open_surface(Surface(renderable=dialog, focus_target=dialog, presentation="modal"))

    assert dialog.focused is True
    assert form.focused is True
    target = host.current_editor_target()
    assert target is not None
    target.insert_text("abc")
    assert field.value == "abc"

    assert host.route_input(InputEvent(kind="key", key="tab")) == ()
    assert host.current_editor_target() is None

    intents = host.route_input(InputEvent(kind="key", key="enter"))
    assert tuple(intent_tuple(intent) for intent in intents) == (
        ("dialog_confirm", "", ""),
        ("surface_close", "", ""),
    )
    assert host.current_focus() is None


def test_confirm_dialog_modal_cancel_closes_before_text_field_escape() -> None:
    seen_escape: list[str] = []
    field = TextField(value="", on_escape=lambda: seen_escape.append("field"))
    form = Form([FormRow("name", field)])
    dialog = ConfirmDialog(title="Edit", body=form)
    host = SurfaceHost()
    host.open_surface(Surface(renderable=dialog, focus_target=dialog, presentation="modal"))

    intents = host.route_input(InputEvent(kind="key", key="escape"))

    assert tuple(intent_tuple(intent) for intent in intents) == (("dialog_cancel", "", ""),)
    assert seen_escape == []
    assert host.current_focus() is None
```

- [ ] **Step 3: Run tests to verify red**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_hardening.py -q
```

Expected: FAIL because `Dialog`/`ConfirmDialog` lack `theme`; modal integration may already pass. If modal tests pass on the first run, keep them as regression coverage and only implement the theme gap.

- [ ] **Step 4: Add Dialog theme field and action styling**

In `dialog.py`, import `ThemeResolver` and `style_text`:

```python
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import style_text
```

Add `theme` to `Dialog`:

```python
theme: ThemeResolver | None = None
```

Pass theme into `_dialog_result()` from `Dialog.render()` and `ConfirmDialog.render()`:

```python
theme=self.theme,
```

Update helper signature:

```python
def _dialog_result(
    *,
    title: str,
    body: object | str | None,
    action_labels: tuple[str, ...],
    constraints: RenderConstraints,
    theme: ThemeResolver | None = None,
) -> RenderResult:
```

Style title and action line:

```python
title_line = truncate_to_width(title, max_width=target_width, ellipsis="")
lines = [RenderLine(style_text(title_line, theme, "widget.dialog.title"))]
...
action_line = truncate_to_width(action_line, max_width=target_width, ellipsis="")
lines.append(RenderLine(style_text(action_line, theme, "widget.dialog.action")))
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_hardening.py tests/tui/test_widgets_foundation.py tests/tui/test_surfaces.py tests/tui/test_input_routing.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/tui/test_widgets_hardening.py src/loushang/tui/ui_parts/widgets/dialog.py
git commit -m "test(tui): harden dialog modal routing"
```

## Task 6: Update Widget Reference Docs

**Files:**
- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`
- Test: none

- [ ] **Step 1: Update English docs**

Add a short section after "Dialogs":

```markdown
## Theme Tokens

P0A widgets accept `ThemeResolver` where styling is supported. Initial stable
tokens are:

| Token | Applies to |
| --- | --- |
| `widget.focus` | Focused enabled controls or rows. |
| `widget.disabled` | Disabled controls or disabled radio options. |
| `widget.error` | `TextField` and `FormRow` error lines. |
| `widget.field.label` | `TextField` labels. |
| `widget.field.help` | `TextField` help lines. |
| `widget.button.default` | Default buttons. |
| `widget.button.primary` | Primary buttons. |
| `widget.button.danger` | Danger buttons. |
| `widget.button.ghost` | Ghost buttons. |
| `widget.dialog.title` | Dialog titles. |
| `widget.dialog.action` | Dialog action rows. |
```

- [ ] **Step 2: Update Chinese docs**

Mirror the section in `docs/zh-CN/reference/tui-widgets.md` with Chinese
descriptions and identical token names.

- [ ] **Step 3: Commit**

```bash
git add docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md
git commit -m "docs(tui): document widget theme tokens"
```

## Task 7: Full Verification And Cleanup

**Files:**
- Modify only if verification finds issues.

- [ ] **Step 1: Run focused widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent TUI tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_basic_theme_compliance.py tests/tui/test_surfaces.py tests/tui/test_input_routing.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full TUI suite**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS.

- [ ] **Step 4: Run Ruff**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui docs
```

Expected: PASS.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git status --short --branch
git log --oneline --decorate -8
```

Expected: branch contains the spec commit plus implementation commits, with no
uncommitted changes.

## Completion Criteria

- P0A widgets have hardening tests for theming, constraints, and modal routing.
- No new P0B/P1 controls are added.
- `Form(theme=...)`, `Dialog(theme=...)`, and inherited `ConfirmDialog(theme=...)`
  are the only public API additions.
- All focused, adjacent, full TUI, and Ruff checks pass.
