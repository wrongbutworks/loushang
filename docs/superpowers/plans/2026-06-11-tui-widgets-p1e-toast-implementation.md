# TUI Widgets P1E Toast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure renderable `Toast` / `ToastStack` widget for deterministic non-blocking notifications without changing overlay, focus, timer, or scheduler behavior.

**Architecture:** Implement Toast as one focused widget module under `src/loushang/tui/ui_parts/widgets/toast.py`. `Toast` is an immutable notification data item; `ToastStack` owns local tuple-backed queue state, deterministic value/timestamp normalization, explicit dismissal/pruning operations, and one-line rendering. The widget remains terminal-pure and can be embedded in layouts or manually opened through existing `SurfaceHost` APIs by callers.

**Tech Stack:** Python 3.11+, dataclasses with slots, `Literal`, existing `RenderResult`, `cell_width` helpers, `ThemeResolver`, widget `style_text`, pytest, Ruff.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-11-tui-widgets-p1e-toast-design.md`
- Existing patterns:
  - `src/loushang/tui/ui_parts/widgets/display.py`
  - `src/loushang/tui/ui_parts/widgets/tree.py`
  - `src/loushang/tui/ui_parts/widgets/_utils.py`
  - `tests/tui/test_widgets_light_controls.py`
  - `tests/tui/test_widgets_small_controls.py`
  - `tests/tui/test_widgets_hardening.py`
  - `docs/en/reference/tui-widgets.md`
  - `docs/zh-CN/reference/tui-widgets.md`

## File Structure

Create:

- `src/loushang/tui/ui_parts/widgets/toast.py`
  - Owns public `ToastKind`, `Toast`, and `ToastStack`.
  - Owns private `_NowMs`, `_monotonic_ms`, validation, normalization, expiration, ordering, dismissal, pruning, and rendering helpers.
- `tests/tui/test_widgets_toast.py`
  - Focused tests for exports, construction, normalization, duplicate handling, expiration, ordering, dismissal, rendering, theme tokens, constraints, and example importability.
- `examples/tui/50_widgets_toast.py`
  - Small runnable app showing a `ToastStack` embedded in a TUI layout.

Modify:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export `Toast`, `ToastKind`, and `ToastStack`.
- `src/loushang/tui/ui_parts/__init__.py`
  - Re-export `Toast`, `ToastKind`, and `ToastStack`.
- `src/loushang/tui/__init__.py`
  - Re-export `Toast`, `ToastKind`, and `ToastStack`.
- `docs/en/reference/tui-widgets.md`
  - Add P1E Toast Controls section, theme tokens, example link, and remove `Toast` from planned catalog.
- `docs/zh-CN/reference/tui-widgets.md`
  - Mirror the English reference update.

Do not modify:

- `SurfaceHost`, `Tui`, `InputRouter`, `RenderLoop`, scheduler, global keybindings, or existing widgets.

---

### Task 1: Add Failing Export And Construction Tests

**Files:**
- Create: `tests/tui/test_widgets_toast.py`

- [ ] **Step 1: Create focused test file with helpers**

```python
from __future__ import annotations

import runpy
from typing import Any

import pytest

from loushang.tui import (
    RenderConstraints,
    ThemeResolver,
    Toast,
    ToastKind,
    ToastStack,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import Toast as UiToast
from loushang.tui.ui_parts import ToastKind as UiToastKind
from loushang.tui.ui_parts import ToastStack as UiToastStack
from loushang.tui.ui_parts.widgets import Toast as WidgetToast
from loushang.tui.ui_parts.widgets import ToastKind as WidgetToastKind
from loushang.tui.ui_parts.widgets import ToastStack as WidgetToastStack


class Clock:
    def __init__(self, *values: int) -> None:
        self.values = list(values) or [0]
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        if len(self.values) == 1:
            return self.values[0]
        return self.values.pop(0)

    def set(self, value: int) -> None:
        self.values = [value]


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)
```

- [ ] **Step 2: Add failing public export tests**

```python
def test_toast_widgets_are_reexported_from_public_modules() -> None:
    assert Toast is UiToast
    assert Toast is WidgetToast
    assert ToastStack is UiToastStack
    assert ToastStack is WidgetToastStack
    assert ToastKind is UiToastKind
    assert ToastKind is WidgetToastKind
    assert Toast("Saved").message == "Saved"
```

- [ ] **Step 3: Add failing construction and normalization tests**

```python
def test_toast_stack_normalizes_generated_values_and_timestamps() -> None:
    clock = Clock(100)
    stack = ToastStack(
        (
            Toast("Saved"),
            Toast("Synced", value="sync", created_at_ms=50),
        ),
        now_ms=clock,
    )

    assert stack.all_toasts() == (
        Toast("Saved", value="toast-1", created_at_ms=100),
        Toast("Synced", value="sync", created_at_ms=50),
    )
    assert clock.calls == 1

    assert stack.push("Queued", kind="success", title="Job") == "toast-2"
    assert stack.all_toasts()[-1] == Toast(
        "Queued",
        title="Job",
        kind="success",
        value="toast-2",
        created_at_ms=100,
    )


def test_toast_stack_rejects_duplicate_values_invalid_kind_and_negative_duration() -> None:
    with pytest.raises(ValueError):
        ToastStack((Toast("One", value="dup"), Toast("Two", value="dup")))

    with pytest.raises(ValueError):
        ToastStack((Toast("Bad", kind="unknown"),))  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        ToastStack((Toast("Bad", duration_ms=-1),))


def test_toast_stack_push_applies_toast_overrides_and_rejects_message_override_for_strings() -> None:
    stack = ToastStack(now_ms=Clock(5))

    value = stack.push(Toast("Saved", value="save"), kind="success", title="Config")

    assert value == "save"
    assert stack.all_toasts() == (
        Toast("Saved", title="Config", kind="success", value="save", created_at_ms=5),
    )

    with pytest.raises(TypeError):
        stack.push("Saved", message="Other")  # type: ignore[call-arg]
```

- [ ] **Step 4: Run focused tests to verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py -q
```

Expected: FAIL during import because `Toast`, `ToastKind`, and `ToastStack` do not exist.

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/tui/test_widgets_toast.py
git commit -m "test(tui): add toast widget api tests"
```

---

### Task 2: Implement Toast Skeleton, Normalization, And Public Exports

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/toast.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_toast.py`

- [ ] **Step 1: Create `toast.py` public data types and helpers**

```python
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import style_text

ToastKind = Literal["info", "success", "warning", "danger"]
_NowMs = Callable[[], int]
_VALID_KINDS = frozenset({"info", "success", "warning", "danger"})

__all__ = ["Toast", "ToastKind", "ToastStack"]


def _monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


@dataclass(frozen=True, slots=True)
class Toast:
    message: str
    title: str = ""
    kind: ToastKind = "info"
    value: str = ""
    duration_ms: int | None = 4000
    created_at_ms: int | None = None
    dismissible: bool = True
```

- [ ] **Step 2: Add `ToastStack` fields and normalization**

```python
@dataclass(slots=True)
class ToastStack:
    toasts: Sequence[Toast] = ()
    max_visible: int = 3
    newest_on_top: bool = True
    empty_height: int = 0
    theme: ThemeResolver | None = None
    now_ms: _NowMs = _monotonic_ms
    _next_generated_index: int = field(default=1, init=False, repr=False)

    def __post_init__(self) -> None:
        self.empty_height = max(0, self.empty_height)
        self.toasts = self._normalize_batch(tuple(self.toasts))

    def _normalize_batch(self, toasts: tuple[Toast, ...]) -> tuple[Toast, ...]:
        now_ms = self.now_ms() if any(toast.created_at_ms is None for toast in toasts) else None
        existing: set[str] = set()
        normalized: list[Toast] = []
        for toast in toasts:
            normalized.append(self._normalize_toast(toast, now_ms=now_ms, existing_values=existing))
        return tuple(normalized)

    def _normalize_toast(self, toast: Toast, *, now_ms: int | None, existing_values: set[str]) -> Toast:
        self._validate_toast(toast)
        value = toast.value or self._next_generated_value(existing_values)
        if value in existing_values:
            raise ValueError(f"duplicate Toast value: {value!r}")
        existing_values.add(value)
        if toast.created_at_ms is None:
            if now_ms is None:
                raise AssertionError("now_ms is required for Toast without created_at_ms")
            created_at_ms = now_ms
        else:
            created_at_ms = toast.created_at_ms
        return replace(toast, value=value, created_at_ms=created_at_ms)

    def _next_generated_value(self, existing_values: set[str]) -> str:
        stored_values = {toast.value for toast in self.toasts}
        while True:
            value = f"toast-{self._next_generated_index}"
            self._next_generated_index += 1
            if value not in existing_values and value not in stored_values:
                return value

    def _validate_toast(self, toast: Toast) -> None:
        if toast.kind not in _VALID_KINDS:
            raise ValueError(f"unknown Toast kind: {toast.kind!r}")
        if toast.duration_ms is not None and toast.duration_ms < 0:
            raise ValueError("Toast duration_ms must be non-negative or None")
```

- [ ] **Step 3: Add basic public methods and placeholder render**

```python
    def all_toasts(self) -> tuple[Toast, ...]:
        return tuple(self.toasts)

    def push(self, toast: Toast | str, **overrides: object) -> str:
        if isinstance(toast, str):
            if "message" in overrides:
                raise TypeError("Toast message cannot be overridden when pushing a string")
            candidate = Toast(toast, **overrides)
        elif isinstance(toast, Toast):
            candidate = replace(toast, **overrides) if overrides else toast
        else:
            raise TypeError("push() expects Toast or str")
        existing = {item.value for item in self.toasts}
        now_ms = self.now_ms() if candidate.created_at_ms is None else None
        normalized = self._normalize_toast(candidate, now_ms=now_ms, existing_values=existing)
        self.toasts = (*tuple(self.toasts), normalized)
        return normalized.value

    def visible_toasts(self) -> tuple[Toast, ...]:
        return tuple(self.toasts)

    def prune_expired(self) -> int:
        return 0

    def dismiss(self, value: str) -> bool:
        for toast in self.toasts:
            if toast.value == value and toast.dismissible:
                self.toasts = tuple(item for item in self.toasts if item.value != value)
                return True
            if toast.value == value:
                return False
        return False

    def dismiss_oldest(self) -> bool:
        return False

    def clear(self) -> None:
        self.toasts = ()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([], constraints=constraints)
```

- [ ] **Step 4: Add public exports**

In `src/loushang/tui/ui_parts/widgets/__init__.py`:

```python
from .toast import Toast as Toast
from .toast import ToastKind as ToastKind
from .toast import ToastStack as ToastStack
```

Add `"Toast"`, `"ToastKind"`, and `"ToastStack"` to `widgets.__all__`.

In `src/loushang/tui/ui_parts/__init__.py`, re-export the same names from
`.widgets` and add them to `ui_parts.__all__`.

In `src/loushang/tui/__init__.py`, add the same names to the existing
`from loushang.tui.ui_parts import (...)` block and top-level `__all__`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py -q
```

Expected: Task 1 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/toast.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
git commit -m "feat(tui): add toast widget skeleton"
```

---

### Task 3: Add Failing Expiration, Ordering, And Dismissal Tests

**Files:**
- Modify: `tests/tui/test_widgets_toast.py`

- [ ] **Step 1: Add expiration visibility tests**

```python
def test_toast_visible_toasts_filters_expired_without_mutating() -> None:
    clock = Clock(100)
    stack = ToastStack(
        (
            Toast("Old", value="old", created_at_ms=0, duration_ms=100),
            Toast("Pinned", value="pin", created_at_ms=0, duration_ms=None),
            Toast("Fresh", value="fresh", created_at_ms=50, duration_ms=100),
        ),
        newest_on_top=False,
        now_ms=clock,
    )

    assert stack.visible_toasts() == (
        Toast("Pinned", value="pin", duration_ms=None, created_at_ms=0),
        Toast("Fresh", value="fresh", created_at_ms=50, duration_ms=100),
    )
    assert tuple(toast.value for toast in stack.all_toasts()) == ("old", "pin", "fresh")


def test_toast_expiration_boundary_is_expired() -> None:
    stack = ToastStack((Toast("Boundary", value="b", created_at_ms=10, duration_ms=90),), now_ms=Clock(100))

    assert stack.visible_toasts() == ()
```

- [ ] **Step 2: Add prune and single-sample tests**

```python
def test_toast_prune_expired_mutates_and_returns_count() -> None:
    stack = ToastStack(
        (
            Toast("Old", value="old", created_at_ms=0, duration_ms=10),
            Toast("Fresh", value="fresh", created_at_ms=50, duration_ms=100),
        ),
        now_ms=Clock(100),
    )

    assert stack.prune_expired() == 1
    assert stack.all_toasts() == (Toast("Fresh", value="fresh", created_at_ms=50, duration_ms=100),)


def test_toast_expiration_operations_sample_now_once() -> None:
    visible_clock = Clock(100, 101, 102)
    stack = ToastStack((Toast("A", value="a", created_at_ms=0, duration_ms=101),), now_ms=visible_clock)

    assert tuple(toast.value for toast in stack.visible_toasts()) == ("a",)
    assert visible_clock.calls == 1

    prune_clock = Clock(100, 101, 102)
    stack = ToastStack((Toast("A", value="a", created_at_ms=0, duration_ms=101),), now_ms=prune_clock)
    assert stack.prune_expired() == 0
    assert prune_clock.calls == 1
```

- [ ] **Step 3: Add ordering and dismissal tests**

```python
def test_toast_ordering_and_max_visible() -> None:
    toasts = tuple(Toast(str(index), value=str(index), created_at_ms=index, duration_ms=None) for index in range(5))

    newest = ToastStack(toasts, max_visible=3, newest_on_top=True, now_ms=Clock(10))
    oldest = ToastStack(toasts, max_visible=3, newest_on_top=False, now_ms=Clock(10))

    assert tuple(toast.value for toast in newest.visible_toasts()) == ("4", "3", "2")
    assert tuple(toast.value for toast in oldest.visible_toasts()) == ("0", "1", "2")
    assert ToastStack(toasts, max_visible=0).visible_toasts() == ()


def test_toast_dismiss_clear_and_non_dismissible_behavior() -> None:
    stack = ToastStack(
        (
            Toast("A", value="a"),
            Toast("B", value="b", dismissible=False),
            Toast("C", value="c"),
        )
    )

    assert stack.dismiss("missing") is False
    assert stack.dismiss("b") is False
    assert tuple(toast.value for toast in stack.all_toasts()) == ("a", "b", "c")
    assert stack.dismiss("a") is True
    assert tuple(toast.value for toast in stack.all_toasts()) == ("b", "c")
    stack.clear()
    assert stack.all_toasts() == ()


def test_toast_dismiss_oldest_skips_expired_and_non_dismissible_without_pruning() -> None:
    stack = ToastStack(
        (
            Toast("Expired", value="expired", created_at_ms=0, duration_ms=10),
            Toast("Pinned", value="pinned", dismissible=False, created_at_ms=90, duration_ms=100),
            Toast("Fresh", value="fresh", created_at_ms=90, duration_ms=100),
        ),
        now_ms=Clock(100),
    )

    assert stack.dismiss_oldest() is True
    assert tuple(toast.value for toast in stack.all_toasts()) == ("expired", "pinned")
    assert stack.dismiss_oldest() is False
    assert tuple(toast.value for toast in stack.all_toasts()) == ("expired", "pinned")
```

- [ ] **Step 4: Add dismiss-oldest single-sample test**

```python
def test_toast_dismiss_oldest_samples_now_once() -> None:
    clock = Clock(100, 101, 102)
    stack = ToastStack((Toast("A", value="a", created_at_ms=0, duration_ms=101),), now_ms=clock)

    assert stack.dismiss_oldest() is True
    assert clock.calls == 1


def test_toast_dismiss_oldest_only_considers_visible_window() -> None:
    toasts = tuple(Toast(str(index), value=str(index), created_at_ms=index, duration_ms=None) for index in range(5))

    hidden_oldest = ToastStack(toasts, max_visible=2, newest_on_top=True)
    assert tuple(toast.value for toast in hidden_oldest.visible_toasts()) == ("4", "3")
    assert hidden_oldest.dismiss_oldest() is True
    assert tuple(toast.value for toast in hidden_oldest.all_toasts()) == ("0", "1", "2", "4")

    no_visible = ToastStack(toasts, max_visible=0)
    assert no_visible.dismiss_oldest() is False
    assert tuple(toast.value for toast in no_visible.all_toasts()) == ("0", "1", "2", "3", "4")
```

- [ ] **Step 5: Run focused tests to verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py -q
```

Expected: FAIL on expiration/order/dismissal behavior.

- [ ] **Step 6: Commit failing tests**

```bash
git add tests/tui/test_widgets_toast.py
git commit -m "test(tui): cover toast queue behavior"
```

---

### Task 4: Implement Expiration, Ordering, Dismissal, And Pruning

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/toast.py`
- Test: `tests/tui/test_widgets_toast.py`

- [ ] **Step 1: Add expiration and visibility helpers**

```python
    def _is_expired(self, toast: Toast, *, now_ms: int) -> bool:
        if toast.duration_ms is None:
            return False
        return now_ms - int(toast.created_at_ms or 0) >= toast.duration_ms

    def _visible_toasts_at(self, now_ms: int) -> tuple[Toast, ...]:
        if self.max_visible <= 0:
            return ()
        visible = tuple(toast for toast in self.toasts if not self._is_expired(toast, now_ms=now_ms))
        if self.newest_on_top:
            visible = tuple(reversed(visible))
        return visible[: self.max_visible]

    def visible_toasts(self) -> tuple[Toast, ...]:
        return self._visible_toasts_at(self.now_ms())
```

- [ ] **Step 2: Implement pruning and dismissal**

```python
    def prune_expired(self) -> int:
        now_ms = self.now_ms()
        kept = tuple(toast for toast in self.toasts if not self._is_expired(toast, now_ms=now_ms))
        removed = len(tuple(self.toasts)) - len(kept)
        self.toasts = kept
        return removed

    def dismiss_oldest(self) -> bool:
        now_ms = self.now_ms()
        visible_values = {toast.value for toast in self._visible_toasts_at(now_ms)}
        for toast in self.toasts:
            if toast.value not in visible_values or not toast.dismissible:
                continue
            self.toasts = tuple(item for item in self.toasts if item.value != toast.value)
            return True
        return False
```

Keep existing `dismiss(value)` semantics from Task 2; it removes a matching
dismissible toast by value even if that toast is currently expired.

- [ ] **Step 3: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py -q
```

Expected: all current toast tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/toast.py
git commit -m "feat(tui): handle toast queue semantics"
```

---

### Task 5: Add Failing Render And Theme Tests

**Files:**
- Modify: `tests/tui/test_widgets_toast.py`

- [ ] **Step 1: Add deterministic render tests**

```python
def test_toast_stack_renders_title_message_and_empty_message_rows() -> None:
    stack = ToastStack(
        (
            Toast("Saved", title="Config", kind="success", value="save", duration_ms=None),
            Toast("", title="Warning", kind="warning", value="warn", duration_ms=None),
            Toast("Plain", kind="info", value="plain", duration_ms=None),
        ),
        newest_on_top=False,
    )

    assert plain_lines(stack, width=40, height=5) == (
        "[success] Config: Saved",
        "[warning] Warning",
        "[info] Plain",
    )


def test_toast_stack_respects_width_height_and_empty_height() -> None:
    empty = ToastStack(empty_height=1)
    assert plain_lines(empty, width=10, height=3) == ("",)
    assert plain_lines(ToastStack(empty_height=2), width=10, height=1) == ("",)
    assert plain_lines(ToastStack(), width=10, height=3) == ()

    stack = ToastStack(
        (
            Toast("Very long message", kind="info", value="a", duration_ms=None),
            Toast("Second", kind="danger", value="b", duration_ms=None),
        ),
        newest_on_top=False,
    )
    lines = render_lines(stack, width=12, height=1)

    assert plain_lines(stack, width=12, height=1) == ("[info] Very",)
    assert_widths_within(lines, 12)
    assert_widths_within(render_lines(stack, width=1, height=3), 1)
```

- [ ] **Step 2: Add theme token tests**

```python
def test_toast_stack_applies_theme_tokens_and_preserves_visible_width() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.toast.success": {"color": "green"},
            "widget.toast.title": {"bold": True},
            "widget.toast.message": {"color": "white"},
        }
    )
    stack = ToastStack((Toast("Saved", title="Config", kind="success", value="save", duration_ms=None),), theme=theme)

    raw = render_lines(stack, width=40, height=2)

    assert raw[0].startswith("\x1b[32m[success]")
    assert "\x1b[1mConfig" in raw[0]
    assert "\x1b[37mSaved" in raw[0]
    assert_widths_within(raw, 40)
```

- [ ] **Step 3: Add render single-sample test**

```python
def test_toast_render_samples_now_once() -> None:
    clock = Clock(100, 101, 102)
    stack = ToastStack((Toast("A", value="a", created_at_ms=0, duration_ms=101),), now_ms=clock)

    assert plain_lines(stack, width=20, height=2) == ("[info] A",)
    assert clock.calls == 1
```

- [ ] **Step 4: Run focused tests to verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py -q
```

Expected: FAIL on rendering/theme behavior.

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/tui/test_widgets_toast.py
git commit -m "test(tui): cover toast rendering"
```

---

### Task 6: Implement Deterministic Toast Rendering

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/toast.py`
- Test: `tests/tui/test_widgets_toast.py`

- [ ] **Step 1: Add row rendering helpers**

```python
    def _toast_line(self, toast: Toast, target_width: int) -> str:
        prefix = style_text(f"[{toast.kind}]", self.theme, f"widget.toast.{toast.kind}")
        title = style_text(toast.title, self.theme, "widget.toast.title") if toast.title else ""
        message = style_text(toast.message, self.theme, "widget.toast.message") if toast.message else ""
        if title and message:
            line = f"{prefix} {title}: {message}"
        elif title:
            line = f"{prefix} {title}"
        elif message:
            line = f"{prefix} {message}"
        else:
            line = prefix
        return truncate_to_width(line, max_width=target_width, ellipsis="")
```

- [ ] **Step 2: Replace `render()`**

```python
    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        height = max(0, constraints.max_height)
        if height == 0:
            return RenderResult.from_lines([], constraints=constraints)
        visible = self._visible_toasts_at(self.now_ms())
        if not visible:
            empty_count = min(self.empty_height, height)
            return RenderResult.from_lines([RenderLine("") for _ in range(empty_count)], constraints=constraints)
        lines = [RenderLine(self._toast_line(toast, target_width)) for toast in visible[:height]]
        return RenderResult.from_lines(lines, constraints=constraints)
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py -q
```

Expected: PASS.

- [ ] **Step 4: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/toast.py
git commit -m "feat(tui): render toast stack"
```

---

### Task 7: Add Docs And Runnable Example

**Files:**
- Create: `examples/tui/50_widgets_toast.py`
- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`
- Test: `tests/tui/test_widgets_toast.py`

- [ ] **Step 1: Add failing example import test**

```python
def test_widgets_toast_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/50_widgets_toast.py", run_name="__test__")

    assert callable(namespace["build_app"])
```

- [ ] **Step 2: Run the example import test to verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py::test_widgets_toast_example_imports -q
```

Expected: FAIL because `examples/tui/50_widgets_toast.py` does not exist.

- [ ] **Step 3: Create `examples/tui/50_widgets_toast.py`**

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
    Toast,
    ToastStack,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class ToastApp(FocusableMixin):
    stack: ToastStack = field(
        default_factory=lambda: ToastStack(
            (
                Toast("Welcome", title="Loushang", kind="info", duration_ms=None),
                Toast("Changes saved", kind="success", duration_ms=None),
            ),
            newest_on_top=True,
        )
    )
    counter: int = 0

    def __post_init__(self) -> None:
        super().__init__()
        self.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        toast_result = self.stack.render(RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 3)))
        rows = [
            RenderLine(truncate_to_width("Toast Stack", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            *toast_result.lines,
            RenderLine(""),
            RenderLine(truncate_to_width("Press i/s/w/d to add, x to dismiss oldest, c to clear, q to quit.", max_width=constraints.width, ellipsis="")),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        if getattr(event, "kind", "") != "text":
            return None
        key = getattr(event, "text", "").lower()
        if key == "c":
            self.stack.clear()
            return True
        if key == "x":
            return self.stack.dismiss_oldest()
        kinds = {"i": "info", "s": "success", "w": "warning", "d": "danger"}
        kind = kinds.get(key)
        if kind is None:
            return None
        self.counter += 1
        self.stack.push(f"Toast {self.counter}", kind=kind)
        return True


def build_app() -> Tui:
    tui = Tui()
    app = ToastApp()
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


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 4: Update English docs**

In `docs/en/reference/tui-widgets.md`:

- Add `P1E Toast Controls` after P1D.
- Add `Toast` / `ToastStack` entry.
- Document queue operations and expiration semantics.
- State clearly that Toast does not open overlays automatically.
- Add theme tokens `widget.toast.info`, `widget.toast.success`,
  `widget.toast.warning`, `widget.toast.danger`, `widget.toast.title`, and
  `widget.toast.message`.
- Remove `Toast` from planned catalog, leaving `Popover`.
- Add example link.

Snippet:

```python
from loushang.tui import ToastStack

stack = ToastStack()
stack.push("Saved", kind="success", title="Config")
```

- [ ] **Step 5: Update Chinese docs**

Mirror the English content in `docs/zh-CN/reference/tui-widgets.md`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add examples/tui/50_widgets_toast.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md tests/tui/test_widgets_toast.py
git commit -m "docs(tui): document toast widget"
```

---

### Task 8: Final Verification And Cleanup

**Files:**
- Review all changed files.

- [ ] **Step 1: Run focused Toast tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_toast.py -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full TUI tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS.

- [ ] **Step 4: Run Ruff on touched surfaces**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/50_widgets_toast.py docs
```

Expected: PASS.

- [ ] **Step 5: Inspect git diff**

Run:

```bash
git diff --stat origin/main...HEAD
git diff --check
```

Expected: no whitespace errors; diff contains only spec/plan, Toast widget,
exports, tests, docs, and example.

- [ ] **Step 6: Commit any final fixes**

If verification required small fixes:

```bash
git add <fixed-files>
git commit -m "fix(tui): finalize toast widget"
```

If no fixes were needed, do not create an empty commit.

---

## Success Criteria

- `Toast`, `ToastKind`, and `ToastStack` are exported from public TUI modules.
- Toast normalization creates stable values and timestamps.
- Duplicate values, invalid kinds, and negative durations are rejected.
- `push(Toast(...), **overrides)` uses `dataclasses.replace()` semantics.
- Expiration filtering is deterministic and all expiration-sensitive operations
  sample `now_ms()` exactly once.
- `visible_toasts()` and `render()` filter expired toasts without mutating.
- `prune_expired()` is the only expiration operation that removes expired
  toasts.
- Dismissal methods have explicit return semantics and respect
  `dismissible=False`.
- `dismiss_oldest()` skips expired toasts without pruning them.
- Rendering obeys width, height, ordering, and empty-height constraints.
- Theme tokens are deterministic and covered.
- Docs and example import tests pass.
- Existing TUI tests remain green.
