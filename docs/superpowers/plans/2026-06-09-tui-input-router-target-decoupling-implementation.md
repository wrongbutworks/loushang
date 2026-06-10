# TUI InputRouter Target Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor generic TUI input routing so `InputRouter` routes through a prompt target adapter instead of directly depending on concrete `Composer` methods.

**Architecture:** Keep the first slice behavior-preserving. Define target protocols and `ComposerInputTarget` in `src/loushang/tui/input.py`, route generic `InputRouter` through an internal `_target`, and keep `InputRouter(composer=...)` as the compatibility path. Native coding input may reuse target helpers only where that does not change its product-specific routing order.

**Tech Stack:** Python 3.11+, dataclasses, typing `Protocol`, pytest, existing `loushang.tui` input tests, `uv --cache-dir .uv-cache run --extra dev pytest`.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-09-tui-input-router-decouple-design.md`
- Generic input implementation: `src/loushang/tui/input.py`
- Native coding input implementation: `src/loushang/coding/ui/native_input.py`
- Generic input tests: `tests/tui/test_input_routing.py`
- Native input tests: `tests/coding/test_native_coding_tui_input.py`
- Existing routing design note: `docs/internals/architecture/tui/native-terminal-core/key-designs/KD-002-input-event-routing.md`

## File Structure

- Modify `src/loushang/tui/input.py`
  - Add `EditorInputTarget`, `PromptInputTarget`, `ComposerInputTarget`, generic route helper functions, and `InputRouter` target construction.
  - Keep these in `input.py` for this slice to avoid import churn. Split to a new `input_targets.py` only in a later cleanup if the module becomes harder to navigate.
- Modify `tests/tui/test_input_routing.py`
  - Add fake target tests for constructor rules and protocol routing.
  - Keep existing Composer-backed tests as behavior parity coverage.
- Modify `src/loushang/coding/ui/native_input.py`
  - Reuse target helpers for ordinary selection/editing/completion routing without changing native priority order.
- Modify `tests/coding/test_native_coding_tui_input.py`
  - Add behavior coverage that proves native slash-command selected completion stays native-only.
- Modify `docs/internals/architecture/tui/native-terminal-core/key-designs/KD-002-input-event-routing.md`
  - Document the new target boundary and generic/native routing distinction.

## Task 1: Add Red Tests for Target Construction and Helper Routing

**Files:**
- Modify: `tests/tui/test_input_routing.py`

- [ ] **Step 1: Add pytest import**

At the top of `tests/tui/test_input_routing.py`, add:

```python
import pytest
```

- [ ] **Step 2: Add imports for new symbols**

Extend the existing `from loushang.tui.input import ...` usage or add a direct import:

```python
from loushang.tui.input import (
    route_editor_editing_key,
    route_editor_selection_key,
)
```

Do not import these from `loushang.tui.__init__`; this slice does not need to expand the top-level public API.

- [ ] **Step 3: Add a fake prompt target test double**

Add this helper near the existing test helper classes:

```python
@dataclass(slots=True)
class FakePromptTarget:
    value: str = ""
    browsing_history: bool = False
    has_completions: bool = False
    calls: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)

    def insert_text(self, text: str) -> None:
        self.calls.append(f"insert_text:{text}")
        self.value += text

    def paste(self, text: str) -> None:
        self.calls.append(f"paste:{text}")
        self.value += text

    def clear(self) -> None:
        self.calls.append("clear")
        self.value = ""

    def add_history(self, text: str) -> None:
        self.calls.append(f"add_history:{text}")
        self.history.append(text)

    def insert_newline(self) -> None:
        self.calls.append("insert_newline")
        self.value += "\n"

    def _record(self, name: str) -> None:
        self.calls.append(name)

    def move_left(self) -> None:
        self._record("move_left")

    def move_right(self) -> None:
        self._record("move_right")

    def move_word_left(self) -> None:
        self._record("move_word_left")

    def move_word_right(self) -> None:
        self._record("move_word_right")

    def move_to_line_start(self) -> None:
        self._record("move_to_line_start")

    def move_to_line_end(self) -> None:
        self._record("move_to_line_end")

    def select_char_left(self) -> None:
        self._record("select_char_left")

    def select_char_right(self) -> None:
        self._record("select_char_right")

    def select_word_left(self) -> None:
        self._record("select_word_left")

    def select_word_right(self) -> None:
        self._record("select_word_right")

    def select_line_start(self) -> None:
        self._record("select_line_start")

    def select_line_end(self) -> None:
        self._record("select_line_end")

    def delete_backward(self) -> None:
        self._record("delete_backward")

    def delete_forward(self) -> None:
        self._record("delete_forward")

    def delete_word_backward(self) -> None:
        self._record("delete_word_backward")

    def delete_word_forward(self) -> None:
        self._record("delete_word_forward")

    def kill_to_line_start(self) -> None:
        self._record("kill_to_line_start")

    def kill_to_line_end(self) -> None:
        self._record("kill_to_line_end")

    def yank(self) -> None:
        self._record("yank")

    def yank_pop(self) -> None:
        self._record("yank_pop")

    def undo(self) -> None:
        self._record("undo")

    def redo(self) -> None:
        self._record("redo")

    def history_previous(self) -> None:
        self._record("history_previous")

    def history_next(self) -> None:
        self._record("history_next")

    def move_visual_up(self, *, width: int) -> bool:
        self.calls.append(f"move_visual_up:{width}")
        return False

    def move_visual_down(self, *, width: int) -> bool:
        self.calls.append(f"move_visual_down:{width}")
        return False

    def move_visual_page_up(self, *, width: int, visible_lines: int) -> None:
        self.calls.append(f"move_visual_page_up:{width}:{visible_lines}")

    def move_visual_page_down(self, *, width: int, visible_lines: int) -> None:
        self.calls.append(f"move_visual_page_down:{width}:{visible_lines}")

    def jump_to_char(self, text: str, *, direction: Literal["forward", "backward"]) -> None:
        self.calls.append(f"jump_to_char:{direction}:{text}")

    def refresh_completions(self, *, force: bool = False, explicit: bool = False) -> None:
        self.calls.append(f"refresh_completions:{force}:{explicit}")
        self.has_completions = True

    def apply_selected_completion(self) -> None:
        self.calls.append("apply_selected_completion")

    def select_previous_completion(self) -> None:
        self.calls.append("select_previous_completion")

    def select_next_completion(self) -> None:
        self.calls.append("select_next_completion")

    def clear_completion_items(self) -> None:
        self.calls.append("clear_completion_items")
        self.has_completions = False
```

Also add these imports to the test file:

```python
from dataclasses import dataclass, field
from typing import Literal
```

If `dataclass` is already imported, only add `field`.

- [ ] **Step 4: Add constructor and target routing tests**

Add:

```python
def test_input_router_rejects_missing_prompt_target() -> None:
    with pytest.raises(TypeError, match="requires composer or target"):
        InputRouter()


def test_input_router_rejects_composer_and_target_together() -> None:
    with pytest.raises(TypeError, match="composer or target"):
        InputRouter(composer=Composer(prompt="> "), target=FakePromptTarget())


def test_input_router_routes_text_paste_and_submit_through_target() -> None:
    target = FakePromptTarget()
    router = InputRouter(target=target)

    assert router.route(InputEvent(kind="text", text="he")) == ()
    assert router.route(InputEvent(kind="paste", text="llo")) == ()
    assert router.route(InputEvent(kind="key", key="enter")) == (InputIntent(kind="submit", text="hello"),)

    assert target.calls == [
        "insert_text:he",
        "paste:llo",
        "add_history:hello",
        "clear",
    ]
    assert target.history == ["hello"]
    assert target.value == ""
```

- [ ] **Step 5: Add helper routing tests**

Add:

```python
def test_editor_key_helpers_route_to_target_operations() -> None:
    target = FakePromptTarget()

    assert route_editor_editing_key(target, "left")
    assert route_editor_selection_key(target, "shift+left")

    assert target.calls == ["move_left", "select_char_left"]
```

- [ ] **Step 6: Run new tests and verify RED**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest \
  tests/tui/test_input_routing.py::test_input_router_rejects_missing_prompt_target \
  tests/tui/test_input_routing.py::test_input_router_rejects_composer_and_target_together \
  tests/tui/test_input_routing.py::test_input_router_routes_text_paste_and_submit_through_target \
  tests/tui/test_input_routing.py::test_editor_key_helpers_route_to_target_operations \
  -q
```

Expected: FAIL because `InputRouter(target=...)`, constructor validation, and `route_editor_*` helpers do not exist yet.

- [ ] **Step 7: Leave red tests uncommitted**

Do not commit Task 1 by itself. Continue to Tasks 2 and 3, then commit the tests
and green implementation together.

## Task 2: Add Target Protocols, Composer Adapter, and Helper Functions

**Files:**
- Modify: `src/loushang/tui/input.py`
- Test: `tests/tui/test_input_routing.py`

- [ ] **Step 1: Add typing and dataclass imports**

Change imports in `src/loushang/tui/input.py`:

```python
from dataclasses import InitVar, dataclass, field
from typing import Literal, Protocol
```

Use only the imports actually needed after implementation.

- [ ] **Step 2: Add target protocols**

Place these above `InputRouter`:

```python
class EditorInputTarget(Protocol):
    def insert_text(self, text: str) -> None: ...
    def paste(self, text: str) -> None: ...
    def move_left(self) -> None: ...
    def move_right(self) -> None: ...
    def move_word_left(self) -> None: ...
    def move_word_right(self) -> None: ...
    def move_to_line_start(self) -> None: ...
    def move_to_line_end(self) -> None: ...
    def select_char_left(self) -> None: ...
    def select_char_right(self) -> None: ...
    def select_word_left(self) -> None: ...
    def select_word_right(self) -> None: ...
    def select_line_start(self) -> None: ...
    def select_line_end(self) -> None: ...
    def delete_backward(self) -> None: ...
    def delete_forward(self) -> None: ...
    def delete_word_backward(self) -> None: ...
    def delete_word_forward(self) -> None: ...
    def kill_to_line_start(self) -> None: ...
    def kill_to_line_end(self) -> None: ...
    def yank(self) -> None: ...
    def yank_pop(self) -> None: ...
    def undo(self) -> None: ...
    def redo(self) -> None: ...


class PromptInputTarget(EditorInputTarget, Protocol):
    @property
    def value(self) -> str: ...

    @property
    def browsing_history(self) -> bool: ...

    @property
    def has_completions(self) -> bool: ...

    def clear(self) -> None: ...
    def add_history(self, text: str) -> None: ...
    def insert_newline(self) -> None: ...
    def history_previous(self) -> None: ...
    def history_next(self) -> None: ...
    def move_visual_up(self, *, width: int) -> bool: ...
    def move_visual_down(self, *, width: int) -> bool: ...
    def move_visual_page_up(self, *, width: int, visible_lines: int) -> None: ...
    def move_visual_page_down(self, *, width: int, visible_lines: int) -> None: ...
    def jump_to_char(self, text: str, *, direction: Literal["forward", "backward"]) -> None: ...
    def refresh_completions(self, *, force: bool = False, explicit: bool = False) -> None: ...
    def apply_selected_completion(self) -> None: ...
    def select_previous_completion(self) -> None: ...
    def select_next_completion(self) -> None: ...
    def clear_completion_items(self) -> None: ...
```

- [ ] **Step 3: Add ComposerInputTarget**

Add below the protocols:

```python
@dataclass(frozen=True, slots=True)
class ComposerInputTarget:
    composer: Composer

    @property
    def value(self) -> str:
        return self.composer.value

    @property
    def browsing_history(self) -> bool:
        return self.composer.browsing_history

    @property
    def has_completions(self) -> bool:
        return self.composer.has_completions
```

Then implement all protocol methods as direct delegations to `self.composer`.
Do not add new behavior or validation in the adapter.

- [ ] **Step 4: Add generic helper functions**

Rename the helper bodies by introducing these target-based helper signatures:

```python
def route_editor_editing_key(
    target: EditorInputTarget,
    key: str,
    *,
    keybindings: KeybindingManager | None = None,
) -> bool: ...


def route_editor_selection_key(
    target: EditorInputTarget,
    key: str,
    *,
    keybindings: KeybindingManager | None = None,
) -> bool: ...


def route_prompt_completion_key(
    target: PromptInputTarget,
    key: str,
    *,
    keybindings: KeybindingManager | None = None,
) -> bool: ...
```

Move the current `route_composer_editing_key()` and `route_composer_selection_key()` bodies into the first two helpers, replacing `composer` with `target`.

`route_prompt_completion_key()` must contain only this completion navigation/cancel/apply logic:

```python
def route_prompt_completion_key(
    target: PromptInputTarget,
    key: str,
    *,
    keybindings: KeybindingManager | None = None,
) -> bool:
    keybindings = keybindings or KeybindingManager()
    if keybindings.matches(key, "tui.select.up"):
        target.select_previous_completion()
        return True
    if keybindings.matches(key, "tui.select.down"):
        target.select_next_completion()
        return True
    if keybindings.matches(key, "tui.input.tab"):
        target.apply_selected_completion()
        return True
    if keybindings.matches(key, "tui.select.cancel"):
        target.clear_completion_items()
        return True
    return False
```

- [ ] **Step 5: Keep compatibility wrappers**

Replace old helpers with wrappers:

```python
def route_composer_editing_key(
    composer: Composer,
    key: str,
    *,
    keybindings: KeybindingManager | None = None,
) -> bool:
    return route_editor_editing_key(ComposerInputTarget(composer), key, keybindings=keybindings)
```

Do the same for `route_composer_selection_key()`.

- [ ] **Step 6: Run helper tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest \
  tests/tui/test_input_routing.py::test_editor_key_helpers_route_to_target_operations \
  -q
```

Expected: PASS.

- [ ] **Step 7: Run existing input routing tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_input_routing.py -q
```

Expected: constructor target tests still FAIL until Task 3; existing Composer-backed tests should not regress.

## Task 3: Route Generic InputRouter Through `_target`

**Files:**
- Modify: `src/loushang/tui/input.py`
- Test: `tests/tui/test_input_routing.py`

- [ ] **Step 1: Change InputRouter fields and post-init**

Change the dataclass fields:

```python
@dataclass(slots=True)
class InputRouter:
    composer: Composer | None = None
    target: InitVar[PromptInputTarget | None] = None
    surface_host: SurfaceHost | None = None
    running: bool = False
    steering_supported: bool = False
    width: int = 80
    height: int = 24
    keybindings: KeybindingManager | None = None
    _target: PromptInputTarget = field(init=False, repr=False)
    _jump_mode: Literal["forward", "backward"] | None = None
```

Add:

```python
def __post_init__(self, target: PromptInputTarget | None) -> None:
    if self.composer is not None and target is not None:
        raise TypeError("InputRouter accepts composer or target, not both")
    if target is not None:
        self._target = target
        return
    if self.composer is not None:
        self._target = ComposerInputTarget(self.composer)
        return
    raise TypeError("InputRouter requires composer or target")
```

Do not expose `target` as a public property in this task. Tests should verify behavior, not internals.

- [ ] **Step 2: Replace concrete composer calls in generic route path**

Inside `InputRouter.route()`, assign:

```python
target = self._target
```

Replace direct generic routing calls:

- `route_composer_selection_key(self.composer, ...)` -> `route_editor_selection_key(target, ...)`
- completion navigation block -> `target.has_completions and route_prompt_completion_key(target, ...)`
- `self.composer.refresh_completions(...)` -> `target.refresh_completions(...)`
- `self.composer.apply_selected_completion()` -> `target.apply_selected_completion()`
- `self.composer.insert_newline()` -> `target.insert_newline()`
- `route_composer_editing_key(self.composer, ...)` -> `route_editor_editing_key(target, ...)`
- paste/text/jump operations -> `target.*`

Do not add the native slash-command submit behavior to generic `InputRouter`. Existing `test_input_router_enter_submits_text_without_applying_completion` must keep passing.

- [ ] **Step 3: Replace submit and visual movement internals**

Update `submit()`, `_move_up_or_history()`, and `_move_down_or_history()` to use `self._target`.

`submit()` must still:

1. Read `text = self._target.value`.
2. Return `()` if `not text`.
3. Call `self._target.add_history(text)`.
4. Call `self._target.clear()`.
5. Return `submit`, `steer`, or `follow_up` intents exactly as today.

- [ ] **Step 4: Run new target constructor tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest \
  tests/tui/test_input_routing.py::test_input_router_rejects_missing_prompt_target \
  tests/tui/test_input_routing.py::test_input_router_rejects_composer_and_target_together \
  tests/tui/test_input_routing.py::test_input_router_routes_text_paste_and_submit_through_target \
  -q
```

Expected: PASS.

- [ ] **Step 5: Run generic behavior tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_input_routing.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Tasks 1-3**

Commit the red tests and green implementation together:

```bash
git add src/loushang/tui/input.py tests/tui/test_input_routing.py
git commit -m "refactor(tui): route input through prompt targets"
```

## Task 4: Reuse Safe Target Helpers in NativeInputRouter

**Files:**
- Modify: `src/loushang/coding/ui/native_input.py`
- Test: `tests/coding/test_native_coding_tui_input.py`

- [ ] **Step 1: Add native slash-completion submit regression test**

Add this test near the other native completion tests:

```python
def test_native_input_router_enter_applies_slash_completion_before_submit() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 12.0)
    app.composer.set_text("/mo")
    app.composer.set_completion_items((CompletionItem(value="/model", label="/model"),))

    result = NativeInputRouter(
        app,
        should_exit=lambda text: False,
        is_local_command=lambda text: text == "/model",
    ).handle(InputEvent(kind="key", key="enter"))

    assert result.local_text == "/model"
    assert app.composer.value == ""
```

- [ ] **Step 2: Run the native regression test**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest \
  tests/coding/test_native_coding_tui_input.py::test_native_input_router_enter_applies_slash_completion_before_submit \
  -q
```

Expected: PASS before and after the helper refactor. This is a characterization
test for existing native-only behavior, not a red test.

- [ ] **Step 3: Add imports**

Change the input imports:

```python
from loushang.tui.input import (
    ComposerInputTarget,
    InputEvent,
    InputIntent,
    route_editor_editing_key,
    route_editor_selection_key,
    route_prompt_completion_key,
)
```

Remove `route_composer_editing_key` and `route_composer_selection_key` imports if no longer used.

- [ ] **Step 4: Store a ComposerInputTarget**

Add a private field:

```python
_composer_target: ComposerInputTarget = field(init=False, repr=False)
```

In `__post_init__()`:

```python
self._composer_target = ComposerInputTarget(self.app.composer)
```

Keep the existing keybinding manager normalization unchanged.

- [ ] **Step 5: Replace safe helper usage only**

Replace:

```python
route_composer_selection_key(self.app.composer, event.key, keybindings=keybindings)
route_composer_editing_key(self.app.composer, event.key, keybindings=keybindings)
```

with:

```python
route_editor_selection_key(self._composer_target, event.key, keybindings=keybindings)
route_editor_editing_key(self._composer_target, event.key, keybindings=keybindings)
```

In `_route_completion_key()`, replace the hand-written completion navigation body with:

```python
return route_prompt_completion_key(self._composer_target, event.key, keybindings=keybindings)
```

Do not move `_submit_selected_completion()`, `follow_up_keys`, clipboard image handling, transcript commands, active surface routing, or runtime surface routing.

- [ ] **Step 6: Run native input tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_native_coding_tui_input.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/loushang/coding/ui/native_input.py tests/coding/test_native_coding_tui_input.py
git commit -m "refactor(tui): reuse input target helpers in native router"
```

The native regression test is part of this task, so include the native test file
in the commit.

## Task 5: Document the Target Boundary and Run Final Verification

**Files:**
- Modify: `docs/internals/architecture/tui/native-terminal-core/key-designs/KD-002-input-event-routing.md`
- Verify: `src/loushang/tui/input.py`
- Verify: `src/loushang/coding/ui/native_input.py`
- Verify: `tests/tui/test_input_routing.py`
- Verify: `tests/coding/test_native_coding_tui_input.py`

- [ ] **Step 1: Update KD-002**

In the `Design` section, add a short paragraph after the routing-order list:

```markdown
The generic prompt route uses a `PromptInputTarget` boundary. `InputRouter`
owns routing priority and prompt intents, while concrete editors provide
operations through target adapters such as `ComposerInputTarget`. Product
adapters may reuse target helper functions, but they keep their own routing
order when product semantics differ.
```

In `Editor State Model`, replace "focused composer" wording where appropriate with "focused prompt target" while preserving references that are specifically about the Composer UI part.

- [ ] **Step 2: Run focused generic and native tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest \
  tests/tui/test_input_routing.py \
  tests/tui/test_text_input.py \
  tests/coding/test_native_coding_tui_input.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run broader TUI tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS.

- [ ] **Step 4: Run lint on changed files**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check \
  src/loushang/tui/input.py \
  src/loushang/coding/ui/native_input.py \
  tests/tui/test_input_routing.py \
  tests/coding/test_native_coding_tui_input.py
```

Expected: `All checks passed!`

- [ ] **Step 5: Commit Task 5**

```bash
git add docs/internals/architecture/tui/native-terminal-core/key-designs/KD-002-input-event-routing.md
git commit -m "docs(tui): document input target routing boundary"
```

Make this a separate documentation commit.

## Final Acceptance Criteria

- `InputRouter(composer=...)` remains compatible with existing callers.
- `InputRouter(target=...)` works with a fake prompt target and no `Composer`.
- Passing both `composer` and `target` raises `TypeError`.
- Generic enter with active completion submits raw text and does not apply completion.
- Native slash-command selected-completion submit remains native-only.
- `route_composer_editing_key()` and `route_composer_selection_key()` remain compatibility wrappers.
- Native router helper reuse does not reorder runtime surface, active surface, text/paste/resize, transcript, clipboard, follow-up, or slash-command submit behavior.
- Focused verification and ruff commands pass.
