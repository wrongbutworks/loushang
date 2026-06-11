# TUI Focused Editor Target Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let focused surface editors reuse generic `InputRouter` editor-key routing without leaking consumed surface input into prompt editing.

**Architecture:** Add an explicit consumed/declined result path to `SurfaceHost`, then layer focused editor target discovery on top of existing surface focus. `TextInput` exposes a high-level editor target adapter so routed edits preserve callbacks and undo, while `InputRouter` keeps prompt-only actions on the prompt lane only when no focused editor target owns editing.

**Tech Stack:** Python 3.11+, dataclasses, typing `Protocol`, pytest, existing `loushang.tui` surface/input tests, `uv --cache-dir .uv-cache run --extra dev pytest`.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-10-tui-focused-editor-target-routing-design.md`
- Prior input target spec: `docs/superpowers/specs/2026-06-09-tui-input-router-decouple-design.md`
- Input routing design note: `docs/internals/architecture/tui/native-terminal-core/key-designs/KD-002-input-event-routing.md`
- Framework implementation: `src/loushang/tui/framework.py`
- Generic input routing: `src/loushang/tui/input.py`
- Text input implementation: `src/loushang/tui/ui_parts/text_input.py`
- Stateful surfaces: `src/loushang/tui/surfaces.py`
- Framework tests: `tests/tui/test_render_framework.py`
- Surface tests: `tests/tui/test_surfaces.py`
- Text input tests: `tests/tui/test_text_input.py`
- Input routing tests: `tests/tui/test_input_routing.py`

## File Structure

- Modify `src/loushang/tui/framework.py`
  - Add `EditorInputTargetProvider`.
  - Add `SurfaceInputRouteResult`.
  - Add `SurfaceHost.route_input_result()`.
  - Add `SurfaceHost.current_editor_target()`.
  - Keep `SurfaceHost.route_input()` as a compatibility wrapper.
- Modify `src/loushang/tui/surfaces.py`
  - Return `True` from existing stateful consumed-without-intent paths in `SelectionSurface` and `SettingsSurface`.
  - Keep intent-producing paths unchanged.
- Modify `src/loushang/tui/ui_parts/text_input.py`
  - Add a private `_TextInputEditorTarget` adapter.
  - Add `TextInput.editor_input_target()` returning the adapter.
  - Do not change direct low-level `TextInput.insert_text()` undo semantics.
- Modify `src/loushang/tui/input.py`
  - Teach `InputRouter` to read surface consumed state.
  - Add focused editor fallback after surface decline and before prompt editing.
  - Keep active prompt jump-mode text handling before focused editor insertion.
- Modify `tests/tui/test_render_framework.py`
  - Cover consumed route results and focused editor target discovery.
- Modify `tests/tui/test_surfaces.py`
  - Cover `True` returns from stateful consumed surface paths.
- Modify `tests/tui/test_text_input.py`
  - Cover adapter methods, callbacks, undo/redo, and direct low-level edit compatibility.
- Modify `tests/tui/test_input_routing.py`
  - Cover focused editor fallback, no double insertion, surface intent priority, prompt submit suppression, jump-mode priority, and unchanged no-focus prompt behavior.
- Modify `docs/internals/architecture/tui/native-terminal-core/key-designs/KD-002-input-event-routing.md`
  - Document focused editor target routing and surface consumed semantics.

## Task 1: SurfaceHost Consumed Route Result

**Files:**
- Modify: `tests/tui/test_render_framework.py`
- Modify: `src/loushang/tui/framework.py`

- [ ] **Step 1: Write failing tests for consumed route results**

Add near the existing `FocusTarget` helper:

```python
class ReturningFocusTarget(FocusableMixin):
    def __init__(self, result: Any) -> None:
        super().__init__()
        self.result = result
        self.events: list[Any] = []

    def handle_input(self, event: Any) -> Any:
        self.events.append(event)
        return self.result
```

Add tests:

```python
def test_surface_host_route_input_result_preserves_consumption_without_changing_route_input() -> None:
    cases: tuple[tuple[Any, tuple[Any, ...], bool], ...] = (
        (None, (), False),
        (False, (), False),
        (True, (), True),
        ("handled", ("handled",), True),
        (("handled",), ("handled",), True),
    )
    for result, expected_intents, expected_consumed in cases:
        target = ReturningFocusTarget(result)
        host = SurfaceHost()
        host.open_surface(Surface(renderable=TextRenderable(("surface",), []), focus_target=target))

        routed = host.route_input_result("x")

        assert routed.intents == expected_intents
        assert routed.consumed is expected_consumed
        assert host.route_input("x") == expected_intents
```

Add close-intent coverage:

```python
def test_surface_host_route_input_result_closes_on_close_intent() -> None:
    target = ReturningFocusTarget(InputIntent(kind="surface_close"))
    host = SurfaceHost()
    handle = host.open_surface(Surface(renderable=TextRenderable(("surface",), []), focus_target=target))

    routed = host.route_input_result(InputEvent(kind="key", key="escape"))

    assert routed.intents == (InputIntent(kind="surface_close"),)
    assert routed.consumed is True
    assert host.entries == []
    assert handle.entry.close_reason == "surface_close"
```

- [ ] **Step 2: Run red test**

Run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_framework.py::test_surface_host_route_input_result_preserves_consumption_without_changing_route_input tests/tui/test_render_framework.py::test_surface_host_route_input_result_closes_on_close_intent -q
```

Expected: fail because `SurfaceHost.route_input_result` does not exist.

- [ ] **Step 3: Implement `SurfaceInputRouteResult` and wrapper**

In `src/loushang/tui/framework.py`, add:

```python
@runtime_checkable
class EditorInputTargetProvider(Protocol):
    def editor_input_target(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class SurfaceInputRouteResult:
    intents: tuple[Any, ...]
    consumed: bool
```

Add helper:

```python
def _surface_input_consumed(result: Any, intents: tuple[Any, ...]) -> bool:
    if isinstance(result, bool):
        return result
    if result is None:
        return False
    if isinstance(result, tuple):
        return bool(result)
    return True
```

Refactor `SurfaceHost.route_input()` into:

```python
def route_input_result(
    self,
    event: Any,
    *,
    close_on_intents: tuple[str, ...] = ("surface_close", "dialog_cancel"),
) -> SurfaceInputRouteResult:
    self._sync_focus_for_visible_entries(self._last_known_size())
    entry = self._current_focus_entry()
    if entry is None:
        result = self.handle_input(event)
    else:
        result = self._handle_entry_input(entry, event)
    intents = _normalize_surface_input_result(result)
    if entry is not None:
        for intent in intents:
            if getattr(intent, "kind", None) in close_on_intents:
                self.close_surface(entry, reason=getattr(intent, "kind", "closed"))
                break
    return SurfaceInputRouteResult(
        intents=intents,
        consumed=_surface_input_consumed(result, intents),
    )


def route_input(
    self,
    event: Any,
    *,
    close_on_intents: tuple[str, ...] = ("surface_close", "dialog_cancel"),
) -> tuple[Any, ...]:
    return self.route_input_result(
        event,
        close_on_intents=close_on_intents,
    ).intents
```

- [ ] **Step 4: Run green test**

Run the same focused pytest command. Expected: pass.

- [ ] **Step 5: Commit**

```sh
git add src/loushang/tui/framework.py tests/tui/test_render_framework.py
git commit -m "feat(tui): expose surface input consumption"
```

## Task 2: Stateful Surfaces Return True For Consumed Paths

**Files:**
- Modify: `tests/tui/test_surfaces.py`
- Modify: `src/loushang/tui/surfaces.py`

- [ ] **Step 1: Write failing tests for consumed-without-intent returns**

Update existing assertions or add focused tests:

```python
def test_selection_surface_consumed_paths_return_true_without_intents() -> None:
    surface = SelectionSurface(
        [SelectItem("Alpha"), SelectItem("Model")],
        enable_search=True,
        filter_mode="contains",
    )

    assert surface.handle_input(InputEvent(kind="text", text="mo")) is True
    assert surface.handle_input(InputEvent(kind="key", key="backspace")) is True
    assert surface.handle_input(InputEvent(kind="key", key="down")) is True


def test_selection_surface_empty_owned_enter_and_mouse_return_true() -> None:
    surface = SelectionSurface([], empty_text="No items")

    assert surface.handle_input(InputEvent(kind="key", key="enter")) is True
    assert surface.handle_input(InputEvent(kind="mouse", mouse_button=0, mouse_row=0, mouse_action="press")) is True
```

Add settings tests:

```python
def test_settings_surface_consumed_paths_return_true_without_intents() -> None:
    surface = SettingsSurface(
        [
            SettingItem(id="theme", label="Theme", current_value="dark"),
            SettingItem(id="model", label="Model", current_value="kimi"),
        ],
        enable_search=True,
    )

    assert surface.handle_input(InputEvent(kind="text", text="mo")) is True
    assert surface.handle_input(InputEvent(kind="key", key="backspace")) is True
    assert surface.handle_input(InputEvent(kind="key", key="down")) is True
```

Update `test_settings_surface_can_delegate_value_selection_to_submenu` first Enter assertion from `is None` to `is True`.

- [ ] **Step 2: Run red tests**

Run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_surfaces.py -q
```

Expected: fail on `is True` assertions.

- [ ] **Step 3: Return `True` from stateful consumed paths**

In `SelectionSurface.handle_input`, change consumed-without-intent branches:

- search text after `_apply_filter(...)`: `return True`
- mouse event after `_handle_mouse(...)`: `return True`
- search editing key after `_apply_filter(...)`: `return True`
- `up`, `down`, `pageUp`, `pageDown`, `home`, `end`: return `True`
- Enter with no selected item: return `True`

In `SettingsSurface.handle_input`, change consumed-without-intent branches:

- search text after mutation: `return True`
- search editing key after mutation: `return True`
- settings navigation keys: return `True`
- activation paths where `_activate_setting()` opens a submenu or owns an empty activation: return `True`

In `_handle_submenu_input`, return `True` when the submenu consumed an event but produced only a close/cancel side effect or a boolean true.

Widen annotations from `InputIntent | None` to `InputIntent | bool | None` for the changed methods.

- [ ] **Step 4: Run green tests**

Run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_surfaces.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```sh
git add src/loushang/tui/surfaces.py tests/tui/test_surfaces.py
git commit -m "fix(tui): mark stateful surface inputs consumed"
```

## Task 3: Focused Editor Target Discovery

**Files:**
- Modify: `tests/tui/test_render_framework.py`
- Modify: `src/loushang/tui/framework.py`

- [ ] **Step 1: Write failing tests for current editor target**

Add helper:

```python
class EditorProviderFocusTarget(FocusTarget):
    def __init__(self, name: str, target: object | None) -> None:
        super().__init__(name)
        self.target = target

    def editor_input_target(self) -> object | None:
        return self.target
```

Add tests:

```python
def test_surface_host_returns_current_visible_surface_editor_target() -> None:
    editor_target = object()
    focus = EditorProviderFocusTarget("editor", editor_target)
    host = SurfaceHost()
    host.open_surface(Surface(renderable=TextRenderable(("editor",), []), focus_target=focus))

    assert host.current_editor_target() is editor_target


def test_surface_host_ignores_base_hidden_and_closed_editor_targets() -> None:
    base_target = object()
    base = EditorProviderFocusTarget("base", base_target)
    base.focus()
    focus = EditorProviderFocusTarget("editor", object())
    host = SurfaceHost(base_focus=base)

    assert host.current_editor_target() is None

    handle = host.open_surface(Surface(renderable=TextRenderable(("editor",), []), focus_target=focus))
    assert host.current_editor_target() is focus.target

    handle.set_hidden(True)
    assert host.current_editor_target() is None

    handle.set_hidden(False)
    assert host.current_editor_target() is focus.target

    handle.close("done")
    assert host.current_editor_target() is None
```

- [ ] **Step 2: Run red tests**

Run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_framework.py::test_surface_host_returns_current_visible_surface_editor_target tests/tui/test_render_framework.py::test_surface_host_ignores_base_hidden_and_closed_editor_targets -q
```

Expected: fail because `current_editor_target()` does not exist.

- [ ] **Step 3: Implement discovery**

In `SurfaceHost`, add:

```python
def current_editor_target(self) -> Any | None:
    self._sync_focus_for_visible_entries(self._last_known_size())
    entry = self._current_focus_entry()
    if entry is None:
        return None
    focus_target = entry.surface.focus_target
    if not isinstance(focus_target, EditorInputTargetProvider):
        return None
    target = focus_target.editor_input_target()
    return target if target is not None else None
```

Keep this surface-only; do not inspect `base_focus`.

- [ ] **Step 4: Run green tests**

Run the same focused pytest command. Expected: pass.

- [ ] **Step 5: Commit**

```sh
git add src/loushang/tui/framework.py tests/tui/test_render_framework.py
git commit -m "feat(tui): expose focused editor targets"
```

## Task 4: TextInput High-Level Editor Target Adapter

**Files:**
- Modify: `tests/tui/test_text_input.py`
- Modify: `src/loushang/tui/ui_parts/text_input.py`

- [ ] **Step 1: Write failing tests for adapter behavior**

Add:

```python
def test_text_input_editor_input_target_routes_high_level_text_edits() -> None:
    changes: list[str] = []
    field = TextInput(on_change=changes.append)
    target = field.editor_input_target()

    target.insert_text("ab")
    target.paste("c\nd")

    assert field.value == "abc d"
    assert changes == ["ab", "abc d"]
    assert field.undo()
    assert field.value == "ab"
    assert field.undo()
    assert field.value == ""


def test_text_input_editor_input_target_routes_destructive_edits_with_undo() -> None:
    changes: list[str] = []
    field = TextInput(on_change=changes.append)
    target = field.editor_input_target()

    target.insert_text("abc")
    target.delete_backward()

    assert field.value == "ab"
    assert changes == ["abc", "ab"]
    assert field.undo()
    assert field.value == "abc"
```

Add alias coverage:

```python
def test_text_input_editor_input_target_exposes_shared_editor_operations() -> None:
    field = TextInput()
    target = field.editor_input_target()

    target.insert_text("alpha beta")
    target.move_to_line_start()
    target.move_word_right()
    target.kill_to_line_end()

    assert field.value == "alpha"
    assert field.kill_ring == (" beta",)
```

Keep `test_text_input_direct_edits_preserve_existing_undo_boundary` unchanged.

- [ ] **Step 2: Run red tests**

Run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_text_input.py::test_text_input_editor_input_target_routes_high_level_text_edits tests/tui/test_text_input.py::test_text_input_editor_input_target_routes_destructive_edits_with_undo tests/tui/test_text_input.py::test_text_input_editor_input_target_exposes_shared_editor_operations -q
```

Expected: fail because `editor_input_target()` does not exist.

- [ ] **Step 3: Implement adapter**

In `src/loushang/tui/ui_parts/text_input.py`, add:

```python
def editor_input_target(self) -> object:
    return _TextInputEditorTarget(self)
```

Add a private dataclass after `TextInput`:

```python
@dataclass(frozen=True, slots=True)
class _TextInputEditorTarget:
    field: TextInput

    def insert_text(self, text: str) -> None:
        changed = self.field._apply_edit(lambda: self.field.insert_text(text))
        if changed:
            self.field._last_action = "type-word"

    def paste(self, text: str) -> None:
        changed = self.field._apply_edit(lambda: self.field.insert_text(text))
        if changed:
            self.field._last_action = None
```

Implement the remaining protocol methods by delegating to existing `TextInput`
methods. Character deletes must call `_apply_edit()` around `delete_backward`
and `delete_forward`; kill/yank/undo/redo can call existing high-level methods.

- [ ] **Step 4: Run green tests**

Run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_text_input.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```sh
git add src/loushang/tui/ui_parts/text_input.py tests/tui/test_text_input.py
git commit -m "feat(tui): add text input editor target adapter"
```

## Task 5: InputRouter Focused Editor Fallback

**Files:**
- Modify: `tests/tui/test_input_routing.py`
- Modify: `src/loushang/tui/input.py`

- [ ] **Step 1: Write focused editor routing tests**

Add `CommandSurface`, `SelectItem`, and `TextInput` to the top-level
`loushang.tui` import in `tests/tui/test_input_routing.py`.

Add helper:

```python
class DecliningEditorFocus(FocusableMixin):
    def __init__(self, target: object) -> None:
        super().__init__()
        self.target = target

    def editor_input_target(self) -> object:
        return self.target

    def handle_input(self, event: Any) -> bool:
        return False
```

Add:

```python
def test_input_router_routes_text_and_paste_to_declined_focused_editor_target() -> None:
    prompt = Composer(prompt="> ")
    field = TextInput()
    host = SurfaceHost()
    host.open_surface(
        Surface(
            renderable=DummyRenderable(),
            focus_target=DecliningEditorFocus(field.editor_input_target()),
        )
    )
    router = InputRouter(composer=prompt, surface_host=host)

    assert router.route(InputEvent(kind="text", text="ab")) == ()
    assert router.route(InputEvent(kind="paste", text="c\nd")) == ()

    assert field.value == "abc d"
    assert prompt.value == ""
```

Add:

```python
def test_input_router_does_not_double_insert_direct_focused_text_input_surface() -> None:
    changes: list[str] = []
    prompt = Composer(prompt="> ")
    field = TextInput(on_change=changes.append)
    host = SurfaceHost()
    host.open_surface(Surface(renderable=DummyRenderable(), focus_target=field))
    router = InputRouter(composer=prompt, surface_host=host)

    assert router.route(InputEvent(kind="text", text="a")) == ()

    assert field.value == "a"
    assert changes == ["a"]
    assert prompt.value == ""
```

Add:

```python
def test_input_router_routes_focused_editor_selection_and_editing_keys() -> None:
    prompt = Composer(prompt="> ")
    field = TextInput()
    target = field.editor_input_target()
    target.insert_text("abc")
    host = SurfaceHost()
    host.open_surface(Surface(renderable=DummyRenderable(), focus_target=DecliningEditorFocus(target)))
    router = InputRouter(composer=prompt, surface_host=host)

    assert router.route(InputEvent(kind="key", key="shift+left")) == ()
    assert field.selected_range == (2, 3)
    assert router.route(InputEvent(kind="key", key="backspace")) == ()

    assert field.value == "ab"
    assert prompt.value == ""
```

Add priority and prompt-lane tests:

```python
def test_input_router_surface_intent_wins_before_focused_editor_fallback() -> None:
    class ClosingEditorFocus(DecliningEditorFocus):
        def handle_input(self, event: Any) -> InputIntent | None:
            if isinstance(event, InputEvent) and event.kind == "key":
                return InputIntent(kind="surface_close")
            return None

    prompt = Composer(prompt="> ")
    field = TextInput()
    host = SurfaceHost()
    host.open_surface(Surface(renderable=DummyRenderable(), focus_target=ClosingEditorFocus(field.editor_input_target())))
    router = InputRouter(composer=prompt, surface_host=host)

    assert router.route(InputEvent(kind="key", key="left")) == (InputIntent(kind="surface_close"),)
    assert field.value == ""
    assert host.entries == []
```

```python
def test_input_router_does_not_submit_prompt_while_focused_editor_target_is_active() -> None:
    prompt = Composer(prompt="> ")
    prompt.insert_text("prompt")
    field = TextInput()
    host = SurfaceHost()
    host.open_surface(Surface(renderable=DummyRenderable(), focus_target=DecliningEditorFocus(field.editor_input_target())))
    router = InputRouter(composer=prompt, surface_host=host)

    assert router.route(InputEvent(kind="key", key="enter")) == ()
    assert prompt.value == "prompt"
```

Add explicit cancel suppression coverage:

```python
def test_input_router_does_not_abort_running_prompt_while_focused_editor_target_is_active() -> None:
    prompt = Composer(prompt="> ")
    field = TextInput()
    host = SurfaceHost()
    host.open_surface(Surface(renderable=DummyRenderable(), focus_target=DecliningEditorFocus(field.editor_input_target())))
    router = InputRouter(composer=prompt, surface_host=host, running=True)

    assert router.route(InputEvent(kind="key", key="escape")) == ()
```

```python
def test_input_router_prompt_jump_text_wins_before_focused_editor_fallback() -> None:
    prompt = Composer(prompt="> ")
    prompt.insert_text("abc def")
    prompt.move_to_line_start()
    router = InputRouter(composer=prompt)
    assert router.route(InputEvent(kind="key", key="ctrl+]")) == ()

    field = TextInput()
    host = SurfaceHost()
    host.open_surface(Surface(renderable=DummyRenderable(), focus_target=DecliningEditorFocus(field.editor_input_target())))
    router.surface_host = host

    assert router.route(InputEvent(kind="text", text="d")) == ()
    prompt.delete_forward()

    assert prompt.value == "abc ef"
    assert field.value == ""
```

Add a surface-consumed regression:

```python
def test_input_router_does_not_leak_searchable_surface_text_to_prompt() -> None:
    prompt = Composer(prompt="> ")
    host = SurfaceHost()
    surface = CommandSurface([SelectItem("/status", value="/status")])
    host.open_surface(Surface(renderable=surface, focus_target=surface))
    router = InputRouter(composer=prompt, surface_host=host)

    assert router.route(InputEvent(kind="text", text="sta")) == ()

    assert prompt.value == ""
    assert tuple(item.selected_value for item in surface._filtered_items) == ("/status",)
```

- [ ] **Step 2: Run red tests**

Run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_input_routing.py -q
```

Expected: focused editor tests fail because `InputRouter` has no focused editor fallback and no consumed route handling.

- [ ] **Step 3: Add private surface route result to `InputRouter`**

In `src/loushang/tui/input.py`, add a private dataclass:

```python
@dataclass(frozen=True, slots=True)
class _SurfaceRoute:
    intents: tuple[InputIntent, ...] = ()
    consumed: bool = False
```

Update `_route_surface_first()` to return `_SurfaceRoute`:

- Prefer `surface_host.route_input_result(_legacy_event(event))`.
- Filter returned values to `InputIntent` before returning to app code.
- Preserve `consumed=True` from the host even when there are no `InputIntent` values.
- Keep a compatibility path for hosts that only expose `route_input()` or `handle_input()`.

- [ ] **Step 4: Add focused editor target lookup**

Add:

```python
def _focused_editor_target(self) -> EditorInputTarget | None:
    if self.surface_host is None:
        return None
    current = getattr(self.surface_host, "current_editor_target", None)
    if not callable(current):
        return None
    target = current()
    return target if target is not None else None
```

Use structural typing; no runtime `isinstance` protocol check is needed.

- [ ] **Step 5: Update route ordering**

For key events:

1. Keep key release return.
2. Keep existing jump-mode cleanup for key events.
3. Call `_route_surface_first(event)`.
4. Return surface intents if present.
5. Return `()` if surface consumed.
6. If a focused editor target exists:
   - route selection keys to it
   - route ordinary editing keys to it
   - return `()` for all remaining key events so prompt submit/newline/history/completion does not run while focused editor owns editing
7. Continue existing prompt routing when no focused editor target exists.

For text events:

1. If `_jump_mode` is active, route to prompt `jump_to_char()`, clear jump, and return.
2. Route surface first.
3. Stop on surface intents or consumed.
4. Insert into focused editor target when present.
5. Otherwise insert into prompt target.

For paste events:

1. Clear `_jump_mode`.
2. Route surface first.
3. Stop on surface intents or consumed.
4. Paste into focused editor target when present.
5. Otherwise paste into prompt target.

- [ ] **Step 6: Run green tests**

Run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_input_routing.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```sh
git add src/loushang/tui/input.py tests/tui/test_input_routing.py
git commit -m "feat(tui): route input to focused editor targets"
```

## Task 6: Documentation And Verification

**Files:**
- Modify: `docs/internals/architecture/tui/native-terminal-core/key-designs/KD-002-input-event-routing.md`

- [ ] **Step 1: Write documentation update**

In `KD-002`, extend the generic prompt target paragraph with:

```markdown
Focused surface editors may expose an editor target through `editor_input_target()`.
`SurfaceHost.route_input_result()` distinguishes surface intents from consumed
events without changing the compatibility `route_input()` return value. Generic
`InputRouter` routing stays surface-first: surface intents win, consumed surface
events stop fallback, and only declined events may route ordinary text, paste,
selection, and editing keys to the focused editor target. Prompt-only actions
such as submit, newline, history, completion, queue editing, and jump setup do
not mutate prompt state while a focused editor target owns the editing lane.
```

In the test obligations list, add:

```markdown
- focused surface editor targets receive ordinary text/editing only after the surface declines the event
- consumed surface text, search, and navigation events do not leak into prompt editing
```

- [ ] **Step 2: Run focused verification**

Run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_render_framework.py tests/tui/test_surfaces.py tests/tui/test_text_input.py tests/tui/test_input_routing.py -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/framework.py src/loushang/tui/input.py src/loushang/tui/surfaces.py src/loushang/tui/ui_parts/text_input.py tests/tui/test_render_framework.py tests/tui/test_surfaces.py tests/tui/test_text_input.py tests/tui/test_input_routing.py
```

Expected: all pass.

- [ ] **Step 3: Run broader TUI verification**

Run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: all TUI tests pass.

- [ ] **Step 4: Commit docs and any final cleanup**

```sh
git add docs/internals/architecture/tui/native-terminal-core/key-designs/KD-002-input-event-routing.md
git commit -m "docs(tui): document focused editor input routing"
```

If final cleanup changed code or tests, include those files in the commit with the same message only if they are strictly related to documentation wording or lint cleanup. Otherwise create a separate targeted commit.

## Final Verification

Before opening a PR or reporting completion, run:

```sh
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/framework.py src/loushang/tui/input.py src/loushang/tui/surfaces.py src/loushang/tui/ui_parts/text_input.py tests/tui/test_render_framework.py tests/tui/test_surfaces.py tests/tui/test_text_input.py tests/tui/test_input_routing.py
git status --short
```

Expected:

- TUI tests pass.
- Ruff passes.
- Working tree is clean except for intentional untracked files outside this branch, if any.
