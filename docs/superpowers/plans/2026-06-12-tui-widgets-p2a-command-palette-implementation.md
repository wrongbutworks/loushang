# TUI Widgets P2A Command Palette Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable `CommandPaletteView` widget that filters command items, supports keyboard selection, and returns structured command intents without breaking the existing compat `CommandPalette` data model.

**Architecture:** Keep `CommandPalette` and `CommandPaletteItem` as frozen compat data objects in `loushang.tui.compat`. Add a new focused renderable widget in `src/loushang/tui/ui_parts/widgets/command_palette.py` that composes `TextInput` for query editing, owns local active-result/window state, and returns `InputIntent` values for select/cancel. Export the widget through the existing widget export chain, then document and demonstrate it with a standalone example.

**Tech Stack:** Python dataclasses with slots, existing `loushang.tui` render primitives, `TextInput`, `ThemeResolver`, pytest, `widget_example_playback`.

---

## Spec

Implement against:

- `docs/superpowers/specs/2026-06-12-tui-widgets-p2a-command-palette-design.md`

Hard boundaries:

- Do not replace, rename, or make renderable the existing `CommandPalette`.
- Do not import compat data objects from top-level `loushang.tui` inside the widget module. Import from `loushang.tui.compat`.
- Do not change RenderLoop, SurfaceHost, InputRouter, Composer, or coding command/model workflows.
- `CommandPaletteItem.disabled` is honored only by `CommandPaletteView` in this slice.
- Coding `NativeSurfaceView` tuple-return handling remains out of scope.

## File Map

- Modify `src/loushang/tui/compat.py`
  - Add backward-compatible `disabled: bool = False` to `CommandPaletteItem`.
- Modify `src/loushang/tui/input.py`
  - Add `command_select` and `command_cancel` to `InputIntentKind`.
- Create `src/loushang/tui/ui_parts/widgets/command_palette.py`
  - Own `CommandPaletteView`.
  - Own filtering, active result repair, visible result windowing, input handling, rendering, and theme tokens.
- Modify `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export `CommandPaletteView`.
- Modify `src/loushang/tui/ui_parts/__init__.py`
  - Re-export `CommandPaletteView`.
- Modify `src/loushang/tui/__init__.py`
  - Re-export `CommandPaletteView` while preserving `CommandPalette` and `CommandPaletteItem`.
- Create `tests/tui/test_widgets_command_palette.py`
  - Focused widget, compat, export, render, input, and playback tests.
- Add `examples/tui/51_widgets_command_palette.py`
  - Operations Console example.
- Modify `docs/en/reference/tui-widgets.md`
  - Add P2A Command Palette section, theme tokens, example link.
- Modify `docs/zh-CN/reference/tui-widgets.md`
  - Mirror English docs.

---

### Task 1: Compat Data And Intent Kind Expansion

**Files:**
- Modify: `src/loushang/tui/compat.py`
- Modify: `src/loushang/tui/input.py`
- Create: `tests/tui/test_widgets_command_palette.py`

- [ ] **Step 1: Add failing compat and intent tests**

Create `tests/tui/test_widgets_command_palette.py` with helpers and initial tests:

```python
from __future__ import annotations

from typing import Any, get_args

from loushang.tui import CommandPalette, CommandPaletteItem
from loushang.tui.input import InputIntentKind


def intent_tuple(intent: object) -> tuple[str, str, str]:
    return (
        str(getattr(intent, "kind", "")),
        str(getattr(intent, "text", "")),
        str(getattr(intent, "note", "")),
    )


def intent_tuples(intents: object) -> tuple[tuple[str, str, str], ...]:
    if isinstance(intents, tuple):
        return tuple(intent_tuple(intent) for intent in intents)
    return (intent_tuple(intents),)


def test_command_palette_item_disabled_defaults_to_false() -> None:
    assert CommandPaletteItem("deploy").disabled is False
    assert CommandPaletteItem("archive", disabled=True).disabled is True


def test_command_palette_intent_kinds_are_declared() -> None:
    kinds = get_args(InputIntentKind)

    assert "command_select" in kinds
    assert "command_cancel" in kinds


def test_existing_coding_palette_adapter_keeps_disabled_out_of_scope() -> None:
    from loushang.coding.ui.native_surfaces import _palette_items

    items = _palette_items(
        CommandPalette(
            (
                CommandPaletteItem(
                    value="archive",
                    label="Archive release",
                    description="unavailable",
                    disabled=True,
                ),
            )
        )
    )

    assert len(items) == 1
    assert items[0].selected_value == "archive"
    assert not hasattr(items[0], "disabled")
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py -q
```

Expected: FAIL because `CommandPaletteItem.disabled` and the new intent kinds do not exist.

- [ ] **Step 3: Implement minimal compat and intent changes**

In `src/loushang/tui/compat.py`, update only `CommandPaletteItem`:

```python
@dataclass(frozen=True, slots=True)
class CommandPaletteItem:
    value: str
    label: str = ""
    description: str = ""
    disabled: bool = False

    def display_label(self) -> str:
        return self.label or self.value
```

In `src/loushang/tui/input.py`, add the literals near existing semantic widget intents:

```python
    "question_submit",
    "question_cancel",
    "command_select",
    "command_cancel",
    "consumed",
```

- [ ] **Step 4: Verify focused and existing coding tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py tests/coding/test_ui_command_list.py::test_session_command_palette_reuses_structured_command_items tests/coding/test_ui_model_list.py::test_available_model_palette_reuses_structured_model_items -q
```

Expected: PASS. Existing coding palette equality tests should still pass because omitted `disabled` defaults to `False`.

- [ ] **Step 5: Commit**

```bash
git add src/loushang/tui/compat.py src/loushang/tui/input.py tests/tui/test_widgets_command_palette.py
git commit -m "feat(tui): extend command palette compat intents"
```

---

### Task 2: CommandPaletteView Core Behavior

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/command_palette.py`
- Modify: `tests/tui/test_widgets_command_palette.py`

- [ ] **Step 1: Add failing constructor, filtering, and query tests**

Append tests:

```python
from loushang.tui import InputEvent, RenderConstraints, strip_control_sequences, visible_width
from loushang.tui.compat import CompletionItem, CompletionProvider
from loushang.tui.ui_parts.widgets.command_palette import CommandPaletteView


def _items() -> tuple[CommandPaletteItem, ...]:
    return (
        CommandPaletteItem("deploy", "Deploy service", "Run deployment pipeline"),
        CommandPaletteItem("logs", "Open logs", "Show latest logs"),
        CommandPaletteItem("tests", "Run tests", "Execute test suite"),
        CommandPaletteItem("cache", "Clear cache", "Invalidate local cache"),
        CommandPaletteItem("worker", "Restart worker", "Restart background worker"),
        CommandPaletteItem("archive", "Archive release", "unavailable", disabled=True),
    )


def render_result(part: Any, *, width: int = 60, height: int = 10):
    return part.render(RenderConstraints(width=width, max_height=height))


def render_lines(part: Any, *, width: int = 60, height: int = 10) -> tuple[str, ...]:
    return tuple(line.text for line in render_result(part, width=width, height=height).lines)


def plain_lines(part: Any, *, width: int = 60, height: int = 10) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def test_command_palette_view_title_sources_and_private_snapshot() -> None:
    palette = CommandPalette(_items(), title="Actions")

    assert CommandPaletteView(palette).title == "Actions"
    assert CommandPaletteView(palette, title="").title == ""
    assert CommandPaletteView(_items()).title == "Command Palette"
    assert CommandPaletteView(_items(), title="Run").title == "Run"


def test_command_palette_view_query_is_internal_editor_backed() -> None:
    view = CommandPaletteView(_items(), query="dep")

    assert view.query == "dep"
    assert [item.value for item in view.filtered_items] == ["deploy"]

    view.set_query("log")
    assert view.query == "log"
    assert [item.value for item in view.filtered_items] == ["logs"]

    assert view.handle_input(InputEvent(kind="text", text="s")) is True
    assert view.query == "logs"
    assert [item.value for item in view.filtered_items] == ["logs"]


def test_command_palette_view_filters_value_label_and_description_case_insensitive_in_order() -> None:
    view = CommandPaletteView(_items())

    assert [item.value for item in view.filtered_items] == [
        "deploy",
        "logs",
        "tests",
        "cache",
        "worker",
        "archive",
    ]

    view.set_query("RUN")
    assert [item.value for item in view.filtered_items] == ["deploy", "tests"]

    view.set_query("restart")
    assert [item.value for item in view.filtered_items] == ["worker"]


def test_command_palette_from_completion_provider_preserves_existing_shape() -> None:
    palette = CommandPalette.from_completion_provider(
        CompletionProvider(
            (
                CompletionItem("/deploy", label="/deploy", description="Deploy app"),
            )
        ),
        title="Commands",
    )

    assert palette == CommandPalette(
        (CommandPaletteItem("/deploy", "/deploy", "Deploy app"),),
        title="Commands",
    )
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py -q
```

Expected: FAIL because `src/loushang/tui/ui_parts/widgets/command_palette.py` does not exist.

- [ ] **Step 3: Add minimal CommandPaletteView skeleton and filtering**

Create `src/loushang/tui/ui_parts/widgets/command_palette.py`.

Required structure:

```python
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width, visible_width
from loushang.tui.compat import CommandPalette, CommandPaletteItem
from loushang.tui.core import CursorDeclaration, RenderConstraints, RenderLine, RenderResult
from loushang.tui.input import InputIntent
from loushang.tui.keybindings import normalize_key_id
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.text_input import TextInput
from loushang.tui.ui_parts.widgets._utils import style_text

__all__ = ["CommandPaletteView"]

_QUERY_LABEL_WIDTH = 14
_FOOTER = "[up/down] command  [enter] run  [esc] close"


@dataclass(slots=True, init=False)
class CommandPaletteView:
    _items: tuple[CommandPaletteItem, ...]
    _title: str
    _query_input: TextInput
    placeholder: str
    max_visible: int
    empty_text: str
    close_on_select: bool
    close_on_cancel: bool
    theme: ThemeResolver | None
    focused: bool
    _active_index: int = field(default=0, init=False, repr=False)
    _first_visible_index: int = field(default=0, init=False, repr=False)

    def __init__(...) -> None:
        ...
```

Implementation details:

- Use a custom `__init__`.
- If `palette` is a `CommandPalette`, set `_items = tuple(palette.items)` and `_title = palette.title if title is None else title`.
- If `palette` is a sequence, set `_items = tuple(palette)` and `_title = "Command Palette" if title is None else title`.
- Construct `_query_input = TextInput(placeholder=placeholder, theme=theme, focused=focused)`.
- Call `_query_input.set_text(query)` followed by `_repair_active(previous_value="")`.
- Add read-only properties:

```python
@property
def title(self) -> str:
    return self._title

@property
def query(self) -> str:
    return self._query_input.value

@property
def filtered_items(self) -> tuple[CommandPaletteItem, ...]:
    needle = self.query.casefold().strip()
    if not needle:
        return self._items
    return tuple(item for item in self._items if _matches(item, needle))

@property
def active_value(self) -> str:
    item = self._active_item()
    return "" if item is None else item.value
```

- Add `_matches(item, needle)` over `value`, `display_label()`, and `description`.
- Add `_enabled_indices(filtered)` and `_repair_active(previous_value: str = "")`.
- `_repair_active()` must preserve the previous active item by value when that
  value remains present in `filtered_items` and the item is still enabled.
- If `previous_value` is empty or no longer enabled in the filtered results,
  `_repair_active()` moves to the first enabled filtered item.
- In `_repair_active`, treat the "previous active item remains visible" spec phrase as "still present in filtered results and enabled"; the visible render window is handled separately by `_ensure_active_visible()`.
- `set_query(query)` must capture `previous_value = self.active_value` before
  changing `_query_input`, then call `_repair_active(previous_value=previous_value)`.

- [ ] **Step 4: Verify constructor and filtering tests pass**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py -q
```

Expected: the tests added so far pass.

- [ ] **Step 5: Add failing navigation, disabled, intent, and rendering tests**

Append tests:

```python
def test_command_palette_view_disabled_items_render_but_navigation_skips_them() -> None:
    view = CommandPaletteView(_items())
    view.focus()

    view.set_query("archive")
    assert view.active_value == ""
    assert view.handle_input(InputEvent(kind="key", key="enter")) is None
    assert plain_lines(view, width=60, height=10).count("> Archive release") == 0
    assert any("Archive release" in line for line in plain_lines(view, width=60, height=10))


def test_command_palette_view_navigation_repairs_active_and_visible_window() -> None:
    view = CommandPaletteView(_items(), max_visible=2)
    view.focus()

    assert view.active_value == "deploy"
    assert view.handle_input(InputEvent(kind="key", key="down")) is True
    assert view.handle_input(InputEvent(kind="key", key="down")) is True
    assert view.active_value == "tests"

    lines = plain_lines(view, width=60, height=8)
    assert any(line.startswith("> Run tests") for line in lines)
    assert sum(line.startswith("> ") for line in lines) == 1

    assert view.handle_input(InputEvent(kind="key", key="ctrl+end")) is True
    assert view.active_value == "worker"
    assert view.handle_input(InputEvent(kind="key", key="ctrl+home")) is True
    assert view.active_value == "deploy"


def test_command_palette_view_select_and_cancel_intents_with_close_flags() -> None:
    view = CommandPaletteView(_items())

    assert intent_tuples(view.handle_input(InputEvent(kind="key", key="enter"))) == (
        ("command_select", "deploy", "Deploy service"),
        ("surface_close", "", ""),
    )

    stay_open = CommandPaletteView(_items(), close_on_select=False, close_on_cancel=False)
    assert intent_tuples(stay_open.handle_input(InputEvent(kind="key", key="enter"))) == (
        ("command_select", "deploy", "Deploy service"),
    )
    assert intent_tuples(stay_open.handle_input(InputEvent(kind="key", key="escape"))) == (
        ("command_cancel", "", ""),
    )
    assert intent_tuples(stay_open.handle_input(InputEvent(kind="key", key="esc"))) == (
        ("command_cancel", "", ""),
    )
    assert intent_tuples(view.handle_input(InputEvent(kind="key", key="ctrl+c"))) == (
        ("command_cancel", "", ""),
        ("surface_close", "", ""),
    )


def test_command_palette_view_home_end_edit_query_ctrl_edges_move_results() -> None:
    view = CommandPaletteView(_items(), query="dep")

    assert view.handle_input(InputEvent(kind="key", key="home")) is True
    assert view.handle_input(InputEvent(kind="text", text="x")) is True
    assert view.query == "xdep"
    assert view.active_value == ""

    view.set_query("")
    assert view.handle_input(InputEvent(kind="key", key="ctrl+end")) is True
    assert view.active_value == "worker"


def test_command_palette_view_preserves_active_value_across_query_changes() -> None:
    view = CommandPaletteView(_items())

    assert view.handle_input(InputEvent(kind="key", key="down")) is True
    assert view.active_value == "logs"

    view.set_query("log")
    assert view.active_value == "logs"

    view.set_query("run")
    assert view.active_value == "deploy"


def test_command_palette_view_paste_updates_query_and_repairs_active() -> None:
    view = CommandPaletteView(_items())

    assert view.handle_input(InputEvent(kind="paste", text="cache")) is True
    assert view.query == "cache"
    assert view.active_value == "cache"


def test_command_palette_view_respects_width_height_cursor_and_empty_state() -> None:
    view = CommandPaletteView(_items(), query="missing")
    view.focus()

    result = render_result(view, width=18, height=5)
    lines = tuple(strip_control_sequences(line.text) for line in result.lines)

    assert len(lines) <= 5
    assert all(visible_width(line) <= 18 for line in lines)
    assert any("No commands" in line for line in lines)
    assert result.cursor is not None
```

- [ ] **Step 6: Run tests to verify failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py -q
```

Expected: FAIL on missing input/render behavior.

- [ ] **Step 7: Implement input, active windowing, intents, and rendering**

Implementation requirements:

- `focus()` sets `focused=True` and focuses `_query_input`.
- `blur()` sets `focused=False` and blurs `_query_input`.
- `editor_input_target()` returns `_query_input.editor_input_target()` only when focused; otherwise `None`.
- Handle palette keys before delegating to `TextInput`:

```python
def handle_input(self, event: object) -> object:
    kind = getattr(event, "kind", "")
    if kind in {"text", "paste"}:
        before = self.query
        previous_value = self.active_value
        handled = self._query_input.handle_input(event)
        if handled and self.query != before:
            self._repair_active(previous_value=previous_value)
        return handled or None
    if kind != "key":
        return None
    key = normalize_key_id(getattr(event, "key", ""))
    if key in {"escape", "esc", "ctrl+c"}:
        return self._cancel()
    if key == "enter":
        return self._select_active()
    if key == "up":
        return self._move_active(-1)
    if key == "down":
        return self._move_active(1)
    if key == "ctrl+home":
        return self._jump_active(first=True)
    if key == "ctrl+end":
        return self._jump_active(first=False)
    before = self.query
    previous_value = self.active_value
    handled = self._query_input.handle_editing_key(key)
    if handled and self.query != before:
        self._repair_active(previous_value=previous_value)
    return True if handled else None
```

- `_select_active()` returns `None` when there is no enabled active item, so
  all-disabled/no-match activation consumes nothing.
- `_cancel()` and `_select_active()` return tuple intents according to close flags.
- `_ensure_active_visible(height)` mirrors `Menu._ensure_active_visible()` but uses filtered result length.
- Rendering should build bounded rows:
  - optional title row if `self.title` is non-empty and height remains
  - blank separator when height allows
  - query row with a fixed label width of 14
  - blank separator when height allows
  - `Results` label when height allows
  - result rows, capped by `min(self.max_visible, remaining_height)`
  - empty row when no filtered items
  - footer when height allows
- For query row, render the owned `TextInput` into width `target_width - _QUERY_LABEL_WIDTH` and offset cursor by label width.
- Use tokens:
  - `widget.commandPalette.title`
  - `widget.commandPalette.queryLabel`
  - `widget.commandPalette.queryText`
  - `widget.commandPalette.placeholder`
  - `widget.commandPalette.section`
  - `widget.commandPalette.item`
  - `widget.commandPalette.focus`
  - `widget.commandPalette.disabled`
  - `widget.commandPalette.description`
  - `widget.commandPalette.empty`
  - `widget.commandPalette.footer`
- Keep visible width stable after applying theme by using `truncate_to_width(..., ellipsis="")` on the final rendered row.

- [ ] **Step 8: Verify focused widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/command_palette.py tests/tui/test_widgets_command_palette.py
git commit -m "feat(tui): add command palette view"
```

---

### Task 3: Public Exports And Documentation

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`
- Modify: `tests/tui/test_widgets_command_palette.py`

- [ ] **Step 1: Add failing public re-export and theme tests**

Append tests:

```python
def test_command_palette_view_is_reexported_from_public_modules() -> None:
    from loushang.tui import CommandPaletteView
    from loushang.tui.ui_parts import CommandPaletteView as UiCommandPaletteView
    from loushang.tui.ui_parts.widgets import CommandPaletteView as WidgetCommandPaletteView

    assert CommandPaletteView is UiCommandPaletteView
    assert CommandPaletteView is WidgetCommandPaletteView


def test_command_palette_view_theme_tokens_apply_without_width_changes() -> None:
    from loushang.tui import ThemeResolver

    theme = ThemeResolver(
        defaults={
            "widget.commandPalette.title": {"bold": True},
            "widget.commandPalette.queryLabel": {"color": "cyan"},
            "widget.commandPalette.queryText": {"color": "white"},
            "widget.commandPalette.placeholder": {"color": "bright_black"},
            "widget.commandPalette.section": {"bold": True},
            "widget.commandPalette.item": {"color": "white"},
            "widget.commandPalette.focus": {"bold": True, "color": "cyan"},
            "widget.commandPalette.disabled": {"dim": True},
            "widget.commandPalette.description": {"color": "bright_black"},
            "widget.commandPalette.empty": {"color": "bright_black"},
            "widget.commandPalette.footer": {"color": "bright_black"},
        }
    )
    view = CommandPaletteView(_items(), theme=theme)
    view.focus()

    raw = render_lines(view, width=60, height=10)
    plain = tuple(strip_control_sequences(line) for line in raw)

    assert raw[0].startswith("\x1b[1m")
    assert "\x1b[1;36m> Deploy service" in "\n".join(raw)
    assert all(visible_width(line) <= 60 for line in raw)
    assert all(visible_width(line) <= 60 for line in plain)
```

- [ ] **Step 2: Run tests to verify export failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py::test_command_palette_view_is_reexported_from_public_modules tests/tui/test_widgets_command_palette.py::test_command_palette_view_theme_tokens_apply_without_width_changes -q
```

Expected: FAIL because `CommandPaletteView` is not exported yet.

- [ ] **Step 3: Add export chain**

In `src/loushang/tui/ui_parts/widgets/__init__.py`:

```python
from .command_palette import CommandPaletteView as CommandPaletteView
```

Add `"CommandPaletteView"` to `__all__`.

In `src/loushang/tui/ui_parts/__init__.py`:

```python
from .widgets import CommandPaletteView as CommandPaletteView
```

Add `"CommandPaletteView"` to `__all__`.

In `src/loushang/tui/__init__.py`, add `CommandPaletteView` to the existing `from loushang.tui.ui_parts import (...)` block and `__all__`.

- [ ] **Step 4: Update English docs**

In `docs/en/reference/tui-widgets.md`:

- Add a `## P2A Command Palette` section after P1E.
- Include a widget table row for `CommandPaletteView`.
- Include this usage snippet:

```python
from loushang.tui import CommandPalette, CommandPaletteItem, CommandPaletteView

palette = CommandPalette(
    (
        CommandPaletteItem("deploy", "Deploy service", "Run deployment pipeline"),
        CommandPaletteItem("archive", "Archive release", "unavailable", disabled=True),
    ),
    title="Commands",
)
view = CommandPaletteView(palette)
view.focus()
```

- Document that `CommandPalette` is the data model and `CommandPaletteView` is the focusable widget.
- Document that selection returns `command_select`, cancel returns `command_cancel`, and close flags optionally add `surface_close`.
- Document disabled item semantics and the legacy coding adapter out-of-scope boundary.
- Add all `widget.commandPalette.*` tokens to the theme token table.
- Add `examples/tui/51_widgets_command_palette.py` to the Example list.
- Update the theme intro from `P0A...P1E` to include `P2A`.

- [ ] **Step 5: Update Chinese docs**

Mirror the English changes in `docs/zh-CN/reference/tui-widgets.md`. Keep class names and intent kinds literal. Update the theme intro to include `P2A`.

- [ ] **Step 6: Verify docs and focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py -q
```

Expected: PASS.

Run:

```bash
uv --cache-dir .uv-cache run ruff check src/loushang/tui/compat.py src/loushang/tui/input.py src/loushang/tui/ui_parts/widgets/command_palette.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_command_palette.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md tests/tui/test_widgets_command_palette.py
git commit -m "docs(tui): document command palette view"
```

---

### Task 4: Operations Console Example And Playback

**Files:**
- Create: `examples/tui/51_widgets_command_palette.py`
- Modify: `tests/tui/test_widgets_command_palette.py`

- [ ] **Step 1: Add failing example import and playback tests**

Append tests:

```python
import runpy

from tests.tui.widget_example_playback import play_example


def test_widgets_command_palette_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/51_widgets_command_palette.py", run_name="__test__")

    build_app = namespace["build_app"]
    app = build_app()
    result = app.render(RenderConstraints(width=80, max_height=20))

    assert callable(build_app)
    assert result.lines


def test_widgets_command_palette_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/51_widgets_command_palette.py",
        events=(
            ("down", InputEvent(kind="key", key="down")),
            ("type log", InputEvent(kind="text", text="log")),
            ("enter", InputEvent(kind="key", key="enter")),
            ("escape", InputEvent(kind="key", key="escape")),
        ),
        width=80,
        height=20,
    )

    assert frames[0].lines[:10] == (
        "Operations Console",
        "",
        "Status        Ready",
        "",
        "Commands",
        "",
        "Search",
        "",
        "Results",
        "> Deploy service  Run deployment pipeline",
    )
    assert any(line == "> Open logs  Show latest logs" for line in frames[1].lines)
    assert any(line == "> Open logs  Show latest logs" for line in frames[2].lines)
    assert any("Selected: Open logs" in line for line in frames[3].lines)
    assert any("Cancelled" in line for line in frames[4].lines)
```

Adjust exact expected lines after the example render shape is implemented. Keep stripped-text snapshots stable and assert only high-signal rows if the bounded layout changes by one separator line.

- [ ] **Step 2: Run tests to verify example failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py::test_widgets_command_palette_example_imports tests/tui/test_widgets_command_palette.py::test_widgets_command_palette_example_playback_snapshots -q
```

Expected: FAIL because the example file does not exist.

- [ ] **Step 3: Create the example**

Create `examples/tui/51_widgets_command_palette.py` with the same app pattern as `45_widgets_light_controls.py` and `50_widgets_toast.py`.

Required shape:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    CommandPaletteItem,
    CommandPaletteView,
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    ThemeResolver,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)
```

Use:

- `LABEL_WIDTH = 14`
- `COMMAND_PALETTE_THEME = ThemeResolver(defaults={...})`
- `_field(label, value, width=...)`
- `OperationsConsoleApp(FocusableMixin)`
  - `palette: CommandPaletteView`
  - `status: str = "Ready"`
  - `last_command: str = "none"`
  - `__post_init__()` calls `FocusableMixin.__init__(self)` and `self.focus()`.
  - `focus()` focuses the palette.
  - `blur()` blurs the palette.
  - `editor_input_target()` delegates to `self.palette.editor_input_target()`.
  - `render()` shows:
    - `Operations Console`
    - status rows
    - `Commands`
    - palette render output
    - controls footer
  - `handle_input()` sends input to `self.palette`, then updates status from `command_select` or `command_cancel`.

Handle tuple intents:

```python
def _as_intents(result: object) -> tuple[object, ...]:
    if isinstance(result, tuple):
        return result
    return (result,) if result is not None and result is not True else ()
```

Use `close_on_select=False` and `close_on_cancel=False` in the embedded example so selecting/cancelling updates the status row instead of relying on overlays.

Initial commands:

```python
def _command_items() -> tuple[CommandPaletteItem, ...]:
    return (
        CommandPaletteItem("deploy", "Deploy service", "Run deployment pipeline"),
        CommandPaletteItem("logs", "Open logs", "Show latest logs"),
        CommandPaletteItem("tests", "Run tests", "Execute test suite"),
        CommandPaletteItem("cache", "Clear cache", "Invalidate local cache"),
        CommandPaletteItem("worker", "Restart worker", "Restart background worker"),
        CommandPaletteItem("archive", "Archive release", "unavailable", disabled=True),
    )
```

`main()` should follow existing examples:

```python
async def main() -> int:
    tui = build_app()

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if event.kind == "text" and "q" in event.text.lower():
            return context.stop(0)
        context.tui.handle_input(event)
        return TuiInputResult()

    return await TuiRunner(tui).run(on_input=on_input)
```

- [ ] **Step 4: Run playback and refine expected snapshots**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py::test_widgets_command_palette_example_imports tests/tui/test_widgets_command_palette.py::test_widgets_command_palette_example_playback_snapshots -q
```

Expected: PASS after snapshot expectations match the final stripped render.

- [ ] **Step 5: Manual smoke command**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev python examples/tui/51_widgets_command_palette.py
```

Expected: Opens a TUI. Manual keys:

- type `log` filters to Open logs
- `enter` updates status to selected Open logs
- `escape` updates status to cancelled
- `q` exits

If the environment cannot run an interactive TUI, report that and rely on playback tests.

- [ ] **Step 6: Commit**

```bash
git add examples/tui/51_widgets_command_palette.py tests/tui/test_widgets_command_palette.py
git commit -m "test(tui): add command palette example playback"
```

---

### Task 5: Final Verification And Readiness

**Files:**
- No new implementation files unless verification exposes a defect.

- [ ] **Step 1: Run focused CommandPalette tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_command_palette.py -q
```

Expected: PASS.

- [ ] **Step 2: Run related TUI widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_question_dialog.py tests/tui/test_widgets_toast.py tests/tui/test_widgets_command_palette.py -q
```

Expected: PASS.

- [ ] **Step 3: Run compat coding tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_ui_command_list.py tests/coding/test_ui_model_list.py -q
```

Expected: PASS.

- [ ] **Step 4: Run TUI module lint**

Run:

```bash
uv --cache-dir .uv-cache run ruff check src/loushang/tui tests/tui/test_widgets_command_palette.py examples/tui/51_widgets_command_palette.py
```

Expected: PASS.

- [ ] **Step 5: Run broader TUI suite if time permits**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS. If this is slow but passes focused suites, report focused verification and note that full TUI was not run.

- [ ] **Step 6: Inspect git diff**

Run:

```bash
git status --short
git diff --stat
git diff --check
```

Expected:

- Dirty files match this plan only.
- `git diff --check` has no whitespace errors.

- [ ] **Step 7: Commit final fixes if any**

Only commit if verification required follow-up changes:

```bash
git add <changed-files>
git commit -m "fix(tui): polish command palette view"
```

---

## Review Checklist

Before opening a PR or merging:

- `CommandPalette` remains a data-only compat object.
- `CommandPaletteItem.disabled` defaults to `False`.
- `CommandPaletteView` imports compat models from `loushang.tui.compat`.
- `query` is read-only and backed by the internal `TextInput`.
- `home/end` edit the query, while `ctrl+home/ctrl+end` move result focus.
- Disabled rows render, are skipped, and cannot activate.
- Repeated `down` navigation keeps the active result visible.
- Selection/cancel intents are structured and close flags behave correctly.
- Docs mention data model vs widget distinction.
- Example playback proves filtering, selection, and cancellation.
