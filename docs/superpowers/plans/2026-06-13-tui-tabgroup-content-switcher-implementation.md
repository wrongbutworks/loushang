# TUI TabGroup And ContentSwitcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build reusable tabbed page content and searchable long-list widgets for `loushang.tui`.

**Architecture:** Keep existing `Tabs` as the header primitive, add `TabGroup` and `TabPage` as the composed page container, and keep `_ContentSwitcher` private inside the tab group module. Add `SearchableList` as a reusable widget-shaped extraction of behavior already proven by `SelectionSurface`, `SettingsSurface`, and `CommandPaletteView`.

**Tech Stack:** Python dataclasses, `loushang.tui` render/input primitives, `TextInput`, `ThemeResolver`, pytest widget tests, example playback harness.

---

## Spec

Implement against:

`docs/superpowers/specs/2026-06-12-tui-tabgroup-content-switcher-design.md`

Important decisions from the spec:

- `Tabs` remains a one-line selected-value primitive.
- `ContentSwitcher` is internal for the first slice.
- `TabGroup` returns `TabChange` for value changes when `on_change is None`.
- `SearchableList` is reusable widget page content, not a new settings schema.
- `SearchableList` first-slice filtering is case-insensitive substring matching over item keys and labels.
- Existing `widget.tabs.tab` must stay in the fallback chain for enabled unselected tabs.
- Public convenience exports include `TabGroup`, `TabPage`, `SearchableList`, `SearchableListItem`, and `SearchableListSelect`.
- `TabChange` remains defined in `src/loushang/tui/ui_parts/widgets/tab_group.py` as the local structured return object, but it is not re-exported through `loushang.tui`, `loushang.tui.ui_parts`, or `loushang.tui.ui_parts.widgets`.

## File Structure

Create:

- `src/loushang/tui/ui_parts/widgets/tab_group.py`
  - Owns `TabPage`, local `TabChange`, `TabGroup`, and private `_ContentSwitcher`.
  - Delegates tab header behavior to existing `Tabs`.
  - Delegates rendering, input, focus, blur, and editor target to selected page content.

- `src/loushang/tui/ui_parts/widgets/searchable_list.py`
  - Owns `SearchableListItem`, `SearchableListSelect`, and `SearchableList`.
  - Uses private `TextInput` as query source of truth.
  - Owns filtered items, active index, scroll offset, focus region, and overflow counts.

- `tests/tui/test_widgets_tab_group.py`
  - Unit tests for `TabGroup`, `TabPage`, local `TabChange`, `_ContentSwitcher` behavior through `TabGroup`, nested tab focus, and theme fallback.

- `tests/tui/test_widgets_searchable_list.py`
  - Unit tests for `SearchableList` filtering, active repair, focus transitions, viewport scrolling, disabled items, exports, and empty states.

- `examples/tui/52_widgets_tabgroup_searchable_list.py`
  - Settings-style example with top-level tabs, nested tabs, search, long list, fixed content canvas, and stable footer.

Modify:

- `src/loushang/tui/ui_parts/widgets/tabs.py`
  - Add level-aware theme token fallback while preserving current public behavior.
  - Keep `widget.tabs.tab` as the legacy normal fallback.

- `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export new public widget classes.

- `src/loushang/tui/ui_parts/__init__.py`
  - Re-export new public widget classes.

- `src/loushang/tui/__init__.py`
  - Re-export new public widget classes.

- `docs/en/reference/tui-widgets.md`
  - Document public `TabGroup` and `SearchableList` APIs at a high level.

- `docs/zh-CN/reference/tui-widgets.md`
  - Mirror the English reference update.

- `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`
  - Add the new UI part family to the inventory.

- `docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md`
  - Move the stable architecture guidance from the superpowers spec into the long-term internal UI part document.

Do not create or export a public `ContentSwitcher` in this slice.

## Task 1: Add TabGroup Core Tests

**Files:**

- Create: `tests/tui/test_widgets_tab_group.py`
- Reference: `tests/tui/test_widgets_light_controls.py`
- Reference: `src/loushang/tui/ui_parts/widgets/tabs.py`

- [ ] **Step 1: Create render helpers and dummy content classes**

Add this test scaffolding:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loushang.tui import CursorDeclaration, InputEvent, RenderConstraints, RenderLine, RenderResult, strip_control_sequences
from loushang.tui.ui_parts.widgets.tab_group import TabChange, TabGroup, TabPage


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


@dataclass(slots=True)
class StaticPage:
    lines: tuple[str, ...]

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines(
            [RenderLine(line[: constraints.width]) for line in self.lines[: constraints.max_height]],
            constraints=constraints,
        )


@dataclass(slots=True)
class FocusablePage(StaticPage):
    focused: bool = False
    events: list[str] | None = None

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        key = getattr(event, "key", "")
        if key:
            if self.events is not None:
                self.events.append(key)
            if key == "handled":
                return "page-handled"
            if key == "up":
                return None
        return None
```

- [ ] **Step 2: Add failing normalization and render tests**

Add tests:

```python
def test_tab_group_normalizes_value_and_renders_selected_page() -> None:
    group = TabGroup(
        [
            TabPage("overview", "Overview", StaticPage(("Overview page",))),
            TabPage("logs", "Logs", StaticPage(("Logs page",))),
        ],
        value="missing",
        content_height=2,
    )

    assert group.selected_value == "overview"
    assert group.selected_page is not None
    assert plain_lines(group, width=40, height=4) == (
        "* [Overview]    [Logs]",
        "Overview page",
        "",
    )
```

```python
def test_tab_group_fixed_content_height_pads_and_clips() -> None:
    group = TabGroup(
        [TabPage("long", "Long", StaticPage(("one", "two", "three")))],
        content_height=2,
    )

    assert plain_lines(group, width=20, height=5) == (
        "* [Long]",
        "one",
        "two",
    )

    short = TabGroup([TabPage("short", "Short", StaticPage(("one",)))], content_height=3)
    assert plain_lines(short, width=20, height=5) == (
        "* [Short]",
        "one",
        "",
        "",
    )
```

- [ ] **Step 3: Add failing input/focus tests**

Add tests:

```python
def test_tab_group_returns_tab_change_without_callback() -> None:
    group = TabGroup(
        [
            TabPage("one", "One", StaticPage(("One",))),
            TabPage("two", "Two", StaticPage(("Two",))),
        ],
        focused=True,
    )

    result = group.handle_input(InputEvent(kind="key", key="right"))

    assert result == TabChange(value="two", previous_value="one", level=0)
    assert group.selected_value == "two"
```

```python
def test_tab_group_callback_result_takes_precedence() -> None:
    calls: list[str] = []
    group = TabGroup(
        [
            TabPage("one", "One", StaticPage(("One",))),
            TabPage("two", "Two", StaticPage(("Two",))),
        ],
        focused=True,
        on_change=lambda value: calls.append(value),
    )

    assert group.handle_input(InputEvent(kind="key", key="right")) is True
    assert calls == ["two"]
```

```python
def test_tab_group_down_enters_content_and_up_returns_to_header() -> None:
    page = FocusablePage(("content",), events=[])
    group = TabGroup([TabPage("page", "Page", page)], focused=True)

    assert group.handle_input(InputEvent(kind="key", key="down")) is True
    assert group.header_focused is False
    assert page.focused is True

    assert group.handle_input(InputEvent(kind="key", key="handled")) == "page-handled"
    assert page.events == ["handled"]

    assert group.handle_input(InputEvent(kind="key", key="up")) is True
    assert group.header_focused is True
    assert page.focused is False
```

- [ ] **Step 4: Add failing state persistence and editor target tests**

Add tests:

```python
def test_tab_group_preserves_page_objects_across_switches() -> None:
    first = FocusablePage(("first",), events=[])
    second = FocusablePage(("second",), events=[])
    group = TabGroup(
        [TabPage("first", "First", first), TabPage("second", "Second", second)],
        focused=True,
    )

    group.focus_content()
    assert first.focused is True
    assert group.handle_input(InputEvent(kind="key", key="right")) == TabChange("second", "first", 0)
    assert first.focused is False
    assert second.focused is True

    group.handle_input(InputEvent(kind="key", key="left"))
    assert first is group.selected_page.content
    assert first.focused is True
```

```python
def test_tab_group_editor_target_delegates_only_when_content_focused() -> None:
    class EditorPage(FocusablePage):
        def editor_input_target(self) -> object | None:
            return "editor-target" if self.focused else None

    group = TabGroup([TabPage("edit", "Edit", EditorPage(("edit",)))], focused=True)

    assert group.editor_input_target() is None
    assert group.focus_content() is True
    assert group.editor_input_target() == "editor-target"
```

```python
def test_tab_group_offsets_selected_content_cursor() -> None:
    class CursorPage(StaticPage):
        def render(self, constraints: RenderConstraints) -> RenderResult:
            return RenderResult.from_lines(
                [RenderLine("abc")],
                constraints=constraints,
                cursor=CursorDeclaration(row=0, column=2),
            )

    group = TabGroup([TabPage("edit", "Edit", CursorPage(("abc",)))], focused=True)

    result = group.render(RenderConstraints(width=20, max_height=3))

    assert result.cursor == CursorDeclaration(row=1, column=2)
```

```python
def test_tab_group_renders_header_only_when_no_content_height_remains() -> None:
    group = TabGroup([TabPage("one", "One", StaticPage(("content",)))])

    assert plain_lines(group, width=20, height=1) == ("* [One]",)
```

- [ ] **Step 5: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/tui/test_widgets_tab_group.py -q
```

Expected: fail with `ModuleNotFoundError` for `loushang.tui.ui_parts.widgets.tab_group` or missing classes.

- [ ] **Step 6: Commit failing tests**

```bash
git add tests/tui/test_widgets_tab_group.py
git commit -m "test(tui): cover tab group core behavior"
```

## Task 2: Implement TabGroup Core

**Files:**

- Create: `src/loushang/tui/ui_parts/widgets/tab_group.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_tab_group.py`

- [ ] **Step 1: Add tab group module skeleton**

Create `src/loushang/tui/ui_parts/widgets/tab_group.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from loushang.tui.core import CursorDeclaration, RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import callback_result
from loushang.tui.ui_parts.widgets.tabs import TabItem, Tabs

__all__ = ["TabGroup", "TabPage"]


@dataclass(frozen=True, slots=True)
class TabPage:
    value: str
    label: str
    content: object
    disabled: bool = False
    badge: str = ""


@dataclass(frozen=True, slots=True)
class TabChange:
    value: str
    previous_value: str
    level: int = 0


@dataclass(slots=True)
class _ContentSwitcher:
    content_height: int | None = None

    def render(self, content: object | None, constraints: RenderConstraints) -> RenderResult:
        height = self._target_height(constraints)
        if content is None or height <= 0:
            return RenderResult.from_lines([RenderLine("") for _ in range(height)], constraints=constraints)
        render = getattr(content, "render", None)
        cursor = None
        if not callable(render):
            lines = [RenderLine("")]
        else:
            result = render(RenderConstraints(width=constraints.width, max_height=height, visible_height=constraints.visible_height))
            lines = list(result.lines[:height])
            if result.cursor is not None and result.cursor.row < len(lines):
                cursor = result.cursor
        while len(lines) < height:
            lines.append(RenderLine(""))
        return RenderResult.from_lines(lines[:height], constraints=constraints, cursor=cursor)

    def _target_height(self, constraints: RenderConstraints) -> int:
        if self.content_height is None:
            return max(0, constraints.max_height)
        return max(0, min(self.content_height, constraints.max_height))
```

- [ ] **Step 2: Add `TabGroup` dataclass and normalization**

Append:

```python
@dataclass(slots=True)
class TabGroup:
    pages: Sequence[TabPage]
    value: str = ""
    level: int = 0
    wrap: bool = True
    content_height: int | None = None
    focused: bool = False
    header_focused: bool = True
    on_change: Callable[[str], object] | None = None
    theme: ThemeResolver | None = None
    _pages: tuple[TabPage, ...] = field(default=(), init=False, repr=False)
    _tabs: Tabs = field(init=False, repr=False)
    _switcher: _ContentSwitcher = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._pages = tuple(self.pages)
        self.value = self._normalize_value(self.value)
        self._switcher = _ContentSwitcher(self.content_height)
        self._tabs = self._make_tabs()

    @property
    def selected_value(self) -> str:
        return self.value

    @property
    def selected_page(self) -> TabPage | None:
        for page in self._pages:
            if page.value == self.value and not page.disabled:
                return page
        return None

    def _enabled_indices(self) -> tuple[int, ...]:
        return tuple(index for index, page in enumerate(self._pages) if not page.disabled)

    def _index_for_value(self, value: str) -> int | None:
        for index, page in enumerate(self._pages):
            if page.value == value:
                return index
        return None

    def _normalize_value(self, requested: str) -> str:
        enabled = self._enabled_indices()
        if not enabled:
            return ""
        requested_index = self._index_for_value(requested)
        if requested_index is not None:
            if requested_index in enabled:
                return self._pages[requested_index].value
            for index in enabled:
                if index > requested_index:
                    return self._pages[index].value
        return self._pages[enabled[0]].value
```

- [ ] **Step 3: Add focus, blur, and delegation helpers**

Append:

```python
    def focus(self) -> None:
        self.focused = True
        self.focus_header()

    def blur(self) -> None:
        if self.focused and not self.header_focused:
            self._blur_content()
        self.focused = False
        self.header_focused = True
        self._sync_tabs()

    def focus_header(self) -> None:
        if not self.header_focused:
            self._blur_content()
        self.focused = True
        self.header_focused = True
        self._sync_tabs()

    def focus_content(self) -> bool:
        page = self.selected_page
        if page is None:
            return False
        focus = getattr(page.content, "focus", None)
        if not callable(focus):
            return False
        self.focused = True
        self.header_focused = False
        focus()
        self._sync_tabs()
        return True

    def _blur_content(self) -> None:
        page = self.selected_page
        if page is None:
            return
        blur = getattr(page.content, "blur", None)
        if callable(blur):
            blur()

    def editor_input_target(self) -> object | None:
        if not self.focused or self.header_focused:
            return None
        page = self.selected_page
        target = getattr(page.content, "editor_input_target", None) if page is not None else None
        return target() if callable(target) else None
```

- [ ] **Step 4: Add input handling and value change contract**

Append:

```python
    def handle_input(self, event: object) -> object:
        if not self.focused:
            return None
        if self.header_focused:
            return self._handle_header_input(event)
        return self._handle_content_input(event)

    def _handle_header_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key" and getattr(event, "key", "") in {"down", "enter"}:
            return True if self.focus_content() else False
        previous = self.value
        result = self._tabs.handle_input(event)
        if self._tabs.value != previous:
            return self._set_value(self._tabs.value, previous_value=previous)
        return result

    def _handle_content_input(self, event: object) -> object:
        page = self.selected_page
        handler = getattr(page.content, "handle_input", None) if page is not None else None
        if callable(handler):
            result = handler(event)
            if result is not None:
                return result
        if getattr(event, "kind", "") == "key" and getattr(event, "key", "") in {"up", "shift+tab"}:
            self.focus_header()
            return True
        return None

    def _set_value(self, value: str, *, previous_value: str) -> object:
        if value == previous_value:
            return False
        content_was_focused = self.focused and not self.header_focused
        if content_was_focused:
            self._blur_content()
        self.value = value
        self._sync_tabs()
        if content_was_focused:
            self.focus_content()
        if self.on_change is not None:
            return callback_result(self.on_change(value))
        return TabChange(value=value, previous_value=previous_value, level=self.level)
```

- [ ] **Step 5: Add rendering and internal `Tabs` sync**

Append:

```python
    def render(self, constraints: RenderConstraints) -> RenderResult:
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)
        self._sync_tabs()
        header = self._tabs.render(RenderConstraints(width=constraints.width, max_height=1, visible_height=constraints.visible_height))
        remaining_height = max(0, constraints.max_height - len(header.lines))
        if remaining_height <= 0:
            return RenderResult.from_lines(header.lines[: constraints.max_height], constraints=constraints)
        content = self._switcher.render(
            None if self.selected_page is None else self.selected_page.content,
            RenderConstraints(width=constraints.width, max_height=remaining_height, visible_height=constraints.visible_height),
        )
        cursor = None
        if content.cursor is not None and len(header.lines) + content.cursor.row < constraints.max_height:
            cursor = CursorDeclaration(row=len(header.lines) + content.cursor.row, column=content.cursor.column)
        return RenderResult.from_lines([*header.lines, *content.lines][: constraints.max_height], constraints=constraints, cursor=cursor)

    def _make_tabs(self) -> Tabs:
        tabs = Tabs(
            tuple(TabItem(page.value, page.label, page.disabled, page.badge) for page in self._pages),
            value=self.value,
            wrap=self.wrap,
            theme=self.theme,
            focused=self.focused and self.header_focused,
        )
        return tabs

    def _sync_tabs(self) -> None:
        self._tabs.tabs = tuple(TabItem(page.value, page.label, page.disabled, page.badge) for page in self._pages)
        self._tabs.value = self.value
        self._tabs.wrap = self.wrap
        self._tabs.theme = self.theme
        self._tabs.focused = self.focused and self.header_focused
```

This implementation intentionally starts without level-aware token arguments. Task 3 adds those to `Tabs` and updates `_make_tabs()` / `_sync_tabs()` to pass them. `TabChange` is intentionally defined in this module but omitted from `__all__`; tests can import it from the concrete module, but convenience exports should not expose it as public API.

- [ ] **Step 6: Add public re-exports**

Modify the three export files:

```python
from .tab_group import TabGroup as TabGroup
from .tab_group import TabPage as TabPage
```

Add `"TabGroup"` and `"TabPage"` to each relevant `__all__`. Do not re-export `TabChange` through `loushang.tui`, `loushang.tui.ui_parts`, or `loushang.tui.ui_parts.widgets`.

- [ ] **Step 7: Run core tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_tab_group.py -q
uv run pytest tests/tui/test_widgets_light_controls.py -q
```

Expected: all pass. If an existing `Tabs` test fails, preserve existing `Tabs` behavior and adjust only `TabGroup`.

- [ ] **Step 8: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/tab_group.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_tab_group.py
git commit -m "feat(tui): add tab group widget"
```

## Task 3: Add Level-Aware Tab Theme Tokens

**Files:**

- Modify: `src/loushang/tui/ui_parts/widgets/tabs.py`
- Modify: `src/loushang/tui/ui_parts/widgets/tab_group.py`
- Modify: `tests/tui/test_widgets_light_controls.py`
- Modify: `tests/tui/test_widgets_tab_group.py`

- [ ] **Step 1: Add failing compatibility test for `widget.tabs.tab` fallback**

Add or update in `tests/tui/test_widgets_light_controls.py`:

```python
def test_tabs_level_tokens_fallback_to_legacy_tab_token() -> None:
    theme = ThemeResolver(defaults={"widget.tabs.tab": {"color": "red"}})
    tabs = Tabs([TabItem("one", "One"), TabItem("two", "Two")], theme=theme)

    raw = render_lines(tabs, width=40, height=1)[0]

    assert "\x1b[31m  [Two]" in raw
```

- [ ] **Step 2: Add failing content-focus token test**

Add to `tests/tui/test_widgets_tab_group.py`:

```python
def test_tab_group_uses_distinct_header_and_content_focus_tokens() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.tabs.level0.selected_header_focus": {"color": "cyan"},
            "widget.tabs.level0.selected_content_focus": {"color": "green"},
            "widget.tabs.tab": {"color": "white"},
        }
    )
    page = FocusablePage(("content",))
    group = TabGroup([TabPage("main", "Main", page)], focused=True, theme=theme)

    header_raw = render_lines(group, width=40, height=3)[0]
    assert header_raw.startswith("\x1b[36m")

    assert group.focus_content() is True
    content_raw = render_lines(group, width=40, height=3)[0]
    assert content_raw.startswith("\x1b[32m")
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
uv run pytest tests/tui/test_widgets_light_controls.py::test_tabs_level_tokens_fallback_to_legacy_tab_token tests/tui/test_widgets_tab_group.py::test_tab_group_uses_distinct_header_and_content_focus_tokens -q
```

Expected: fail because `Tabs` has no level-aware token state yet.

- [ ] **Step 4: Extend `Tabs` dataclass without breaking current callers**

In `src/loushang/tui/ui_parts/widgets/tabs.py`, add:

```python
from typing import Literal

TabFocusState = Literal["auto", "header", "content", "none"]
```

Add fields:

```python
level: int = 0
selected_focus: TabFocusState = "auto"
```

Existing callers that only set `focused=True` must still get the legacy focused selected rendering.

- [ ] **Step 5: Replace single-token tab styling with fallback-token cascades**

Add helpers near `_tab_segment`:

```python
def _selected_focus_state(tabs: Tabs) -> str:
    if tabs.selected_focus != "auto":
        return tabs.selected_focus
    return "header" if tabs.focused else "none"


def _tab_tokens(tabs: Tabs, *, selected: bool, disabled: bool) -> tuple[str, ...]:
    level = max(0, tabs.level)
    nested_prefix = "widget.tabs.nested" if level > 0 else ""
    level_prefix = f"widget.tabs.level{level}"
    if disabled:
        return tuple(token for token in ("widget.tabs.disabled", f"{nested_prefix}.disabled" if nested_prefix else "", f"{level_prefix}.disabled") if token)
    if selected:
        focus_state = _selected_focus_state(tabs)
        if focus_state == "header":
            return tuple(
                token
                for token in (
                    "widget.tabs.selected",
                    "widget.tabs.focus",
                    f"{nested_prefix}.selected_header_focus" if nested_prefix else "",
                    f"{level_prefix}.selected_header_focus",
                )
                if token
            )
        if focus_state == "content":
            return tuple(
                token
                for token in (
                    "widget.tabs.selected",
                    f"{nested_prefix}.selected_content_focus" if nested_prefix else "",
                    f"{level_prefix}.selected_content_focus",
                )
                if token
            )
        return ("widget.tabs.selected",)
    return tuple(
        token
        for token in (
            "widget.tabs.tab",
            "widget.tabs.normal",
            f"{nested_prefix}.normal" if nested_prefix else "",
            f"{level_prefix}.normal",
        )
        if token
    )
```

Pass these tokens to `style_text(text, tabs.theme, *_tab_tokens(...))`.

Order matters: `style_text()` merges later tokens over earlier tokens, so fallback tokens must come first and level-specific tokens last.

- [ ] **Step 6: Pass level and selected focus from `TabGroup`**

Update `_make_tabs()` and `_sync_tabs()` in `tab_group.py`:

```python
selected_focus = "header" if self.focused and self.header_focused else "content" if self.focused else "none"
tabs.level = self.level
tabs.selected_focus = selected_focus
```

- [ ] **Step 7: Run tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_tab_group.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/tabs.py src/loushang/tui/ui_parts/widgets/tab_group.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_tab_group.py
git commit -m "feat(tui): add level-aware tab theme tokens"
```

## Task 4: Add Nested TabGroup Behavior

**Files:**

- Modify: `tests/tui/test_widgets_tab_group.py`
- Modify: `src/loushang/tui/ui_parts/widgets/tab_group.py`

- [ ] **Step 1: Add failing nested focus test**

Add:

```python
def test_nested_tab_group_keeps_parent_selected_content_focus() -> None:
    nested_page = FocusablePage(("nested content",))
    nested = TabGroup([TabPage("overview", "Overview", nested_page)], level=1)
    outer = TabGroup([TabPage("stats", "Stats", nested)], focused=True)

    assert outer.focus_content() is True
    assert nested.focused is True
    assert nested.header_focused is True
    assert outer.header_focused is False

    raw = render_lines(outer, width=60, height=6)
    assert "Stats" in strip_control_sequences(raw[0])
    assert "Overview" in strip_control_sequences(raw[1])
```

- [ ] **Step 2: Add failing nested switching test**

Add:

```python
def test_nested_tab_switch_does_not_change_parent_value() -> None:
    nested = TabGroup(
        [
            TabPage("overview", "Overview", StaticPage(("overview",))),
            TabPage("models", "Models", StaticPage(("models",))),
        ],
        level=1,
    )
    outer = TabGroup([TabPage("stats", "Stats", nested)], focused=True)

    outer.focus_content()
    result = outer.handle_input(InputEvent(kind="key", key="right"))

    assert result == TabChange(value="models", previous_value="overview", level=1)
    assert outer.selected_value == "stats"
    assert nested.selected_value == "models"
```

- [ ] **Step 3: Run nested tests to verify failure**

Run:

```bash
uv run pytest tests/tui/test_widgets_tab_group.py::test_nested_tab_group_keeps_parent_selected_content_focus tests/tui/test_widgets_tab_group.py::test_nested_tab_switch_does_not_change_parent_value -q
```

Expected: fail if `TabGroup.focus()` always forces header focus or if nested input is not delegated cleanly.

- [ ] **Step 4: Adjust `TabGroup.focus()` semantics for embedded focus**

Keep external `TabGroup.focus()` defaulting to header focus. In `focus_content()`, calling `focus()` on a nested `TabGroup` will focus its header, which is the desired entry point for the nested group.

If tests fail because render does not show nested content, ensure `TabGroup.render()` delegates selected page rendering through `_ContentSwitcher` with the full remaining height.

- [ ] **Step 5: Run full TabGroup tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_tab_group.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/tab_group.py tests/tui/test_widgets_tab_group.py
git commit -m "test(tui): cover nested tab group behavior"
```

## Task 5: Add SearchableList Tests

**Files:**

- Create: `tests/tui/test_widgets_searchable_list.py`
- Reference: `tests/tui/test_widgets_command_palette.py`
- Reference: `tests/tui/test_surfaces.py`

- [ ] **Step 1: Create test helpers and item fixture**

Add:

```python
from __future__ import annotations

from typing import Any

from loushang.tui import InputEvent, RenderConstraints, strip_control_sequences
from loushang.tui.ui_parts.widgets.searchable_list import SearchableList, SearchableListItem, SearchableListSelect


def render_lines(part: Any, *, width: int = 60, height: int = 10) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 60, height: int = 10) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def _items() -> tuple[SearchableListItem, ...]:
    return (
        SearchableListItem("model", "Model", "kimi-for-coding"),
        SearchableListItem("thinking-mode", "Thinking mode", "true"),
        SearchableListItem("permission-mode", "Default permission mode", "Default"),
        SearchableListItem("editor-mode", "Editor mode", "vim"),
        SearchableListItem("archive", "Archive", "disabled", disabled=True),
    )
```

- [ ] **Step 2: Add failing query/filter tests**

Add:

```python
def test_searchable_list_filters_key_and_label_case_insensitive_in_order() -> None:
    view = SearchableList(_items(), query="MODE")

    assert view.query == "MODE"
    assert [item.key for item in view.filtered_items] == [
        "model",
        "thinking-mode",
        "permission-mode",
        "editor-mode",
    ]

    view.set_query("permission")
    assert [item.key for item in view.filtered_items] == ["permission-mode"]
```

- [ ] **Step 3: Add failing focus and activation tests**

Add:

```python
def test_searchable_list_search_down_enters_list_and_up_returns_to_search() -> None:
    view = SearchableList(_items(), focused=True)

    assert view.focus_region == "search"
    assert view.handle_input(InputEvent(kind="key", key="down")) is True
    assert view.focus_region == "list"
    assert view.active_key == "model"

    assert view.handle_input(InputEvent(kind="key", key="up")) is True
    assert view.focus_region == "search"
```

```python
def test_searchable_list_activation_returns_structured_select() -> None:
    view = SearchableList(_items(), focused=True)

    assert view.handle_input(InputEvent(kind="key", key="enter")) == SearchableListSelect(
        key="model",
        label="Model",
        value="kimi-for-coding",
    )
```

- [ ] **Step 4: Add failing disabled and empty tests**

Add:

```python
def test_searchable_list_disabled_items_visible_but_not_active() -> None:
    view = SearchableList(_items(), query="archive", focused=True)

    assert [item.key for item in view.filtered_items] == ["archive"]
    assert view.active_item is None
    assert view.active_key == ""
    assert view.handle_input(InputEvent(kind="key", key="enter")) is None
    assert any("Archive" in line for line in plain_lines(view))
```

```python
def test_searchable_list_empty_result_resets_scroll_and_overflow() -> None:
    view = SearchableList(_items(), query="missing", focused=True)

    assert view.filtered_items == ()
    assert view.active_item is None
    assert view.scroll_offset == 0
    assert view.more_above == 0
    assert view.more_below == 0
    assert "No matching items" in plain_lines(view, width=40, height=5)
```

- [ ] **Step 5: Add failing viewport tests**

Add:

```python
def test_searchable_list_renders_bounded_viewport_and_overflow_counts() -> None:
    items = tuple(SearchableListItem(f"item-{index}", f"Item {index}") for index in range(20))
    view = SearchableList(items, focused=True)
    view.focus_list()

    lines = plain_lines(view, width=40, height=6)
    assert any("Item 0" in line for line in lines)
    assert not any("Item 19" in line for line in lines)
    assert view.more_above == 0
    assert view.more_below > 0

    for _ in range(8):
        view.handle_input(InputEvent(kind="key", key="down"))
    plain_lines(view, width=40, height=6)
    assert view.more_above > 0
    assert view.more_below > 0
```

- [ ] **Step 6: Run tests to verify failure**

Run:

```bash
uv run pytest tests/tui/test_widgets_searchable_list.py -q
```

Expected: fail with missing module/classes.

- [ ] **Step 7: Commit failing tests**

```bash
git add tests/tui/test_widgets_searchable_list.py
git commit -m "test(tui): cover searchable list widget"
```

## Task 6: Implement SearchableList

**Files:**

- Create: `src/loushang/tui/ui_parts/widgets/searchable_list.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_searchable_list.py`

- [ ] **Step 1: Audit existing list behavior before coding**

Read these files and keep the new widget aligned:

```bash
sed -n '1,240p' src/loushang/tui/surfaces.py
sed -n '80,340p' src/loushang/tui/ui_parts/widgets/command_palette.py
sed -n '1,120p' src/loushang/tui/ui_parts/widgets/selection.py
```

Expected: confirm the new widget should not inherit `SelectionSurface`, and should keep surface close semantics out of tab pages.

- [ ] **Step 2: Add module skeleton**

Create `searchable_list.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width, visible_width
from loushang.tui.core import CursorDeclaration, RenderConstraints, RenderLine, RenderResult
from loushang.tui.keybindings import normalize_key_id
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.text_input import TextInput
from loushang.tui.ui_parts.widgets._utils import callback_result, style_text

__all__ = ["SearchableList", "SearchableListItem", "SearchableListSelect"]


@dataclass(frozen=True, slots=True)
class SearchableListItem:
    key: str
    label: str
    value: str = ""
    description: str = ""
    disabled: bool = False


@dataclass(frozen=True, slots=True)
class SearchableListSelect:
    key: str
    label: str
    value: str = ""
```

- [ ] **Step 3: Add constructor with private item snapshot and `TextInput`**

Use `init=False`, matching `CommandPaletteView`:

```python
@dataclass(slots=True, init=False)
class SearchableList:
    _items: tuple[SearchableListItem, ...]
    _query_input: TextInput
    _active_index: int = field(default=0, init=False, repr=False)
    _scroll_offset: int = field(default=0, init=False, repr=False)
    _last_visible_count: int = field(default=0, init=False, repr=False)
    focus_region: str
    placeholder: str
    empty_text: str
    on_select: Callable[[SearchableListItem], object] | None
    theme: ThemeResolver | None
    focused: bool

    def __init__(
        self,
        items: Sequence[SearchableListItem],
        *,
        query: str = "",
        active_index: int = 0,
        focus_region: str = "search",
        placeholder: str = "Search",
        empty_text: str = "No matching items",
        on_select: Callable[[SearchableListItem], object] | None = None,
        theme: ThemeResolver | None = None,
        focused: bool = False,
    ) -> None:
        self._items = tuple(items)
        self.placeholder = placeholder
        self.empty_text = empty_text
        self.on_select = on_select
        self.theme = theme
        self.focused = focused
        self.focus_region = focus_region if focus_region in {"search", "list"} else "search"
        self._active_index = max(0, active_index)
        self._scroll_offset = 0
        self._last_visible_count = 0
        self._query_input = TextInput(placeholder=placeholder, theme=theme, focused=focused and self.focus_region == "search")
        self._query_input.set_text(query)
        self._repair_active(previous_key="")
```

- [ ] **Step 4: Add public properties and query repair**

Implement:

```python
    @property
    def query(self) -> str:
        return self._query_input.value

    @property
    def filtered_items(self) -> tuple[SearchableListItem, ...]:
        needle = self.query.casefold().strip()
        if not needle:
            return self._items
        return tuple(item for item in self._items if _matches(item, needle))

    @property
    def active_item(self) -> SearchableListItem | None:
        items = self.filtered_items
        if self._active_index < 0 or self._active_index >= len(items):
            return None
        item = items[self._active_index]
        return None if item.disabled else item

    @property
    def active_key(self) -> str:
        item = self.active_item
        return "" if item is None else item.key

    @property
    def scroll_offset(self) -> int:
        return self._scroll_offset

    @property
    def more_above(self) -> int:
        return max(0, self._scroll_offset)

    @property
    def more_below(self) -> int:
        return max(0, len(self.filtered_items) - (self._scroll_offset + self._last_visible_count))

    def set_query(self, query: str) -> None:
        previous_key = self.active_key
        self._query_input.set_text(query)
        self._repair_active(previous_key=previous_key)
```

`_matches()` should use only `item.key` and `item.label` in the first slice.

- [ ] **Step 5: Add focus and editor target behavior**

Implement:

```python
    def focus(self) -> None:
        self.focused = True
        self.focus_search()

    def blur(self) -> None:
        self.focused = False
        self._query_input.blur()

    def focus_search(self) -> None:
        self.focus_region = "search"
        self._query_input.focus()

    def focus_list(self) -> bool:
        if self.active_item is None:
            return False
        self.focus_region = "list"
        self._query_input.blur()
        return True

    def editor_input_target(self) -> object | None:
        if not self.focused or self.focus_region != "search":
            return None
        return self._query_input.editor_input_target()
```

- [ ] **Step 6: Add input handling**

Implement search/list routing:

```python
    def handle_input(self, event: object) -> object:
        kind = getattr(event, "kind", "")
        if self.focus_region == "search":
            return self._handle_search_input(event)
        if self.focus_region == "list":
            return self._handle_list_input(event)
        return None
```

Search behavior:

```python
    def _handle_search_input(self, event: object) -> object:
        kind = getattr(event, "kind", "")
        if kind in {"text", "paste"}:
            before = self.query
            previous_key = self.active_key
            handled = self._query_input.handle_input(event)
            if handled and self.query != before:
                self._repair_active(previous_key=previous_key)
            return handled or None
        if kind != "key":
            return None
        key = normalize_key_id(getattr(event, "key", ""))
        if key == "down":
            return True if self.focus_list() else None
        if key == "enter":
            return self._select_active()
        if key in {"escape", "esc"} and self.query:
            self.set_query("")
            return True
        if key == "up":
            return None
        before = self.query
        previous_key = self.active_key
        handled = self._query_input.handle_editing_key(key)
        if handled and self.query != before:
            self._repair_active(previous_key=previous_key)
        return True if handled else None
```

List behavior:

```python
    def _handle_list_input(self, event: object) -> object:
        if getattr(event, "kind", "") != "key":
            return None
        key = normalize_key_id(getattr(event, "key", ""))
        if key == "up" and self._at_first_enabled_item():
            self.focus_search()
            return True
        if key == "up":
            return self._move_active(-1)
        if key == "down":
            return self._move_active(1)
        if key == "pageup":
            return self._move_active(-max(1, self._last_visible_count))
        if key == "pagedown":
            return self._move_active(max(1, self._last_visible_count))
        if key == "home":
            return self._jump_active(first=True)
        if key == "end":
            return self._jump_active(first=False)
        if key == "enter":
            return self._select_active()
        return None
```

- [ ] **Step 7: Add active repair and movement helpers**

Use the `CommandPaletteView` pattern. Disabled items stay visible but are skipped.

```python
def _enabled_indices(items: tuple[SearchableListItem, ...]) -> tuple[int, ...]:
    return tuple(index for index, item in enumerate(items) if not item.disabled)


def _matches(item: SearchableListItem, needle: str) -> bool:
    return needle in item.key.casefold() or needle in item.label.casefold()
```

Implement `_repair_active()`, `_move_active()`, `_jump_active()`, `_at_first_enabled_item()`, `_ensure_active_visible(height)`, and `_select_active()`.

`_select_active()` returns:

```python
item = self.active_item
if item is None:
    return None
if self.on_select is not None:
    return callback_result(self.on_select(item))
return SearchableListSelect(item.key, item.label, item.value)
```

- [ ] **Step 8: Add render behavior**

Render search row first, then list rows. Keep output within `constraints.max_height`.

Use theme tokens:

- `widget.searchableList.search`
- `widget.searchableList.placeholder`
- `widget.searchableList.item`
- `widget.searchableList.focus`
- `widget.searchableList.disabled`
- `widget.searchableList.description`
- `widget.searchableList.empty`
- `widget.searchableList.overflow`

Do not require defaults in `ThemeResolver`; missing tokens should render plain text.

- [ ] **Step 9: Add public re-exports**

Modify the three export files with:

```python
from .searchable_list import SearchableList as SearchableList
from .searchable_list import SearchableListItem as SearchableListItem
from .searchable_list import SearchableListSelect as SearchableListSelect
```

Add names to `__all__`.

- [ ] **Step 10: Run tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_searchable_list.py -q
uv run pytest tests/tui/test_widgets_command_palette.py -q
uv run pytest tests/tui/test_surfaces.py -q
```

Expected: all pass. If `test_surfaces.py` fails, the new widget leaked behavior into existing surfaces; revert that coupling.

- [ ] **Step 11: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/searchable_list.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_searchable_list.py
git commit -m "feat(tui): add searchable list widget"
```

## Task 7: Add Settings-Style Example And Playback

**Files:**

- Create: `examples/tui/52_widgets_tabgroup_searchable_list.py`
- Modify: `tests/tui/test_widgets_tab_group.py`
- Modify: `tests/tui/test_widgets_searchable_list.py` if example-specific assertions belong there instead
- Reference: `tests/tui/widget_example_playback.py`
- Reference: `examples/tui/45_widgets_light_controls.py`
- Reference: `examples/tui/51_widgets_command_palette.py`

- [ ] **Step 1: Add example app skeleton**

Create `examples/tui/52_widgets_tabgroup_searchable_list.py` with:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    SearchableList,
    SearchableListItem,
    SearchableListSelect,
    TabGroup,
    TabPage,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)
```

Use top-level tabs:

```text
Workspace   Models   Permissions   Activity
```

Use `Activity` nested tabs:

```text
Overview   Models
```

- [ ] **Step 2: Implement fixed content canvas and footer in the example app**

The app should compose:

- `TabGroup(content_height=...)`
- `SearchableList` in the Workspace page
- nested `TabGroup(level=1)` in the Activity page
- footer text owned by the app, not by `TabGroup`

Footer examples:

```text
Type to filter · Enter/down to select · Up to tabs · Esc to clear
```

Keep example text ASCII-only.

- [ ] **Step 3: Add playback test imports**

Add these imports to `tests/tui/test_widgets_tab_group.py`:

```python
from tests.tui.widget_example_playback import play_example
```

The file should already import `InputEvent`. If not, import it from `loushang.tui`.

- [ ] **Step 4: Add playback test for initial render and filtering**

Add to `tests/tui/test_widgets_tab_group.py`:

```python
def test_tabgroup_searchable_list_example_playback_filters_settings() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("type mode", InputEvent(kind="text", text="mode")),
        ),
        width=100,
        height=24,
    )

    initial = frames[0].lines
    filtered = frames[-1].lines

    assert any("Workspace" in line and "Activity" in line for line in initial)
    assert any("Search" in line for line in initial)
    assert any("mode" in line.lower() for line in filtered)
    assert any("Model" in line or "mode" in line for line in filtered)
```

- [ ] **Step 5: Add playback test for tab and nested tab switching**

Add:

```python
def test_tabgroup_searchable_list_example_playback_switches_nested_tabs() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("up to tabs", InputEvent(kind="key", key="up")),
            ("right models", InputEvent(kind="key", key="right")),
            ("right permissions", InputEvent(kind="key", key="right")),
            ("right activity", InputEvent(kind="key", key="right")),
            ("down nested", InputEvent(kind="key", key="down")),
            ("right nested models", InputEvent(kind="key", key="right")),
        ),
        width=100,
        height=24,
    )

    assert any("Overview" in line and "Models" in line for line in frames[-1].lines)
    assert any("Tokens per Day" in line or "Model usage" in line for line in frames[-1].lines)
```

- [ ] **Step 6: Add playback test for long-list bounded viewport**

Add:

```python
def test_tabgroup_searchable_list_example_playback_scrolls_long_list_without_layout_jump() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=tuple((f"down {index}", InputEvent(kind="key", key="down")) for index in range(18)),
        width=100,
        height=24,
    )

    footer_rows = [next(index for index, line in enumerate(frame.lines) if "Enter" in line or "filter" in line) for frame in frames]
    assert len(set(footer_rows)) == 1
    assert any("more below" in line.lower() or "more above" in line.lower() for line in frames[-1].lines)
```

- [ ] **Step 7: Add playback test for long-list page keys**

Add:

```python
def test_tabgroup_searchable_list_example_playback_page_keys_and_edges() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("down to list", InputEvent(kind="key", key="down")),
            ("page down", InputEvent(kind="key", key="pagedown")),
            ("end", InputEvent(kind="key", key="end")),
            ("page up", InputEvent(kind="key", key="pageup")),
            ("home", InputEvent(kind="key", key="home")),
        ),
        width=100,
        height=24,
    )

    assert any("more below" in line.lower() for line in frames[0].lines)
    assert any("more above" in line.lower() or "more below" in line.lower() for line in frames[2].lines)
    assert any("more below" in line.lower() for line in frames[-1].lines)
```

- [ ] **Step 8: Add playback test for state preservation across tab switches**

Add:

```python
def test_tabgroup_searchable_list_example_playback_preserves_list_state_across_tabs() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("down to list", InputEvent(kind="key", key="down")),
            ("page down", InputEvent(kind="key", key="pagedown")),
            ("page down again", InputEvent(kind="key", key="pagedown")),
            ("shift tab to top tabs", InputEvent(kind="key", key="shift+tab")),
            ("right models", InputEvent(kind="key", key="right")),
            ("left workspace", InputEvent(kind="key", key="left")),
            ("down content", InputEvent(kind="key", key="down")),
        ),
        width=100,
        height=24,
    )

    final = "\n".join(frames[-1].lines).lower()
    assert "more above" in final
```

- [ ] **Step 9: Run playback tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_tab_group.py tests/tui/test_widgets_searchable_list.py -q
```

Expected: all pass.

- [ ] **Step 10: Run the example manually as a smoke command**

Run:

```bash
uv run python examples/tui/52_widgets_tabgroup_searchable_list.py
```

Expected: opens an interactive TUI. Quit with `q`. If running in a non-interactive automation context, skip this command and rely on playback tests.

- [ ] **Step 11: Commit**

```bash
git add examples/tui/52_widgets_tabgroup_searchable_list.py tests/tui/test_widgets_tab_group.py tests/tui/test_widgets_searchable_list.py
git commit -m "test(tui): add tab group searchable list playback"
```

## Task 8: Update Reference And Internal Docs

**Files:**

- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`
- Modify: `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`
- Create: `docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md`

- [ ] **Step 1: Add English reference section**

Add a new section after P2A or as P2B:

```markdown
## P2B Tabbed Content

| Widget | Use it for |
| --- | --- |
| `TabGroup` / `TabPage` | Tab header plus persistent page content. |
| `SearchableList` / `SearchableListItem` | Searchable long lists that can live inside a tab page. |

`TabGroup` composes existing `Tabs` with persistent page content. It keeps
`ContentSwitcher` internal and returns a structured tab-change object when the
selected page changes without a callback.

`SearchableList` owns query text, filtered items, active row, viewport offset,
and structured selection. It does not edit settings or write configuration.
```

- [ ] **Step 2: Add Chinese reference section**

Mirror the English content in `docs/zh-CN/reference/tui-widgets.md`.

- [ ] **Step 3: Create long-term internal architecture document**

Create `docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md` with stable guidance distilled from the spec:

```markdown
# TabGroup And SearchableList UI Parts

## Purpose

`TabGroup` composes a tab header with persistent page content. `SearchableList`
provides a reusable searchable long-list page widget. `ContentSwitcher` remains
an internal helper for fixed-height selected-content rendering.

## Inputs And State

- `TabPage(value, label, content, disabled=False, badge="")`
- `TabGroup(pages, value="", level=0, content_height=None, focused=False)`
- `SearchableListItem(key, label, value="", description="", disabled=False)`
- `SearchableList(items, query="", focus_region="search", focused=False)`

## Render Constraints

Both widgets must respect `RenderConstraints.width` and
`RenderConstraints.max_height`. Long logical lists render only the visible slice.

## Focus Behavior

`TabGroup` switches between header focus and selected content focus.
`SearchableList` switches between search focus and list focus.

## Events

`TabGroup` value changes return a local structured tab-change object unless an
`on_change` callback is supplied. `SearchableList` activation returns
`SearchableListSelect` unless `on_select` is supplied.

## Theme Tokens

Tab theme resolution must preserve legacy `widget.tabs.tab` fallback while
supporting level-aware selected header/content focus tokens.

## Test Obligations

Unit tests cover selection, focus, fixed-height rendering, nested tabs,
search/filter repair, viewport scrolling, disabled items, and exports. Playback
tests cover settings-style search, nested tabs, long-list scroll keys, footer
stability, and state preservation across tab switches.
```

- [ ] **Step 4: Update internal UI part inventory**

Add to `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`:

```markdown
| Navigation | Tabs, TabGroup, TabPage |
| Lists | SelectList, SearchableList |
```

Adjust existing rows instead of duplicating table categories if the inventory already has a better grouping. Link `TabGroup` or the family name to `./tabgroup-content-switcher.md`.

- [ ] **Step 5: Run docs-related smoke tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_command_palette.py tests/tui/test_widgets_tab_group.py tests/tui/test_widgets_searchable_list.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md
git commit -m "docs(tui): document tab group widgets"
```

## Task 9: Final Regression Pass

**Files:**

- No source edits expected.

- [ ] **Step 1: Run targeted TUI widget regression**

Run:

```bash
uv run pytest tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_command_palette.py tests/tui/test_widgets_tab_group.py tests/tui/test_widgets_searchable_list.py tests/tui/test_surfaces.py -q
```

Expected: all pass.

- [ ] **Step 2: Run broader TUI widget suite**

Run:

```bash
uv run pytest tests/tui/test_widgets_foundation.py tests/tui/test_widgets_table.py tests/tui/test_widgets_textarea.py tests/tui/test_widgets_tree.py tests/tui/test_widgets_question_dialog.py tests/tui/test_widgets_toast.py -q
```

Expected: all pass.

- [ ] **Step 3: Inspect public exports**

Run:

```bash
uv run python - <<'PY'
from loushang.tui import TabGroup, TabPage, SearchableList, SearchableListItem, SearchableListSelect
from loushang.tui.ui_parts import TabGroup as UiTabGroup
from loushang.tui.ui_parts.widgets import TabGroup as WidgetTabGroup
assert TabGroup is UiTabGroup is WidgetTabGroup
print("exports ok")
PY
```

Expected: prints `exports ok`. `TabChange` should remain importable from `loushang.tui.ui_parts.widgets.tab_group` for local tests, but it should not be part of the convenience export chain.

- [ ] **Step 4: Check git status**

Run:

```bash
git status --short --branch
```

Expected: clean working tree with implementation commits ahead of `origin/main`.

## Notes For Implementers

- Do not export `ContentSwitcher`.
- Do not directly subclass `SelectionSurface` or `SettingsSurface` for `SearchableList`.
- Do not add settings persistence or inline setting editors in this plan.
- Keep `SearchableList` filtering to key and label, matching the current spec.
- Keep every render path bounded by `RenderConstraints.max_height`.
- Keep old `Tabs` behavior and tests passing.
- If a step requires writing `.git` and the sandbox has `.git` read-only, request elevated sandbox permissions for the git command only.
