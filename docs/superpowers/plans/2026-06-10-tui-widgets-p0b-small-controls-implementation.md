# TUI Widgets P0B Small Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add P0B small TUI controls for badges, status pills, static progress, key/value details, and toolbar actions.

**Architecture:** Keep the controls as plain `Renderable`/`Focusable` widget modules under `src/loushang/tui/ui_parts/widgets/`. Put display-only widgets in `display.py`, toolbar-specific focus and activation behavior in `toolbar.py`, and reuse existing width helpers plus `widgets._utils.style_text()` for theme-safe rendering. Public APIs are re-exported through `widgets`, `ui_parts`, and top-level `loushang.tui`.

**Tech Stack:** Python 3.11 dataclasses, `RenderResult`/`RenderConstraints`, existing TUI theme and width helpers, `pytest`, `uv`, Ruff.

---

## File Structure

- Create `src/loushang/tui/ui_parts/widgets/display.py`
  - Owns `Badge`, `StatusPill`, `ProgressBar`, `KeyValueItem`, and `KeyValueList`.
  - Contains only display renderables; no input handling.
- Create `src/loushang/tui/ui_parts/widgets/toolbar.py`
  - Owns `ToolbarAction` and `Toolbar`.
  - Implements local focus, navigation, disabled skipping, and activation.
- Modify `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export P0B widget classes and type aliases.
- Modify `src/loushang/tui/ui_parts/__init__.py`
  - Re-export stable P0B widgets.
- Modify `src/loushang/tui/__init__.py`
  - Re-export stable P0B widgets at top level.
- Create `tests/tui/test_widgets_small_controls.py`
  - Focused tests for public exports, rendering, theme tokens, width/height constraints, and toolbar input.
- Create `examples/tui/44_widgets_small_controls.py`
  - Importable demo app showing status/details/progress/toolbar composition.
- Modify `docs/en/reference/tui-widgets.md`
  - Add P0B widgets and theme tokens.
- Modify `docs/zh-CN/reference/tui-widgets.md`
  - Mirror English docs.

Do not modify `Loader`, `Rule`, `Text`, `Button`, `Dialog`, `SurfaceHost`, or input intent definitions unless a planned test proves a direct integration failure.

## Task 1: Add Display Control Red Tests

**Files:**
- Create: `tests/tui/test_widgets_small_controls.py`
- Test: `tests/tui/test_widgets_small_controls.py`

- [ ] **Step 1: Write failing display-control tests**

Create `tests/tui/test_widgets_small_controls.py`:

```python
from __future__ import annotations

import runpy
from typing import Any

from loushang.tui import (
    Badge,
    KeyValueItem,
    KeyValueList,
    ProgressBar,
    RenderConstraints,
    StatusPill,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import Badge as UiBadge
from loushang.tui.ui_parts.widgets import Badge as WidgetBadge


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def test_small_controls_are_reexported_from_public_modules() -> None:
    assert Badge is UiBadge
    assert Badge is WidgetBadge
    assert KeyValueItem("model", "kimi").key == "model"


def test_badge_and_status_pill_render_plain_and_themed_text() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.badge.info": {"color": "cyan"},
            "widget.status.success": {"color": "green", "bold": True},
        }
    )

    badge = Badge("beta", kind="info", theme=theme)
    status = StatusPill("ready", status="success", theme=theme)

    badge_raw = render_lines(badge, width=20)
    status_raw = render_lines(status, width=20)

    assert badge_raw[0].startswith("\x1b[36m")
    assert status_raw[0].startswith("\x1b[1;32m")
    assert strip_control_sequences(badge_raw[0]) == "[beta]"
    assert strip_control_sequences(status_raw[0]) == "(ready)"
    assert plain_lines(Badge("beta")) == ("[beta]",)
    assert plain_lines(StatusPill("ready")) == ("(ready)",)


def test_display_controls_respect_narrow_and_short_constraints() -> None:
    controls = [
        Badge("very-long-badge"),
        StatusPill("very-long-status"),
        ProgressBar(value=4, total=10, label="Very long progress", width=10),
        KeyValueList([("Very long key", "Very long value")]),
    ]

    for control in controls:
        lines = render_lines(control, width=4, height=1)
        assert len(lines) <= 1
        assert_widths_within(lines, 4)


def test_progress_bar_renders_ratio_clamping_percent_and_theme_segments() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.progress.fill": {"color": "green"},
            "widget.progress.track": {"color": "bright_black"},
            "widget.progress.label": {"bold": True},
        }
    )

    progress = ProgressBar(value=4, total=10, label="Indexing", width=10, theme=theme)

    raw = render_lines(progress, width=40)[0]

    assert strip_control_sequences(raw) == "Indexing [####------] 40%"
    assert "\x1b[32m####\x1b[39m" in raw
    assert "\x1b[90m------\x1b[39m" in raw

    assert plain_lines(ProgressBar(value=120, total=100, width=5), width=20) == ("[#####] 100%",)
    assert plain_lines(ProgressBar(value=-1, total=100, width=5), width=20) == ("[-----] 0%",)
    assert plain_lines(ProgressBar(value=1, total=0, width=5), width=20) == ("[-----] 0%",)


def test_progress_bar_can_hide_percent_and_still_fit() -> None:
    progress = ProgressBar(value=1, total=4, label="Build", width=8, show_percent=False)

    assert plain_lines(progress, width=20) == ("Build [##------]",)
    assert_widths_within(render_lines(progress, width=6), 6)


def test_key_value_list_renders_tuples_items_descriptions_and_themes() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.keyValue.key": {"color": "cyan"},
            "widget.keyValue.value": {"color": "white"},
        }
    )
    details = KeyValueList(
        [
            ("Model", "Kimi"),
            KeyValueItem("Mode", "safe", description="current"),
        ],
        theme=theme,
    )

    raw = render_lines(details, width=40, height=4)

    assert raw[0].startswith("\x1b[36mModel")
    assert tuple(strip_control_sequences(line) for line in raw) == (
        "Model: Kimi",
        "Mode : safe  current",
    )


def test_key_value_list_honors_key_width_height_and_truncation() -> None:
    details = KeyValueList(
        [
            ("LongKey", "LongValue"),
            ("Other", "Second"),
        ],
        key_width=3,
    )

    lines = plain_lines(details, width=10, height=1)

    assert lines == ("Lon: Long",)
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py -q
```

Expected: FAIL during import with missing `Badge`, `KeyValueItem`, `KeyValueList`, `ProgressBar`, or `StatusPill`.

- [ ] **Step 3: Do not commit red tests alone**

Continue to Task 2 and commit once display controls are green.

## Task 2: Implement Display Controls And Public Exports

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/display.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_small_controls.py`

- [ ] **Step 1: Implement display widget module**

Create `src/loushang/tui/ui_parts/widgets/display.py`.

Implementation requirements:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width, visible_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import style_text

BadgeKind = Literal["default", "info", "success", "warning", "danger"]
StatusKind = Literal["neutral", "info", "success", "warning", "danger"]


@dataclass(slots=True)
class Badge:
    label: str
    kind: BadgeKind = "default"
    theme: ThemeResolver | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        rendered = truncate_to_width(f"[{self.label}]", max_width=target_width, ellipsis="")
        rendered = style_text(rendered, self.theme, f"widget.badge.{self.kind}")
        return RenderResult.from_lines([RenderLine(rendered)][: constraints.max_height], constraints=constraints)


@dataclass(slots=True)
class StatusPill:
    label: str
    status: StatusKind = "neutral"
    theme: ThemeResolver | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        rendered = truncate_to_width(f"({self.label})", max_width=target_width, ellipsis="")
        rendered = style_text(rendered, self.theme, f"widget.status.{self.status}")
        return RenderResult.from_lines([RenderLine(rendered)][: constraints.max_height], constraints=constraints)


@dataclass(slots=True)
class ProgressBar:
    value: float
    total: float = 100
    label: str = ""
    width: int | None = None
    show_percent: bool = True
    theme: ThemeResolver | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        line = _progress_line(self, target_width)
        return RenderResult.from_lines([RenderLine(line)][: constraints.max_height], constraints=constraints)


@dataclass(frozen=True, slots=True)
class KeyValueItem:
    key: str
    value: object
    description: str = ""


@dataclass(slots=True)
class KeyValueList:
    items: Sequence[KeyValueItem | tuple[str, object]]
    separator: str = ": "
    key_width: int | None = None
    theme: ThemeResolver | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        normalized = [_normalize_item(item) for item in self.items]
        key_width = _key_width(normalized, self.key_width, target_width)
        lines: list[RenderLine] = []
        for item in normalized:
            if len(lines) >= constraints.max_height:
                break
            lines.append(RenderLine(_key_value_line(item, key_width, self.separator, target_width, self.theme)))
        return RenderResult.from_lines(lines, constraints=constraints)
```

Add private helpers in the same module:

```python
def _ratio(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return min(1.0, max(0.0, value / total))


def _percent_text(ratio: float) -> str:
    return f"{round(ratio * 100):.0f}%"


def _progress_line(progress: ProgressBar, target_width: int) -> str:
    ratio = _ratio(progress.value, progress.total)
    percent = _percent_text(ratio) if progress.show_percent else ""
    label = truncate_to_width(progress.label, max_width=target_width, ellipsis="").strip()
    prefix = f"{label} " if label else ""
    suffix = f" {percent}" if percent else ""
    available = max(1, target_width - visible_width(prefix) - visible_width(suffix) - 2)
    if progress.width is not None:
        available = max(1, min(progress.width, available))
    if available <= 0:
        available = 1
    while prefix and visible_width(prefix) + available + 2 + visible_width(suffix) > target_width:
        label_width = max(0, visible_width(prefix) - 2)
        label = truncate_to_width(label.rstrip(), max_width=label_width, ellipsis="")
        prefix = f"{label} " if label else ""
    while suffix and visible_width(prefix) + available + 2 + visible_width(suffix) > target_width:
        suffix = ""
    while available > 1 and visible_width(prefix) + available + 2 + visible_width(suffix) > target_width:
        available -= 1
    filled = round(ratio * available)
    fill = "#" * filled
    track = "-" * max(0, available - filled)
    styled_fill = style_text(fill, progress.theme, "widget.progress.fill")
    styled_track = style_text(track, progress.theme, "widget.progress.track")
    bar = f"[{styled_fill}{styled_track}]"
    line = f"{prefix}{bar}{suffix}"
    line = style_text(line, progress.theme, "widget.progress.label") if prefix or suffix else line
    return truncate_to_width(line, max_width=target_width, ellipsis="")


def _normalize_item(item: KeyValueItem | tuple[str, object]) -> KeyValueItem:
    if isinstance(item, KeyValueItem):
        return item
    key, value = item
    return KeyValueItem(str(key), value)


def _key_width(items: Sequence[KeyValueItem], configured: int | None, target_width: int) -> int:
    if configured is not None:
        return max(0, min(configured, target_width))
    if not items:
        return 0
    longest = max(visible_width(item.key) for item in items)
    return max(0, min(longest, max(1, target_width // 2)))


def _key_value_line(
    item: KeyValueItem,
    key_width: int,
    separator: str,
    target_width: int,
    theme: ThemeResolver | None,
) -> str:
    key = truncate_to_width(item.key, max_width=key_width, ellipsis="")
    key = key + (" " * max(0, key_width - visible_width(key)))
    rendered_key = style_text(key, theme, "widget.keyValue.key")
    prefix = f"{rendered_key}{separator}"
    remaining = max(0, target_width - visible_width(prefix))
    value_text = str(item.value)
    if item.description and remaining > visible_width(value_text) + 2:
        value_text = f"{value_text}  {item.description}"
    value = truncate_to_width(value_text, max_width=remaining, ellipsis="")
    rendered_value = style_text(value, theme, "widget.keyValue.value")
    return truncate_to_width(f"{prefix}{rendered_value}", max_width=target_width, ellipsis="")
```

If the exact code above needs small adjustments for existing helper behavior,
preserve the tested public output and contracts.

- [ ] **Step 2: Export display widgets from `widgets/__init__.py`**

Add imports:

```python
from .display import Badge as Badge
from .display import BadgeKind as BadgeKind
from .display import KeyValueItem as KeyValueItem
from .display import KeyValueList as KeyValueList
from .display import ProgressBar as ProgressBar
from .display import StatusKind as StatusKind
from .display import StatusPill as StatusPill
```

Add all names to `__all__`.

- [ ] **Step 3: Export display widgets from `ui_parts/__init__.py`**

Add imports from `.widgets` and add these names to `__all__`:

```python
Badge
BadgeKind
KeyValueItem
KeyValueList
ProgressBar
StatusKind
StatusPill
```

- [ ] **Step 4: Export display widgets from top-level `loushang.tui`**

Add the same imports from `loushang.tui.ui_parts` and add names to `__all__`.

- [ ] **Step 5: Run display tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py -q
```

Expected: PASS for the display-control tests. Toolbar imports and behavior tests are added in Task 3.

- [ ] **Step 6: Run P0A widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/tui/test_widgets_small_controls.py src/loushang/tui/ui_parts/widgets/display.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
git commit -m "test(tui): add small display widgets"
```

## Task 3: Add Toolbar Red Tests

**Files:**
- Modify: `tests/tui/test_widgets_small_controls.py`
- Test: `tests/tui/test_widgets_small_controls.py`

- [ ] **Step 1: Append toolbar behavior tests**

Add imports to `tests/tui/test_widgets_small_controls.py`:

```python
from loushang.tui import InputEvent, Toolbar, ToolbarAction
```

Append:

```python
def test_toolbar_focus_navigation_and_activation_callback_results() -> None:
    calls: list[str] = []
    toolbar = Toolbar(
        [
            ToolbarAction("Save", on_press=lambda: calls.append("save")),
            ToolbarAction("Delete", disabled=True, value="delete"),
            ToolbarAction("Cancel", value="cancel"),
            ToolbarAction("Preview", on_press=lambda: "preview"),
        ]
    )

    toolbar.focus()

    assert plain_lines(toolbar, width=60) == ("> [Save]  [Delete]  [Cancel]  [Preview]",)
    assert toolbar.handle_input(InputEvent(kind="key", key="right")) is True
    assert toolbar.active_value == "cancel"
    assert plain_lines(toolbar, width=60) == ("[Save]  [Delete]  > [Cancel]  [Preview]",)
    assert toolbar.handle_input(InputEvent(kind="key", key="enter")) == "cancel"
    assert toolbar.handle_input(InputEvent(kind="key", key="right")) is True
    assert toolbar.active_value == "Preview"
    assert toolbar.handle_input(InputEvent(kind="key", key="enter")) == "preview"
    assert toolbar.handle_input(InputEvent(kind="key", key="right")) is True
    assert toolbar.active_value == "Save"
    assert toolbar.handle_input(InputEvent(kind="text", text=" ")) is True
    assert toolbar.handle_input(InputEvent(kind="key", key="space")) is True
    toolbar.blur()
    assert plain_lines(toolbar, width=60) == ("[Save]  [Delete]  [Cancel]  [Preview]",)
    assert calls == ["save", "save"]


def test_toolbar_wrap_false_boundaries_empty_and_all_disabled_semantics() -> None:
    toolbar = Toolbar([ToolbarAction("One"), ToolbarAction("Two")], wrap=False)
    toolbar.focus()

    assert toolbar.handle_input(InputEvent(kind="key", key="left")) is False
    assert toolbar.handle_input(InputEvent(kind="key", key="end")) is True
    assert toolbar.active_value == "Two"
    assert toolbar.handle_input(InputEvent(kind="key", key="right")) is False
    assert toolbar.handle_input(InputEvent(kind="key", key="end")) is False

    assert Toolbar([]).render(RenderConstraints(width=20, max_height=1)).lines == ()
    assert Toolbar([]).handle_input(InputEvent(kind="key", key="right")) is None
    disabled = Toolbar([ToolbarAction("No", disabled=True)])
    disabled.focus()
    assert disabled.handle_input(InputEvent(kind="key", key="right")) is None
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None


def test_toolbar_applies_theme_tokens_and_respects_width() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.toolbar.action": {"color": "white"},
            "widget.toolbar.focus": {"bold": True, "color": "cyan"},
            "widget.toolbar.disabled": {"dim": True},
        }
    )
    toolbar = Toolbar(
        [ToolbarAction("Save"), ToolbarAction("Delete", disabled=True)],
        theme=theme,
    )
    toolbar.focus()

    raw = render_lines(toolbar, width=40)[0]

    assert raw.startswith("\x1b[1;36m> [Save]")
    assert "\x1b[2m[Delete]" in raw
    assert strip_control_sequences(raw) == "> [Save]  [Delete]"
    assert_widths_within(render_lines(toolbar, width=5), 5)
```

- [ ] **Step 2: Run toolbar tests to verify red**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py -q
```

Expected: FAIL because `Toolbar` and `ToolbarAction` are missing or lack behavior.

- [ ] **Step 3: Do not commit red tests alone**

Continue to Task 4 and commit once toolbar is green.

## Task 4: Implement Toolbar And Public Exports

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/toolbar.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_small_controls.py`

- [ ] **Step 1: Implement toolbar module**

Create `src/loushang/tui/ui_parts/widgets/toolbar.py`.

Implementation requirements:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import callback_result, is_activation_event, style_text


@dataclass(frozen=True, slots=True)
class ToolbarAction:
    label: str
    on_press: Callable[[], object] | None = None
    disabled: bool = False
    icon: str = ""
    value: str = ""

    @property
    def display_label(self) -> str:
        return self.label if not self.icon else f"{self.icon} {self.label}".strip()


@dataclass(slots=True)
class Toolbar:
    actions: Sequence[ToolbarAction]
    active_index: int = 0
    wrap: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False
    _active_index: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.actions = tuple(self.actions)
        self._active_index = self._nearest_enabled_index(self.active_index)

    @property
    def active_value(self) -> str:
        action = self._active_action()
        if action is None:
            return ""
        return action.value or action.label

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key":
            key = getattr(event, "key", "")
            if key == "left":
                return self._move_active(-1)
            if key == "right":
                return self._move_active(1)
            if key == "home":
                return self._jump_active(first=True)
            if key == "end":
                return self._jump_active(first=False)
        if is_activation_event(event):
            return self._activate()
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if not self.actions:
            return RenderResult.from_lines([], constraints=constraints)
        target_width = autowrap_safe_width(constraints.width)
        parts = []
        for index, action in enumerate(self.actions):
            prefix = "> " if self.focused and index == self._active_index and not action.disabled else ""
            text = f"{prefix}[{action.display_label}]"
            token = (
                "widget.toolbar.disabled"
                if action.disabled
                else "widget.toolbar.focus"
                if self.focused and index == self._active_index
                else "widget.toolbar.action"
            )
            parts.append(style_text(text, self.theme, token))
        line = truncate_to_width("  ".join(parts), max_width=target_width, ellipsis="")
        return RenderResult.from_lines([RenderLine(line)][: constraints.max_height], constraints=constraints)
```

Add private methods:

```python
    def _enabled_indices(self) -> tuple[int, ...]:
        return tuple(index for index, action in enumerate(self.actions) if not action.disabled)

    def _nearest_enabled_index(self, preferred: int) -> int:
        enabled = self._enabled_indices()
        if not enabled:
            return 0
        preferred = max(0, min(preferred, len(self.actions) - 1))
        if preferred in enabled:
            return preferred
        for index in enabled:
            if index > preferred:
                return index
        return enabled[0]

    def _active_action(self) -> ToolbarAction | None:
        if not self.actions:
            return None
        if self._active_index < 0 or self._active_index >= len(self.actions):
            return None
        action = self.actions[self._active_index]
        return None if action.disabled else action

    def _move_active(self, delta: int) -> bool | None:
        enabled = self._enabled_indices()
        if not enabled:
            return None
        if self._active_index not in enabled:
            self._active_index = enabled[0]
            return True
        position = enabled.index(self._active_index)
        next_position = position + delta
        if self.wrap:
            next_position %= len(enabled)
        elif next_position < 0 or next_position >= len(enabled):
            return False
        next_index = enabled[next_position]
        if next_index == self._active_index:
            return False
        self._active_index = next_index
        return True

    def _jump_active(self, *, first: bool) -> bool | None:
        enabled = self._enabled_indices()
        if not enabled:
            return None
        target = enabled[0] if first else enabled[-1]
        if target == self._active_index:
            return False
        self._active_index = target
        return True

    def _activate(self) -> object:
        action = self._active_action()
        if action is None:
            return None
        if action.on_press is not None:
            return callback_result(action.on_press())
        if action.value:
            return action.value
        return True
```

- [ ] **Step 2: Export toolbar widgets from `widgets/__init__.py`**

Add imports:

```python
from .toolbar import Toolbar as Toolbar
from .toolbar import ToolbarAction as ToolbarAction
```

Add both names to `__all__`.

- [ ] **Step 3: Export toolbar widgets from `ui_parts/__init__.py`**

Add imports from `.widgets` and add names to `__all__`.

- [ ] **Step 4: Export toolbar widgets from top-level `loushang.tui`**

Add imports from `loushang.tui.ui_parts` and add names to `__all__`.

- [ ] **Step 5: Run focused small-control tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py -q
```

Expected: PASS.

- [ ] **Step 6: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/tui/test_widgets_small_controls.py src/loushang/tui/ui_parts/widgets/toolbar.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
git commit -m "test(tui): add toolbar widget"
```

## Task 5: Add Example And Reference Docs

**Files:**
- Create: `examples/tui/44_widgets_small_controls.py`
- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`
- Test: `tests/tui/test_widgets_small_controls.py`

- [ ] **Step 1: Add example import test**

Append to `tests/tui/test_widgets_small_controls.py`:

```python
def test_widgets_small_controls_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/44_widgets_small_controls.py", run_name="__test__")

    assert "build_app" in namespace
```

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py::test_widgets_small_controls_example_imports -q
```

Expected: FAIL because the example file does not exist.

- [ ] **Step 2: Create example file**

Create `examples/tui/44_widgets_small_controls.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    Badge,
    FocusableMixin,
    InputEvent,
    KeyValueItem,
    KeyValueList,
    ProgressBar,
    RenderConstraints,
    RenderLine,
    RenderResult,
    StatusPill,
    Toolbar,
    ToolbarAction,
    Tui,
    TuiInputResult,
    TuiRunner,
)


@dataclass(slots=True)
class SmallControlsApp(FocusableMixin):
    progress: int = 42
    message: str = "Ready"
    toolbar: Toolbar = field(default_factory=lambda: Toolbar(_actions()))

    def __post_init__(self) -> None:
        super().__init__()
        self.toolbar.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        details = KeyValueList(
            [
                KeyValueItem("Model", "Kimi"),
                KeyValueItem("Mode", "safe", description="current"),
                KeyValueItem("Queue", "3 pending"),
            ]
        )
        rows = [
            RenderLine(" ".join(plain for plain in _header(constraints.width))),
            RenderLine(""),
            *ProgressBar(value=self.progress, total=100, label="Indexing", width=12).render(
                RenderConstraints(width=constraints.width, max_height=1)
            ).lines,
            RenderLine(""),
            *details.render(RenderConstraints(width=constraints.width, max_height=4)).lines,
            RenderLine(""),
            *self.toolbar.render(RenderConstraints(width=constraints.width, max_height=1)).lines,
            RenderLine(self.message[: constraints.width]),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        result = self.toolbar.handle_input(event)
        if result == "refresh":
            self.progress = min(100, self.progress + 10)
            self.message = "Refreshed"
            return True
        if result == "cancel":
            self.message = "Cancelled"
            return True
        return result


def build_app() -> Tui:
    tui = Tui()
    app = SmallControlsApp()
    tui.add_child(app)
    tui.set_focus(app)
    return tui


async def main() -> int:
    tui = build_app()

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if event.kind == "text" and "q" in event.text.lower():
            return context.stop(0)
        context.tui.handle_input(event)
        return TuiInputResult()

    return await TuiRunner(tui).run(on_input=on_input)


def _header(width: int) -> tuple[str, ...]:
    constraints = RenderConstraints(width=max(1, width // 3), max_height=1)
    badge = Badge("beta", kind="info").render(constraints).lines[0].text
    status = StatusPill("ready", status="success").render(constraints).lines[0].text
    return "Small Controls", badge, status


def _actions() -> list[ToolbarAction]:
    return [
        ToolbarAction("Refresh", value="refresh"),
        ToolbarAction("Cancel", value="cancel"),
    ]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

If Ruff objects to the `_header()` layout, keep the example simple and deterministic; do not add a complex layout helper.

- [ ] **Step 3: Update English docs**

In `docs/en/reference/tui-widgets.md`:

- Add P0B rows for `Badge`, `StatusPill`, `ProgressBar`, `KeyValueList`, and `Toolbar`.
- Add a "Small Controls" section with a short code snippet.
- Add the P0B theme tokens from the spec to the theme token table.
- Add the new example link.
- Remove `Toolbar`, `ProgressBar`, `Badge`, `StatusPill`, and `KeyValueList`
  from the existing "Planned Catalog" text so docs do not describe implemented
  controls as planned.

- [ ] **Step 4: Update Chinese docs**

Mirror the English docs in `docs/zh-CN/reference/tui-widgets.md`.
Also remove the implemented P0B controls from the Chinese planned-catalog text.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/tui/test_widgets_small_controls.py examples/tui/44_widgets_small_controls.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md
git commit -m "docs(tui): document small controls widgets"
```

## Task 6: Full Verification

**Files:**
- Modify only if verification finds issues.

- [ ] **Step 1: Run focused P0B tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
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
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/44_widgets_small_controls.py docs
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

- `Badge`, `StatusPill`, `ProgressBar`, `KeyValueItem`, `KeyValueList`, `ToolbarAction`, and `Toolbar` are public stable exports.
- P0B controls obey width and height constraints under focused tests.
- Theme tokens apply without visible-width growth.
- `Toolbar` covers navigation, activation, disabled, empty, all-disabled, and boundary semantics.
- Example and docs are updated.
- Full TUI tests and Ruff pass.
