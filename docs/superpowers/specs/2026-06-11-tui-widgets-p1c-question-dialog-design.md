# TUI Widgets P1C QuestionDialog Design

## Status

Draft for implementation planning.

## Context

`loushang.tui` now has the pieces needed to build a reusable question-and-answer
dialog:

- `Dialog` / `ConfirmDialog` provide modal composition, action rows, and
  confirm/cancel intent semantics.
- `Form` provides local focus traversal and validation wiring.
- `TextArea` provides deterministic multi-line editing, `editor_input_target()`,
  height-constrained rendering, and explicit non-enter submit support.

The remaining gap is a high-level widget for asking the user a question and
collecting a multi-line answer. Product UIs can currently compose this manually
with `Dialog + Form + TextArea`, but every caller must decide key handling,
required validation, action intent shape, and close behavior. That wiring should
be reusable.

This widget was originally discussed as `PromptDialog`, but that name conflicts
with AI/Composer prompt terminology. The first slice should use
`QuestionDialog`: it asks a human-readable question and returns the answer to
the application. It must not route answers into `Composer` directly.

## Goals

- Add a public `QuestionDialog` widget for multi-line answers.
- Keep `QuestionDialog` a normal `Renderable`, `Focusable`, and
  `EditorInputTargetProvider`.
- Compose existing `TextArea` behavior instead of introducing another editor.
- Preserve `enter` as newline insertion inside the text area.
- Submit with an explicit non-enter key, defaulting to `ctrl+enter`.
- Cancel with `escape` or `ctrl+c`.
- Support `tab` / `shift+tab` traversal between the body and action row.
- Support required validation, custom validation, and visible error text.
- Return structured `InputIntent` values instead of writing to `Composer` or
  calling product-specific callbacks.
- Support theme tokens and width/height constraints.
- Export stable public API through `loushang.tui.ui_parts.widgets`,
  `loushang.tui.ui_parts`, and top-level `loushang.tui`.
- Add focused tests, docs, and a small example.

## Non-Goals

- Do not add single-line mode in P1C. `TextField` and `Dialog` remain enough for
  that use case.
- Do not write answers into `Composer`.
- Do not add Composer history, completions, slash commands, paste markers,
  images, markdown preview, or prompt-specific behavior.
- Do not change global default keybindings.
- Do not change `InputRouter`, `SurfaceHost`, `Dialog`, `ConfirmDialog`, `Form`,
  or `TextArea` unless a focused test proves a small reusable hook is needed.
- Do not introduce a general dialog layout engine.
- Do not add mouse selection or pointer capture.

## Public API

Add `src/loushang/tui/ui_parts/widgets/question_dialog.py`.

```python
from collections.abc import Callable
from dataclasses import dataclass

@dataclass(init=False, slots=True)
class QuestionDialog:
    title: str
    question: str = ""
    placeholder: str = ""
    help_text: str = ""
    error: str = ""
    height: int = 4
    confirm_label: str = "Submit"
    cancel_label: str = "Cancel"
    required: bool = False
    required_message: str = "Answer required"
    validator: Callable[[str], str | None] | None = None
    close_on_submit: bool = True
    close_on_cancel: bool = True
    submit_key: str = "ctrl+enter"
    theme: ThemeResolver | None = None
    focused: bool = False
```

The first public API should also expose:

- `__init__(..., value: str = "", ...)`.
- `value` as a read-only property backed by the internal `TextArea`; after
  initialization, the answer text lives only in the internal `TextArea`, not in
  separate dataclass state.
- `set_text(text)` and `clear()` delegating to `TextArea`.
- `focus()` and `blur()`.
- `handle_input(event)`.
- `editor_input_target()` returning the internal `TextArea` editor target while
  the body is focused.
- `render(constraints)`.

`QuestionDialog` owns one internal `TextArea`. The question text is rendered as
dialog body copy above the text area, not as the `TextArea` label. This avoids
duplicating the question into every body row and keeps the `TextArea` reusable
inside the dialog.

## Intent Semantics

`QuestionDialog.handle_input()` returns structured `InputIntent` objects:

| Event | Return value |
| --- | --- |
| Successful submit with `close_on_submit=True` | `(InputIntent(kind="question_submit", text=value), InputIntent(kind="surface_close"))` |
| Successful submit with `close_on_submit=False` | `InputIntent(kind="question_submit", text=value)` |
| Cancel with `close_on_cancel=True` | `(InputIntent(kind="question_cancel"), InputIntent(kind="surface_close"))` |
| Cancel with `close_on_cancel=False` | `InputIntent(kind="question_cancel")` |
| Validation failure | `True` after setting `error`; no close intent |
| Body input consumed by `TextArea` | `True` |
| Unhandled input | `None` |

`question_submit` and `question_cancel` are new `InputIntentKind` values. They
carry no Composer behavior by themselves. Application code decides whether a
submitted answer becomes a prompt insertion, a form value, a queue note, or
something else.

The `text` field of `question_submit` contains the answer. `question_cancel`
does not need text.

## Input Behavior

Default keys:

| Input | Behavior |
| --- | --- |
| `enter` | Insert newline in the internal `TextArea`. |
| `ctrl+enter` | Submit the current answer. |
| `escape` / `ctrl+c` | Cancel the dialog. |
| `tab` | Move focus from body to actions, or from actions back to body. |
| `shift+tab` | Move focus from actions to body, or from body to actions. |
| `left` / `right` on action row | Toggle active action between submit and cancel. |
| `enter` / `space` on action row | Activate the active action. |
| text / paste / editor keys while body focused | Delegate to `TextArea`. |

`submit_key` defaults to `"ctrl+enter"` and is implemented through the
`keybindings` argument passed to `TextArea.handle_input()`. The internal
`TextArea` is constructed with an `on_submit` callback that records a private
pending-submit flag. `QuestionDialog.handle_input()` clears that flag before
delegating body input, calls `TextArea.handle_input()`, then checks the flag to
distinguish submit from ordinary consumed edits:

```python
self._pending_submit = False
consumed = self._text_area.handle_input(
    event,
    keybindings={"tui.input.submit": (self.submit_key,)},
)
if self._pending_submit:
    return self._submit_current_value()
if consumed:
    return True
return None
```

Plain `enter` must still insert a newline. The implementation should not change
`DEFAULT_KEYBINDINGS`.

`escape` and `ctrl+c` are intercepted by `QuestionDialog.handle_input()` before
body delegation. The dialog must not rely on `TextArea.handle_input()` or
`TextArea.on_escape` to produce cancel intents, because `TextArea.handle_input()`
only returns a boolean consumed marker.

`QuestionDialog.handle_input(event)` does not accept caller-supplied keybindings
in P1C. The dialog owns its body submit mapping by passing only
`{"tui.input.submit": (self.submit_key,)}` to the internal `TextArea`. This
keeps `submit_key` deterministic and avoids merging ambiguity with application
keybinding overrides. Other TextArea editing keys continue to use the default
TextArea keybindings. A future slice can add explicit keybinding injection if a
real caller needs it.

`submit_key` is normalized with `normalize_key_id()` during initialization. It
must not be any key that the dialog guarantees for newline, cancel, or focus
movement:

- `enter`
- `shift+enter`
- `alt+enter`
- `ctrl+j`
- `escape` / `esc`
- `ctrl+c`
- `tab`
- `shift+tab`
- unmodified printable/text-event keys, such as `s`, `space`, and literal
  space

If `submit_key` normalizes to one of those keys, `QuestionDialog.__init__()`
raises `ValueError`. Other explicit key choices are allowed; if they overlap
with ordinary TextArea editing commands, submit wins because `TextArea` checks
`tui.input.submit` before editor movement keys.

When the focus slot is `"actions"`, editor input is not delegated to the
`TextArea`; only action navigation and activation are handled. When the focus
slot is `"body"`, `editor_input_target()` returns the text area target.

`focus()` starts in the `"body"` focus slot. The first transition to the action
row sets the active action to submit. `left` and `right` toggle the active action
between submit and cancel.

## Validation

Submit flow:

1. Read the current `value`.
2. If `required=True` and `value.strip()` is empty, set `error` to
   `required_message`.
3. If `validator` is provided, call `validator(value)`.
4. If the validator returns a string, set that string as the visible error.
5. If validation fails, return `True` and keep the dialog open.
6. If validation passes, clear any validation error and return submit intent(s).

Validation errors should be rendered through the internal `TextArea.error` row.
`help_text` is shown when there is no active error. Explicit `error` passed to
the constructor is initial display state. Once submit validation runs, the
dialog owns the active validation error state until `set_text()`, `clear()`, or
a later successful submit clears it.

## Rendering

`QuestionDialog.render(constraints)` returns a bounded `RenderResult` with:

1. Title row.
2. Optional question text row.
3. Internal `TextArea` body.
4. Action row: `[Submit]  [Cancel]`.

The dialog should use `autowrap_safe_width(constraints.width)` and truncate all
visible rows. It should preserve the `TextArea` cursor declaration by offsetting
the cursor row by the number of rows rendered before the text area.

Height budget:

- Title row is highest priority.
- Question row is rendered next when present and height allows.
- Action row should be reserved when height allows at least one body row plus
  actions.
- The `TextArea` receives the remaining height.
- If only one row remains after title/question, body wins and actions are
  omitted.
- If the body cannot render, omit the cursor declaration.

Action row rendering:

- The active action should be visually marked without changing row width.
- Suggested plain text:
  - Body focused: `"  [Submit]  [Cancel]"`
  - Submit active: `"> [Submit]  [Cancel]"`
  - Cancel active: `"  [Submit]> [Cancel]"`
- If the row is too narrow, truncate to the safe width.

## Theme Tokens

Add these initial stable tokens:

| Token | Applies to |
| --- | --- |
| `widget.question.title` | Title row. |
| `widget.question.text` | Question row. |
| `widget.question.action` | Inactive action row text. |
| `widget.question.focus` | Active action row text. |

The internal `TextArea` keeps using its own tokens:

- `widget.textArea.label`
- `widget.textArea.placeholder`
- `widget.textArea.text`
- `widget.textArea.error`
- `widget.textArea.help`
- `editor.selection`

`QuestionDialog(theme=...)` passes the same theme resolver to its internal
`TextArea`.

## Files In Scope

Production:

- `src/loushang/tui/input.py`
- `src/loushang/tui/ui_parts/widgets/question_dialog.py`
- `src/loushang/tui/ui_parts/widgets/__init__.py`
- `src/loushang/tui/ui_parts/__init__.py`
- `src/loushang/tui/__init__.py`

Tests:

- `tests/tui/test_widgets_question_dialog.py`
- Adjacent widget hardening tests only if theme/constraint coverage fits better
  there.

Docs and examples:

- `docs/en/reference/tui-widgets.md`
- `docs/zh-CN/reference/tui-widgets.md`
- `examples/tui/48_widgets_question_dialog.py`

## Testing Strategy

Use TDD for implementation:

1. Add public export tests.
2. Add submit/cancel intent tests for body focus and action focus.
3. Add key behavior tests proving `enter` inserts newline and `ctrl+enter`
   submits.
4. Add required and custom validator tests.
5. Add `editor_input_target()` tests proving body focus exposes the text area
   target and action focus does not.
6. Add render tests for title, question, body, actions, cursor offsets, width,
   height, and theme tokens.
7. Add docs and example importability tests.
8. Run focused tests, adjacent widget tests, full TUI tests, and Ruff.

Expected verification commands:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_question_dialog.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_textarea.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/48_widgets_question_dialog.py docs
```

## Rollout Plan

This should be one focused PR with small commits:

1. Commit the design spec.
2. Commit the implementation plan after spec review.
3. Add failing export and intent tests.
4. Implement `QuestionDialog` skeleton and public exports.
5. Add failing submit/cancel/keybinding/validation tests.
6. Implement input handling and validation.
7. Add failing render/theme/cursor tests.
8. Implement deterministic rendering.
9. Add docs and example coverage.
10. Run focused, adjacent, full TUI, and Ruff verification.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Name still confused with Composer prompt behavior. | Use `QuestionDialog`, never `PromptDialog`, and state that submit returns intents only. |
| `InputIntentKind` expansion becomes too broad. | Add only `question_submit` and `question_cancel` for this semantic dialog; ordinary widgets keep callback returns. |
| Enter/submit behavior regresses TextArea. | Test that plain `enter` inserts newline and `ctrl+enter` submits only inside `QuestionDialog`. |
| Validation state conflicts with constructor `error`. | Treat constructor `error` as initial display; submit validation owns later error text. |
| Rendering action row steals body height. | Write explicit height-budget tests for title/question/body/actions. |
| Dialog duplicates too much `Dialog`/`ConfirmDialog` logic. | Keep P1C self-contained first; extract shared helpers only if a follow-up proves duplication hurts. |

## Success Criteria

- `QuestionDialog` is exported from the same public modules as stable widgets.
- It asks a question and collects a multi-line answer without touching
  `Composer`.
- `enter` inserts newlines; `ctrl+enter` submits.
- `escape` and `ctrl+c` cancel.
- Required and custom validation keep the dialog open and render error text.
- Submit and cancel return structured `InputIntent` values with optional
  `surface_close`.
- `editor_input_target()` works while body focus is active.
- Rendering obeys width and height constraints and preserves body cursor
  offsets.
- Theme tokens are deterministic and covered.
- Docs and example import tests pass.
- Existing TUI tests remain green.
