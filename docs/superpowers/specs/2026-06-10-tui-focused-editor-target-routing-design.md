# TUI Focused Editor Target Routing Design

## Status

Draft for implementation planning.

## Context

`InputRouter` now routes generic prompt editing through a `PromptInputTarget`
instead of calling `Composer` directly. That made the prompt editor replaceable,
but it did not yet let focused surface editors reuse the same input policy.

`SurfaceHost` already owns focus capture and restoration. It can route events to
the currently focused surface, and `TextInput` already works as a focused
overlay through its own `handle_input()` implementation. The missing boundary is
a way for focused editors to opt into shared editor-key routing without making
`InputRouter` understand concrete widget classes or rewriting surface submit and
escape semantics.

The next slice should prove the target boundary with `TextInput`, because it is
the smallest existing non-Composer editor and already shares most editing
primitives with `Composer`.

## Goals

- Let a focused surface editor opt into generic editor key routing.
- Keep `InputRouter` responsible for keybinding policy and editing operations.
- Preserve surface-first intent routing and close behavior.
- Preserve prompt submit, follow-up, steer, history, completion, and jump
  semantics.
- Prove the model with `TextInput` without building a full widget ecosystem.
- Keep existing `TextInput.handle_input()` behavior working for `Tui.handle_input`
  and direct surface routing.

## Non-Goals

- Do not introduce a global focus manager beyond `SurfaceHost`.
- Do not make focused `TextInput` submit prompt text.
- Do not route prompt-only actions such as history, completions, page movement,
  queue editing, steer, or follow-up to ordinary focused editors.
- Do not remove `TextInput.handle_input()`.
- Do not change `NativeInputRouter` product-specific routing order.
- Do not add new widgets such as button, tree, list, or dialog containers in this
  slice.

## Design Summary

Add an optional editor-target discovery path to `SurfaceHost`.

1. A focused object may expose an editor target through `editor_input_target()`.
2. `SurfaceHost.current_editor_target()` returns that target only when the
   current focus is a visible surface focus target.
3. `InputRouter` continues to route surface intents first.
4. If the focused surface did not consume the event and a focused editor target
   exists, `InputRouter` routes generic editor text, paste, selection, and
   editing keys to that editor target.
5. Prompt-only routes still fall back to the prompt target.

This preserves the existing contract: surfaces get first chance to handle
submit, escape, custom commands, and close intents. The focused editor fallback
only handles ordinary editing when the surface did not consume the event.

## Editor Target Discovery

Add a runtime-checkable protocol in `framework.py`:

```python
@runtime_checkable
class EditorInputTargetProvider(Protocol):
    def editor_input_target(self) -> Any: ...
```

`Any` avoids importing `EditorInputTarget` into `framework.py` and creating a
cycle from `framework -> input -> framework`. The input module can cast or use
the returned object structurally.

`SurfaceHost.current_editor_target()` should:

- call `_sync_focus_for_visible_entries(self._last_known_size())`
- inspect `self._current_focus_entry()`
- return `None` when focus is only `base_focus`
- return `None` when the surface focus target does not expose
  `editor_input_target()`
- return the provider result when it is not `None`

Only surface focus targets participate in this first slice. Base focus editor
targets are deferred because the prompt already has an explicit prompt target
and base-focus fallback would blur the boundary between prompt and surface
editing.

## TextInput Target

`TextInput` should expose itself as its editor target:

```python
def editor_input_target(self) -> TextInput:
    return self
```

To satisfy `EditorInputTarget`, add compatibility aliases whose names match the
shared helper interface:

```python
def move_to_line_start(self) -> None:
    self.move_to_start()

def move_to_line_end(self) -> None:
    self.move_to_end()

def kill_to_line_start(self) -> None:
    self.kill_to_start()

def kill_to_line_end(self) -> None:
    self.kill_to_end()
```

`TextInput.paste()` should normalize pasted text the same way direct
`handle_input(kind="paste")` does today: insert `_single_line_text(text)`.
This can be implemented as a direct alias to `insert_text()`.

`TextInput` already has the remaining editing and selection operations:
`insert_text`, cursor movement, word movement, delete, kill, yank, undo, redo,
and selection extension.

## InputRouter Data Flow

For key events:

1. Keep the existing key release and jump-mode cleanup behavior.
2. Route surface input first through `_route_surface_first(event)`.
3. If a surface emitted `InputIntent` values, return them unchanged.
4. Ask `surface_host.current_editor_target()` for a focused editor target.
5. If a focused editor target exists:
   - route selection keys with `route_editor_selection_key()`
   - route ordinary editing keys with `route_editor_editing_key()`
   - do not route submit, escape, completion, history, jump, page movement,
     queue edit, or prompt newline to the focused editor
6. Continue with existing prompt-target routing.

For text and paste events:

1. Route surface input first.
2. If surface intents are returned, return them.
3. If there is a focused editor target, insert text or paste into that target.
4. Otherwise keep the existing prompt-target behavior.

Resize and SIGWINCH continue to return `invalidate_render` and do not route to
focused editors.

## Surface Intent Semantics

Focused editor fallback only runs when the surface did not emit intents. This
keeps existing surfaces authoritative for:

- `surface_close`
- `dialog_cancel`
- submit callbacks handled by `TextInput.handle_input()`
- escape callbacks handled by `TextInput.handle_input()`
- selection surfaces and modal command surfaces

If a surface wants `TextInput` submit or escape callbacks, it can continue to
handle those through `TextInput.handle_input()`. The generic `InputRouter`
fallback is only for ordinary editing operations that are currently duplicated
or unavailable when custom surface handlers decline an event.

## Error Handling

- `current_editor_target()` returns `None` when no visible focused surface editor
  is available.
- A provider returning `None` is treated as no focused editor.
- A provider returning an incomplete editor target should fail normally when the
  helper calls a missing method; do not silently fall back to prompt editing.
- Surface routing remains defensive: non-`InputIntent` surface return values are
  ignored as they are today.

## Testing

Add focused tests before implementation:

- `SurfaceHost.current_editor_target()` returns a focused surface target exposed
  by `editor_input_target()`.
- Hidden or closed surface focus targets no longer provide an editor target.
- `TextInput.editor_input_target()` returns the field itself.
- `TextInput` exposes the alias methods required by `EditorInputTarget`.
- `InputRouter` routes text and paste to a focused `TextInput` after the surface
  declines the event, without changing the prompt target.
- `InputRouter` routes selection and editing keys to a focused `TextInput`.
- `InputRouter` still lets surface intents win before focused editor fallback.
- `InputRouter` still submits prompt text when no focused editor target exists.
- Resize/SIGWINCH still invalidate render instead of touching focused editors.

Focused verification:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_text_input.py tests/tui/test_input_routing.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/framework.py src/loushang/tui/input.py src/loushang/tui/ui_parts/text_input.py tests/tui/test_text_input.py tests/tui/test_input_routing.py
```

## Rollout Plan

1. Add `TextInput` editor target compatibility methods and tests.
2. Add `SurfaceHost.current_editor_target()` and focused target tests.
3. Route generic `InputRouter` text, paste, selection, and editing keys through
   the focused editor fallback.
4. Keep prompt-only behavior and native routing unchanged.
5. Document the focused editor target boundary in `KD-002`.

Stop after this slice. A future spec can decide whether `SurfaceHost` should
support base-focus editor targets or whether a higher-level focus registry is
needed for richer widgets.

## Success Criteria

- Existing prompt `InputRouter(composer=...)` behavior remains unchanged.
- Focused `TextInput` can receive ordinary text, paste, selection, and editing
  keys through `InputRouter`.
- Surface intents still win over editor fallback.
- Submit and escape for focused surfaces remain surface-owned.
- `NativeInputRouter` behavior remains unchanged.
- The implementation does not introduce a full widget or focus-manager system.
