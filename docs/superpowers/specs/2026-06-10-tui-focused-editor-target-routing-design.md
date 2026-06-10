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
3. `InputRouter` continues to route surface input first.
4. `SurfaceHost` exposes whether the focused surface consumed the event, even
   when it did not emit `InputIntent` values.
5. If the focused surface declined the event and a focused editor target exists,
   `InputRouter` routes generic editor text, paste, selection, and editing keys
   to that editor target.
6. Prompt-only routes still use the prompt target only when no focused editor
   target owns the editing lane.

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

## Surface Consumption Contract

`SurfaceHost.route_input()` currently returns only normalized surface values:
`None` and boolean results collapse to `()`. That public behavior must remain
unchanged.

Add a narrow result API for routers that need to know whether the focus target
handled the event:

```python
@dataclass(frozen=True, slots=True)
class SurfaceInputRouteResult:
    intents: tuple[Any, ...]
    consumed: bool
```

`SurfaceHost.route_input_result()` should share the same routing and close logic
as `route_input()`, but preserve consumption:

- `None` means `consumed=False`
- `False` means `consumed=False`
- `True` means `consumed=True`
- any non-empty tuple means `consumed=True`
- any non-`None` non-bool scalar means `consumed=True`

`route_input()` becomes a compatibility wrapper returning
`route_input_result(...).intents`.

Consumption is explicit. `route_input_result()` should not try to detect state
mutation by diffing arbitrary surface objects. Existing surfaces that currently
mutate state and return `None` must be updated in this slice to return `True`
for consumed-without-intent paths. In particular:

- `SelectionSurface` search text, search editing keys, mouse presses, selection
  navigation keys, and owned-but-empty Enter paths
- `SettingsSurface` search text, search editing keys, settings navigation keys,
  submenu open/close paths, and owned-but-empty activation paths

Those `True` returns remain invisible to existing callers because
`route_input()` still normalizes booleans to `()`, but they let
`InputRouter` avoid falling through to prompt/focused-editor fallback.

`InputRouter._route_surface_first()` should use `route_input_result()` when
available. It should return the `InputIntent` subset to application code, but
use `consumed=True` to stop prompt/editor fallback. This prevents a focused
`TextInput.handle_input()` edit from being applied once by the surface route and
a second time by the focused editor fallback.

## TextInput Target

`TextInput` should expose a small adapter as its editor target:

```python
def editor_input_target(self) -> object:
    return _TextInputEditorTarget(self)
```

The adapter, not `TextInput` itself, satisfies `EditorInputTarget`. This keeps
the existing low-level `TextInput.insert_text()`, `delete_backward()`, and
`delete_forward()` methods unchanged; tests currently rely on direct low-level
edits not creating undo boundaries. The `object` annotation avoids importing
`EditorInputTarget` into `text_input.py`; the router uses the returned object
structurally.

The adapter methods are high-level user edit operations:

- `insert_text()` calls `_apply_edit(lambda: field.insert_text(text))`, sets
  `_last_action="type-word"` when the value changed, and triggers `on_change`.
- `paste()` calls `_apply_edit(lambda: field.insert_text(text))`, clears
  `_last_action` when the value changed, normalizes single-line paste through
  `TextInput.insert_text()`, and triggers `on_change`.
- destructive character edits call `_apply_edit()` around the low-level delete
  primitives.
- kill, yank, undo, redo, cursor movement, and selection methods delegate to the
  existing high-level `TextInput` methods.

The adapter should expose compatibility methods whose names match the shared
helper interface:

```python
def move_to_line_start(self) -> None:
    self.field.move_to_start()

def move_to_line_end(self) -> None:
    self.field.move_to_end()

def kill_to_line_start(self) -> None:
    self.field.kill_to_start()

def kill_to_line_end(self) -> None:
    self.field.kill_to_end()
```

`TextInput.handle_input()` remains the direct focused-surface path. When a
`TextInput` is used directly as the surface focus target, `InputRouter` should
see `consumed=True` from `route_input_result()` and must not call the adapter
again.

## InputRouter Data Flow

For key events:

1. Keep the existing key release and jump-mode cleanup behavior.
2. Route surface input first through `_route_surface_first(event)`.
3. If a surface emitted `InputIntent` values, return them unchanged.
4. If the surface consumed the event without emitting intents, return `()`.
5. Ask `surface_host.current_editor_target()` for a focused editor target.
6. If a focused editor target exists:
   - route selection keys with `route_editor_selection_key()`
   - route ordinary editing keys with `route_editor_editing_key()`
   - do not route submit, escape, completion, history, jump, page movement,
     queue edit, or prompt newline to the focused editor
   - do not let submit, escape, completion, history, jump, page movement, queue
     edit, or prompt newline fall through to the prompt target while the focused
     editor target owns the editing lane
7. Continue with existing prompt-target routing only when no focused editor
   target is active.

For text and paste events:

1. For text, if prompt jump mode is active, route the character to the prompt
   target's `jump_to_char()`, clear jump mode, and return. Jump remains
   prompt-only and must not insert into a focused editor.
2. For paste, clear jump mode as today.
3. Route surface input first through `_route_surface_first(event)`.
4. If a surface emitted `InputIntent` values, return them unchanged.
5. If the surface consumed the event without emitting intents, return `()`.
6. If there is a focused editor target, insert text or paste into that target.
7. Otherwise keep the existing prompt-target behavior.

Resize and SIGWINCH continue to return `invalidate_render` and do not route to
focused editors.

## Surface Intent Semantics

Focused editor fallback only runs when the surface declined the event:
`consumed=False` and no intents. This keeps existing surfaces authoritative for:

- `surface_close`
- `dialog_cancel`
- submit callbacks handled by `TextInput.handle_input()`
- escape callbacks handled by `TextInput.handle_input()`
- selection surfaces and modal command surfaces

If a surface wants `TextInput` submit or escape callbacks, it can continue to
handle those through `TextInput.handle_input()`. A focused editor target should
also block prompt submit/escape fallback while it owns focus, so pressing Enter
inside a focused editor cannot submit unrelated prompt text. The generic
`InputRouter` fallback is only for ordinary editing operations that are
currently duplicated or unavailable when custom surface handlers decline an
event.

## Error Handling

- `current_editor_target()` returns `None` when no visible focused surface editor
  is available.
- A provider returning `None` is treated as no focused editor.
- A provider returning an incomplete editor target should fail normally when the
  helper calls a missing method; do not silently fall back to prompt editing.
- Surface routing remains defensive for application intents: non-`InputIntent`
  surface return values are not returned by `InputRouter`, but they still count
  as consumed when `route_input_result()` says the surface handled the event.

## Testing

Add focused tests before implementation:

- `SurfaceHost.current_editor_target()` returns a focused surface target exposed
  by `editor_input_target()`.
- `SurfaceHost.route_input_result()` reports `consumed=True` for boolean `True`,
  non-empty tuples, and scalar results while `route_input()` keeps its existing
  normalized return value.
- Existing stateful surfaces that consume input without emitting intents return
  `True`; searchable `SelectionSurface` and `SettingsSurface` text/filter
  edits must not fall through to prompt editing.
- Hidden or closed surface focus targets no longer provide an editor target.
- `TextInput.editor_input_target()` returns a high-level adapter.
- The `TextInput` adapter exposes the methods required by `EditorInputTarget`.
- The `TextInput` adapter preserves `on_change` callbacks and undo/redo
  boundaries for routed text, paste, and destructive edits.
- Direct `TextInput` surfaces do not double-insert when routed through
  `InputRouter`.
- `InputRouter` routes text and paste to a focused `TextInput` after the surface
  declines the event, without changing the prompt target.
- `InputRouter` routes selection and editing keys to a focused `TextInput`.
- `InputRouter` still lets surface intents win before focused editor fallback.
- Prompt jump mode consumes the next text event before focused editor fallback.
- `InputRouter` still submits prompt text when no focused editor target exists,
  and does not submit prompt text while a focused editor target is active.
- Resize/SIGWINCH still invalidate render instead of touching focused editors.

Focused verification:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_text_input.py tests/tui/test_input_routing.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/framework.py src/loushang/tui/input.py src/loushang/tui/ui_parts/text_input.py tests/tui/test_text_input.py tests/tui/test_input_routing.py
```

## Rollout Plan

1. Add `SurfaceHost.route_input_result()` and consumption tests.
2. Update existing stateful surface handlers to return `True` for
   consumed-without-intent paths and add regression tests.
3. Add `SurfaceHost.current_editor_target()` and focused target tests.
4. Add the `TextInput` editor target adapter and tests.
5. Route generic `InputRouter` text, paste, selection, and editing keys through
   the focused editor fallback.
6. Keep prompt-only behavior unchanged when no focused editor target exists.
7. Document the focused editor target boundary in `KD-002`.

Stop after this slice. A future spec can decide whether `SurfaceHost` should
support base-focus editor targets or whether a higher-level focus registry is
needed for richer widgets.

## Success Criteria

- Existing prompt `InputRouter(composer=...)` behavior remains unchanged.
- Focused `TextInput` can receive ordinary text, paste, selection, and editing
  keys through `InputRouter`.
- Focused `TextInput` never receives the same text or paste event twice.
- Routed `TextInput` edits preserve `on_change` and undo/redo behavior.
- Surface intents still win over editor fallback.
- Submit and escape for focused surfaces remain surface-owned.
- Existing searchable/selection/settings surfaces do not leak consumed input to
  prompt editing.
- Prompt jump mode remains prompt-owned.
- `NativeInputRouter` behavior remains unchanged.
- The implementation does not introduce a full widget or focus-manager system.
