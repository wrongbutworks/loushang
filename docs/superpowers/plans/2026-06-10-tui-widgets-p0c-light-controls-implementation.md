# TUI Widgets P0C Light Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add P0C TUI light controls for vertical menus, horizontal tabs, and static spinners.

**Architecture:** Keep each control in a focused widget module under `src/loushang/tui/ui_parts/widgets/`: `menu.py`, `tabs.py`, and `spinner.py`. Reuse existing `RenderResult`, width helpers, `ThemeResolver`, and `_utils` callback/activation helpers; do not add global focus, overlay lifecycle, animation scheduling, or new input intents.

**Tech Stack:** Python 3.11 dataclasses, existing TUI render/input/theme primitives, `pytest`, `uv`, Ruff.

---

## File Structure

- Create `src/loushang/tui/ui_parts/widgets/menu.py`
  - Owns `MenuItem` and `Menu`.
  - Implements vertical local focus, disabled skipping, activation, height-window visibility, and theme tokens.
- Create `src/loushang/tui/ui_parts/widgets/tabs.py`
  - Owns `TabItem` and `Tabs`.
  - Implements canonical selected value, immediate selection on navigation, disabled skipping, callbacks, and theme tokens.
- Create `src/loushang/tui/ui_parts/widgets/spinner.py`
  - Owns `Spinner`.
  - Implements caller-driven one-line activity rendering only; no input handling or scheduling.
- Modify `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export `Menu`, `MenuItem`, `Tabs`, `TabItem`, and `Spinner`.
- Modify `src/loushang/tui/ui_parts/__init__.py`
  - Re-export stable P0C widgets.
- Modify `src/loushang/tui/__init__.py`
  - Re-export stable P0C widgets at top level.
- Create `tests/tui/test_widgets_light_controls.py`
  - Focused tests for public exports, rendering, theme tokens, width/height constraints, menu input, tabs input, and spinner rendering.
- Create `examples/tui/45_widgets_light_controls.py`
  - Importable demo app combining `Tabs`, `Menu`, and `Spinner`.
- Modify `docs/en/reference/tui-widgets.md`
  - Add P0C widgets and theme tokens; remove implemented P0C controls from Planned Catalog.
- Modify `docs/zh-CN/reference/tui-widgets.md`
  - Mirror English docs.

Do not modify `SurfaceHost`, `SelectionSurface`, `InputIntent`, `RenderScheduler`, `Table`, `TreeView`, `TextArea`, `Popover`, `Toast`, or `PromptDialog` in this slice.

## Task 1: Add Menu Red Tests

**Files:**
- Create: `tests/tui/test_widgets_light_controls.py`
- Test: `tests/tui/test_widgets_light_controls.py`

- [ ] **Step 1: Write failing Menu tests**

Create `tests/tui/test_widgets_light_controls.py`:

```python
from __future__ import annotations

from typing import Any

from loushang.tui import (
    InputEvent,
    Menu,
    MenuItem,
    RenderConstraints,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import Menu as UiMenu
from loushang.tui.ui_parts import MenuItem as UiMenuItem
from loushang.tui.ui_parts.widgets import Menu as WidgetMenu
from loushang.tui.ui_parts.widgets import MenuItem as WidgetMenuItem


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def test_light_controls_are_reexported_from_public_modules() -> None:
    assert Menu is UiMenu
    assert Menu is WidgetMenu
    assert MenuItem is UiMenuItem
    assert MenuItem is WidgetMenuItem
    assert MenuItem("open", "Open").value == "open"


def test_menu_renders_focus_disabled_description_theme_and_width() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.menu.item": {"color": "white"},
            "widget.menu.focus": {"bold": True, "color": "cyan"},
            "widget.menu.disabled": {"dim": True},
            "widget.menu.description": {"color": "bright_black"},
        }
    )
    menu = Menu(
        [
            MenuItem("open", "Open", description="current"),
            MenuItem("delete", "Delete", disabled=True),
            MenuItem("quit", "Quit", icon="x"),
        ],
        theme=theme,
    )
    menu.focus()

    raw = render_lines(menu, width=40, height=4)

    assert raw[0].startswith("\x1b[1;36m> Open")
    assert "\x1b[90mcurrent" in raw[0]
    assert "\x1b[2m  Delete" in raw[1]
    assert plain_lines(menu, width=40, height=4) == (
        "> Open  current",
        "  Delete",
        "  x Quit",
    )
    assert_widths_within(render_lines(menu, width=6, height=4), 6)


def test_menu_navigation_activation_callbacks_and_space_forms() -> None:
    calls: list[str] = []
    menu = Menu(
        [
            MenuItem("open", "Open", on_select=lambda: calls.append("open")),
            MenuItem("delete", "Delete", disabled=True),
            MenuItem("quit", "Quit", on_select=lambda: "quit"),
        ]
    )
    menu.focus()

    assert menu.active_value == "open"
    assert menu.handle_input(InputEvent(kind="key", key="enter")) is True
    assert menu.handle_input(InputEvent(kind="key", key="down")) is True
    assert menu.active_value == "quit"
    assert menu.handle_input(InputEvent(kind="key", key="enter")) == "quit"
    assert menu.handle_input(InputEvent(kind="key", key="down")) is True
    assert menu.active_value == "open"
    assert menu.handle_input(InputEvent(kind="text", text=" ")) is True
    assert menu.handle_input(InputEvent(kind="key", key="space")) is True
    assert calls == ["open", "open", "open"]


def test_menu_initial_index_boundaries_empty_disabled_and_height_window() -> None:
    assert Menu(
        [
            MenuItem("one", "One"),
            MenuItem("two", "Two", disabled=True),
        ],
        active_index=99,
    ).active_value == "one"
    assert Menu([MenuItem("fallback", "Fallback")]).handle_input(InputEvent(kind="key", key="enter")) == "fallback"

    menu = Menu(
        [
            MenuItem("one", "One", disabled=True),
            MenuItem("two", "Two", disabled=True),
            MenuItem("three", "Three"),
        ],
        active_index=0,
        wrap=False,
    )
    menu.focus()

    assert menu.active_value == "three"
    assert menu.handle_input(InputEvent(kind="key", key="down")) is False
    assert menu.handle_input(InputEvent(kind="key", key="end")) is False
    assert menu.handle_input(InputEvent(kind="key", key="home")) is False
    assert menu.handle_input(InputEvent(kind="key", key="up")) is False

    assert Menu([]).handle_input(InputEvent(kind="key", key="down")) is None
    assert Menu([]).handle_input(InputEvent(kind="key", key="enter")) is None
    disabled = Menu([MenuItem("no", "No", disabled=True)])
    disabled.focus()
    assert disabled.handle_input(InputEvent(kind="key", key="down")) is None
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None

    windowed = Menu([MenuItem(str(index), f"Item {index}") for index in range(5)], active_index=4)
    windowed.focus()
    assert plain_lines(windowed, width=20, height=2) == ("  Item 3", "> Item 4")


def test_menu_description_threshold_omits_then_truncates_description() -> None:
    menu = Menu([MenuItem("build", "Build", description="compile artifacts")])

    assert plain_lines(menu, width=8, height=1) == ("  Build",)
    assert plain_lines(menu, width=13, height=1) == ("  Build  com",)
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py -q
```

Expected: FAIL during import with missing `Menu` / `MenuItem`.

- [ ] **Step 3: Do not commit red tests alone**

Continue to Task 2 and commit once Menu is green.

## Task 2: Implement Menu And Public Exports

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/menu.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_light_controls.py`

- [ ] **Step 1: Implement `menu.py`**

Create `src/loushang/tui/ui_parts/widgets/menu.py`.

Implementation requirements:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width, visible_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import callback_result, is_activation_event, style_text


@dataclass(frozen=True, slots=True)
class MenuItem:
    value: str
    label: str
    description: str = ""
    disabled: bool = False
    icon: str = ""
    on_select: Callable[[], object] | None = None

    @property
    def display_label(self) -> str:
        return self.label if not self.icon else f"{self.icon} {self.label}".strip()


@dataclass(slots=True)
class Menu:
    items: Sequence[MenuItem]
    active_index: int = 0
    wrap: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False
    _active_index: int = field(default=0, init=False, repr=False)
    _first_visible_index: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.items = tuple(self.items)
        self._active_index = self._nearest_enabled_index(self.active_index)

    @property
    def active_value(self) -> str:
        item = self._active_item()
        return "" if item is None else item.value

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key":
            key = getattr(event, "key", "")
            if key == "up":
                return self._move_active(-1)
            if key == "down":
                return self._move_active(1)
            if key == "home":
                return self._jump_active(first=True)
            if key == "end":
                return self._jump_active(first=False)
        if is_activation_event(event):
            return self._activate()
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        height = max(0, constraints.max_height)
        self._ensure_active_visible(height)
        visible_items = tuple(enumerate(self.items))[self._first_visible_index : self._first_visible_index + height]
        lines = [RenderLine(_menu_line(self, index, item, target_width)) for index, item in visible_items]
        return RenderResult.from_lines(lines, constraints=constraints)
```

Add private helpers in the same module:

```python
    def _enabled_indices(self) -> tuple[int, ...]: ...
    def _nearest_enabled_index(self, preferred: int) -> int: ...
    def _active_item(self) -> MenuItem | None: ...
    def _move_active(self, delta: int) -> bool | None: ...
    def _jump_active(self, *, first: bool) -> bool | None: ...
    def _activate(self) -> object: ...
    def _ensure_active_visible(self, height: int) -> None: ...
```

Helper behavior:

- `_nearest_enabled_index()` mirrors `Toolbar._nearest_enabled_index()`.
- `_move_active()` mirrors `Toolbar._move_active()` but uses `up`/`down`.
- `_jump_active()` mirrors `Toolbar._jump_active()`.
- `_activate()` returns `None` for no enabled active item, `callback_result(item.on_select())` when a callback exists, else `item.value`.
- `_ensure_active_visible(height)` does nothing when `height <= 0`; otherwise adjusts `_first_visible_index` so `_active_index` is inside `[first, first + height)`.
- `_menu_line()`:
  - Prefix is `"> "` only when focused and active and enabled; otherwise `"  "`.
  - Label text is `f"{prefix}{item.display_label}"`.
  - If description can fit after the rendered label with `"  "` and at least one visible description column, append a separately styled description segment.
  - Disabled items use `widget.menu.disabled`.
  - Active focused items use `widget.menu.focus`.
  - Enabled inactive items use `widget.menu.item`.
  - Description segment uses `widget.menu.description`.
  - Final visible width must not exceed target width.

- [ ] **Step 2: Export Menu from public modules**

Add `Menu` and `MenuItem` imports and `__all__` entries in:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
- `src/loushang/tui/ui_parts/__init__.py`
- `src/loushang/tui/__init__.py`

- [ ] **Step 3: Run focused Menu tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py -q
```

Expected: PASS for Menu tests.

- [ ] **Step 4: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 5: Run focused Ruff**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check tests/tui/test_widgets_light_controls.py src/loushang/tui/ui_parts/widgets/menu.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/tui/test_widgets_light_controls.py src/loushang/tui/ui_parts/widgets/menu.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
git commit -m "test(tui): add menu widget"
```

## Task 3: Add Tabs Red Tests

**Files:**
- Modify: `tests/tui/test_widgets_light_controls.py`
- Test: `tests/tui/test_widgets_light_controls.py`

- [ ] **Step 1: Append Tabs imports and tests**

Add to the `from loushang.tui import (...)` import list:

```python
    TabItem,
    Tabs,
```

Add public-layer aliases:

```python
from loushang.tui.ui_parts import TabItem as UiTabItem
from loushang.tui.ui_parts import Tabs as UiTabs
from loushang.tui.ui_parts.widgets import TabItem as WidgetTabItem
from loushang.tui.ui_parts.widgets import Tabs as WidgetTabs
```

Extend `test_light_controls_are_reexported_from_public_modules()`:

```python
    assert Tabs is UiTabs
    assert Tabs is WidgetTabs
    assert TabItem is UiTabItem
    assert TabItem is WidgetTabItem
```

Append:

```python
def test_tabs_normalize_value_render_theme_and_width() -> None:
    changes: list[str] = []
    theme = ThemeResolver(
        defaults={
            "widget.tabs.tab": {"color": "white"},
            "widget.tabs.selected": {"color": "green"},
            "widget.tabs.focus": {"bold": True, "color": "cyan"},
            "widget.tabs.disabled": {"dim": True},
        }
    )
    tabs = Tabs(
        [
            TabItem("overview", "Overview"),
            TabItem("logs", "Logs", badge="3"),
            TabItem("settings", "Settings", disabled=True),
        ],
        value="missing",
        on_change=lambda value: changes.append(value),
        theme=theme,
    )

    assert tabs.value == "overview"
    assert tabs.selected_value == "overview"
    assert changes == []
    assert plain_lines(tabs, width=60, height=1) == ("* [Overview]    [Logs 3]    [Settings]",)

    tabs.focus()
    raw = render_lines(tabs, width=60, height=1)[0]
    assert raw.startswith("\x1b[1;36m> [Overview]")
    assert "\x1b[2m  [Settings]" in raw
    assert_widths_within(render_lines(tabs, width=10, height=1), 10)


def test_tabs_navigation_changes_value_callbacks_and_activation_forms() -> None:
    calls: list[str] = []

    def record_change(value: str) -> str:
        calls.append(value)
        return f"changed:{value}"

    tabs = Tabs(
        [
            TabItem("overview", "Overview"),
            TabItem("disabled", "Disabled", disabled=True),
            TabItem("logs", "Logs"),
        ],
        on_change=record_change,
    )
    tabs.focus()

    assert tabs.handle_input(InputEvent(kind="key", key="right")) == "changed:logs"
    assert tabs.value == "logs"
    assert calls == ["logs"]
    assert tabs.handle_input(InputEvent(kind="key", key="enter")) == "logs"
    assert tabs.handle_input(InputEvent(kind="text", text=" ")) == "logs"
    assert tabs.handle_input(InputEvent(kind="key", key="space")) == "logs"
    assert tabs.handle_input(InputEvent(kind="key", key="right")) == "changed:overview"
    assert tabs.value == "overview"
    assert calls == ["logs", "overview"]


def test_tabs_boundaries_disabled_last_value_and_empty_all_disabled_semantics() -> None:
    assert Tabs(
        [
            TabItem("one", "One"),
            TabItem("two", "Two", disabled=True),
            TabItem("three", "Three"),
        ],
        value="two",
    ).value == "three"

    jumps = Tabs(
        [
            TabItem("one", "One"),
            TabItem("two", "Two"),
            TabItem("three", "Three"),
        ],
        value="one",
        wrap=False,
    )
    assert jumps.handle_input(InputEvent(kind="key", key="end")) is True
    assert jumps.value == "three"
    assert jumps.handle_input(InputEvent(kind="key", key="home")) is True
    assert jumps.value == "one"

    tabs = Tabs(
        [
            TabItem("one", "One"),
            TabItem("two", "Two", disabled=True),
        ],
        value="two",
        wrap=False,
    )
    tabs.focus()

    assert tabs.value == "one"
    assert tabs.handle_input(InputEvent(kind="key", key="left")) is False
    assert tabs.handle_input(InputEvent(kind="key", key="home")) is False
    assert tabs.handle_input(InputEvent(kind="key", key="end")) is False
    assert tabs.handle_input(InputEvent(kind="key", key="right")) is False

    assert Tabs([]).value == ""
    assert Tabs([]).handle_input(InputEvent(kind="key", key="right")) is None
    disabled = Tabs([TabItem("no", "No", disabled=True)])
    disabled.focus()
    assert disabled.value == ""
    assert disabled.handle_input(InputEvent(kind="key", key="right")) is None
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py -q
```

Expected: FAIL during import with missing `Tabs` / `TabItem`.

- [ ] **Step 3: Do not commit red tests alone**

Continue to Task 4 and commit once Tabs is green.

## Task 4: Implement Tabs And Public Exports

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/tabs.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_light_controls.py`

- [ ] **Step 1: Implement `tabs.py`**

Create `src/loushang/tui/ui_parts/widgets/tabs.py`.

Implementation requirements:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import callback_result, is_activation_event, style_text


@dataclass(frozen=True, slots=True)
class TabItem:
    value: str
    label: str
    disabled: bool = False
    badge: str = ""

    @property
    def display_label(self) -> str:
        return self.label if not self.badge else f"{self.label} {self.badge}".strip()


@dataclass(slots=True)
class Tabs:
    tabs: Sequence[TabItem]
    value: str = ""
    wrap: bool = True
    on_change: Callable[[str], object] | None = None
    theme: ThemeResolver | None = None
    focused: bool = False

    def __post_init__(self) -> None:
        self.tabs = tuple(self.tabs)
        self.value = self._normalize_value(self.value)

    @property
    def selected_value(self) -> str:
        return self.value

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key":
            key = getattr(event, "key", "")
            if key == "left":
                return self._move_selection(-1)
            if key == "right":
                return self._move_selection(1)
            if key == "home":
                return self._jump_selection(first=True)
            if key == "end":
                return self._jump_selection(first=False)
        if is_activation_event(event):
            return self.value or None
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if not self.tabs:
            return RenderResult.from_lines([], constraints=constraints)
        target_width = autowrap_safe_width(constraints.width)
        parts = [_tab_segment(self, tab) for tab in self.tabs]
        line = truncate_to_width("  ".join(parts), max_width=target_width, ellipsis="")
        return RenderResult.from_lines([RenderLine(line)][: constraints.max_height], constraints=constraints)
```

Add private helpers:

```python
    def _enabled_indices(self) -> tuple[int, ...]: ...
    def _index_for_value(self, value: str) -> int | None: ...
    def _normalize_value(self, requested: str) -> str: ...
    def _selected_index(self) -> int | None: ...
    def _move_selection(self, delta: int) -> bool | None: ...
    def _jump_selection(self, *, first: bool) -> bool | None: ...
    def _set_value(self, value: str) -> object: ...
```

Helper behavior:

- `_normalize_value()` keeps an enabled requested value; for a disabled requested value, chooses the next enabled tab after it or first enabled; for missing requested value, chooses first enabled; for no enabled tabs returns `""`.
- `_move_selection()` returns `None` for no enabled tabs, `False` for no movement, otherwise updates `value` and returns callback result or `True`.
- `_jump_selection()` returns `None` for no enabled tabs, `False` when already at target, otherwise updates `value` and returns callback result or `True`.
- `_set_value()` updates `self.value`; if `on_change` exists returns `callback_result(on_change(value))`, otherwise `True`.
- `_tab_segment()`:
  - Prefix `"> "` for focused selected tab.
  - Prefix `"* "` for selected but not focused tab.
  - Prefix `"  "` for unselected tabs.
  - Text is `f"{prefix}[{tab.display_label}]"`.
  - Disabled uses `widget.tabs.disabled`.
  - Focused selected uses `widget.tabs.focus`.
  - Selected but not focused uses `widget.tabs.selected`.
  - Enabled unselected uses `widget.tabs.tab`.

- [ ] **Step 2: Export Tabs from public modules**

Add `Tabs` and `TabItem` imports and `__all__` entries in:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
- `src/loushang/tui/ui_parts/__init__.py`
- `src/loushang/tui/__init__.py`

- [ ] **Step 3: Run focused Tabs tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py -q
```

Expected: PASS for Menu and Tabs tests.

- [ ] **Step 4: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 5: Run focused Ruff**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check tests/tui/test_widgets_light_controls.py src/loushang/tui/ui_parts/widgets/tabs.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/tui/test_widgets_light_controls.py src/loushang/tui/ui_parts/widgets/tabs.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
git commit -m "test(tui): add tabs widget"
```

## Task 5: Add Spinner Red Tests

**Files:**
- Modify: `tests/tui/test_widgets_light_controls.py`
- Test: `tests/tui/test_widgets_light_controls.py`

- [ ] **Step 1: Append Spinner imports and tests**

Add `Spinner` to the `from loushang.tui import (...)` import list.

Add public-layer aliases:

```python
from loushang.tui.ui_parts import Spinner as UiSpinner
from loushang.tui.ui_parts.widgets import Spinner as WidgetSpinner
```

Extend `test_light_controls_are_reexported_from_public_modules()`:

```python
    assert Spinner is UiSpinner
    assert Spinner is WidgetSpinner
    assert Spinner(label="Loading").label == "Loading"
```

Append:

```python
def test_spinner_renders_frame_modulo_label_empty_frames_and_width() -> None:
    assert plain_lines(Spinner(label="Loading", frame=5), width=20, height=1) == ("/ Loading",)
    assert plain_lines(Spinner(label="", frame=2), width=20, height=1) == ("-",)
    assert plain_lines(Spinner(label="Waiting", frames=()), width=20, height=1) == ("Waiting",)
    assert plain_lines(Spinner(label="", frames=()), width=20, height=1) == ("",)
    assert_widths_within(render_lines(Spinner(label="Very long loading label"), width=8, height=1), 8)
    assert not hasattr(Spinner(label="Loading"), "handle_input")
    assert not hasattr(Spinner(label="Loading"), "focus")


def test_spinner_applies_theme_tokens_without_width_growth() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.spinner.frame": {"color": "cyan"},
            "widget.spinner.label": {"bold": True},
        }
    )
    raw = render_lines(Spinner(label="Loading", frame=0, theme=theme), width=20, height=1)[0]

    assert raw.startswith("\x1b[36m|\x1b[39m")
    assert "\x1b[1mLoading" in raw
    assert strip_control_sequences(raw) == "| Loading"
    assert visible_width(raw) == len("| Loading")
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py -q
```

Expected: FAIL during import with missing `Spinner`.

- [ ] **Step 3: Do not commit red tests alone**

Continue to Task 6 and commit once Spinner is green.

## Task 6: Implement Spinner And Public Exports

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/spinner.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_light_controls.py`

- [ ] **Step 1: Implement `spinner.py`**

Create `src/loushang/tui/ui_parts/widgets/spinner.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import style_text


@dataclass(slots=True)
class Spinner:
    label: str = ""
    frame: int = 0
    frames: Sequence[str] = ("|", "/", "-", "\\")
    theme: ThemeResolver | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        line = _spinner_line(self, target_width)
        return RenderResult.from_lines([RenderLine(line)][: constraints.max_height], constraints=constraints)
```

Add `_spinner_line(spinner, target_width)`:

- If `frames` is non-empty, choose `frames[frame % len(frames)]`; otherwise no frame text.
- If both frame and label exist, render `"frame label"`.
- If only frame exists, render frame.
- If only label exists, render label.
- If both are empty, return `""`.
- Style frame with `widget.spinner.frame`.
- Style label with `widget.spinner.label`.
- Truncate final line to target width.

- [ ] **Step 2: Export Spinner from public modules**

Add `Spinner` imports and `__all__` entries in:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
- `src/loushang/tui/ui_parts/__init__.py`
- `src/loushang/tui/__init__.py`

- [ ] **Step 3: Run focused Spinner tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py -q
```

Expected: PASS for Menu, Tabs, and Spinner tests.

- [ ] **Step 4: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 5: Run focused Ruff**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check tests/tui/test_widgets_light_controls.py src/loushang/tui/ui_parts/widgets/spinner.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/tui/test_widgets_light_controls.py src/loushang/tui/ui_parts/widgets/spinner.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
git commit -m "test(tui): add spinner widget"
```

## Task 7: Add Example And Reference Docs

**Files:**
- Modify: `tests/tui/test_widgets_light_controls.py`
- Create: `examples/tui/45_widgets_light_controls.py`
- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`
- Test: `tests/tui/test_widgets_light_controls.py`

- [ ] **Step 1: Add example import red test**

Add `import runpy` near the top of `tests/tui/test_widgets_light_controls.py`.

Append:

```python
def test_widgets_light_controls_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/45_widgets_light_controls.py", run_name="__test__")

    assert "build_app" in namespace
```

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py::test_widgets_light_controls_example_imports -q
```

Expected: FAIL because `examples/tui/45_widgets_light_controls.py` does not exist.

- [ ] **Step 2: Create importable example**

Create `examples/tui/45_widgets_light_controls.py`.

Requirements:

- Import `Menu`, `MenuItem`, `Tabs`, `TabItem`, and `Spinner` from top-level `loushang.tui`.
- Define `LightControlsApp(FocusableMixin)` with:
  - `tabs: Tabs`
  - `menu: Menu`
  - `spinner_frame: int`
  - `message: str`
- `render()`:
  - Render title line.
  - Render `tabs`.
  - Render `Spinner(label="Syncing", frame=self.spinner_frame)`.
  - Render `menu`.
  - Render message.
  - Respect width/height with `RenderConstraints`.
- `handle_input()`:
  - Route `left`/`right` to tabs.
  - Route `up`/`down`/`home`/`end`/activation to menu.
  - On menu result `"refresh"`, increment spinner frame and set message.
  - On menu result `"open"`, set message using `tabs.value`.
- Define `build_app() -> Tui`.
- Keep `if __name__ == "__main__"` runner pattern consistent with examples `43` and `44`.

- [ ] **Step 3: Update English docs**

In `docs/en/reference/tui-widgets.md`:

- Add a `P0C Light Controls` section after P0B.
- Add table rows for `Menu` / `MenuItem`, `Tabs` / `TabItem`, and `Spinner`.
- Add short code snippet.
- Add theme tokens:
  - `widget.menu.item`
  - `widget.menu.focus`
  - `widget.menu.disabled`
  - `widget.menu.description`
  - `widget.tabs.tab`
  - `widget.tabs.selected`
  - `widget.tabs.focus`
  - `widget.tabs.disabled`
  - `widget.spinner.frame`
  - `widget.spinner.label`
- Remove `Menu`, `Spinner`, and `Tabs` from Planned Catalog.
- Ensure Planned Catalog still includes `Popover`, `PromptDialog`, `Table`, `TreeView`, `Toast`, and `TextArea`.
- Add example link to `examples/tui/45_widgets_light_controls.py`.

- [ ] **Step 4: Update Chinese docs**

Mirror English docs in `docs/zh-CN/reference/tui-widgets.md`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py -q
```

Expected: PASS.

- [ ] **Step 6: Run focused Ruff**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check tests/tui/test_widgets_light_controls.py examples/tui/45_widgets_light_controls.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/tui/test_widgets_light_controls.py examples/tui/45_widgets_light_controls.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md
git commit -m "docs(tui): document light controls widgets"
```

## Task 8: Full Verification

**Files:**
- Modify only if verification finds issues.

- [ ] **Step 1: Run focused P0C tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
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
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/45_widgets_light_controls.py docs
```

Expected: PASS.

- [ ] **Step 5: Inspect final branch status**

Run:

```bash
git status --short --branch
git log --oneline --decorate -8
```

Expected: clean branch with spec, plan, implementation, docs, and tests committed.

## Completion Criteria

- `Menu`, `MenuItem`, `Tabs`, `TabItem`, and `Spinner` are public stable exports.
- P0C controls obey width and height constraints under focused tests.
- Theme tokens apply without visible-width growth.
- `Menu` covers navigation, activation, disabled, empty, all-disabled, callback, height-window, description, and boundary semantics.
- `Tabs` covers canonical value normalization, selection, disabled, callback, activation, empty/all-disabled, and boundary semantics.
- `Spinner` is static and caller-driven.
- Example and docs are updated.
- Full TUI tests and Ruff pass.
