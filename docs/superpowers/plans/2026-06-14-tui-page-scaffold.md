# TUI PageScaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable `PageScaffold` widget that provides page-level header/body/footer layout and focus orchestration, plus a new example 53 demonstrating it.

**Architecture:** `PageScaffold` lives in `loushang.tui.ui_parts.widgets` as a slot-based widget. It composes caller-owned `header` and `body` renderables, reserves footer height, offsets cursors through inserted chrome, and moves focus between header and body while leaving widget-specific behavior to `Tabs`, `SearchableList`, and other body widgets. The first integration is a new `examples/tui/53_widgets_page_scaffold.py`; do not migrate example 52 or coding settings.

**Tech Stack:** Python 3.11, pytest, Ruff, existing `loushang.tui` render primitives, `InputEvent`, `RenderConstraints`, `SearchableList`, `Tabs`, and widget playback helpers.

---

## Spec

Implement against:

`docs/superpowers/specs/2026-06-14-tui-page-scaffold-design.md`

Important constraints:

- Create `src/loushang/tui/ui_parts/widgets/page_scaffold.py`.
- Create `examples/tui/53_widgets_page_scaffold.py`.
- Do not modify `examples/tui/52_widgets_tabgroup_searchable_list.py`.
- Do not migrate `src/loushang/coding/ui/settings_page.py`.
- Header `enter` and `down` are intentionally intercepted before `Tabs.handle_input()` so PageScaffold can enter the body, matching `TabGroup` header behavior.
- Do not add `widget.pageScaffold.*` theme tokens in this slice.

## File Structure

- Create `src/loushang/tui/ui_parts/widgets/page_scaffold.py`
  - Defines `PageScaffoldContext`, `PageScaffoldFooter`, and `PageScaffold`.
  - Owns generic slot rendering, footer reservation, cursor offset, and header/body focus movement.

- Modify `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export `PageScaffold`, `PageScaffoldContext`, and `PageScaffoldFooter`.

- Modify `src/loushang/tui/ui_parts/__init__.py`
  - Re-export `PageScaffold`, `PageScaffoldContext`, and `PageScaffoldFooter`.

- Modify `src/loushang/tui/__init__.py`
  - Re-export `PageScaffold`, `PageScaffoldContext`, and `PageScaffoldFooter`.

- Create `tests/tui/test_widgets_page_scaffold.py`
  - Covers unit behavior and example 53 playback.

- Create `examples/tui/53_widgets_page_scaffold.py`
  - Demonstrates PageScaffold directly.

- Modify `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`
  - Add PageScaffold to the UI part inventory and clarify its boundary with `ScreenRegionStack`.

---

### Task 1: Rendering Foundation

**Files:**
- Create: `tests/tui/test_widgets_page_scaffold.py`
- Create: `src/loushang/tui/ui_parts/widgets/page_scaffold.py`

- [ ] **Step 1: Write failing rendering tests**

Create `tests/tui/test_widgets_page_scaffold.py` with helpers and these initial tests:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loushang.tui import CursorDeclaration, RenderConstraints, RenderLine, RenderResult, strip_control_sequences
from loushang.tui.ui_parts.widgets.page_scaffold import PageScaffold


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


@dataclass(slots=True)
class StaticPart:
    lines: tuple[str, ...]

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines(
            [RenderLine(line[: constraints.width]) for line in self.lines[: constraints.max_height]],
            constraints=constraints,
        )


@dataclass(slots=True)
class CursorPart(StaticPart):
    cursor: CursorDeclaration | None = None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        result = super().render(constraints)
        return RenderResult.from_lines(result.lines, constraints=constraints, cursor=self.cursor)


def test_page_scaffold_renders_body_only_page() -> None:
    scaffold = PageScaffold(body=StaticPart(("body",)))

    assert plain_lines(scaffold, width=20, height=3) == ("body",)


def test_page_scaffold_ignores_non_renderable_optional_header() -> None:
    scaffold = PageScaffold(
        header=object(),
        body=StaticPart(("body",)),
        separator_after_header=True,
    )

    assert plain_lines(scaffold, width=20, height=3) == ("body",)


def test_page_scaffold_renders_blank_line_for_non_renderable_body() -> None:
    scaffold = PageScaffold(body=object())

    assert plain_lines(scaffold, width=20, height=3) == ("",)


def test_page_scaffold_renders_header_separator_body_padding_and_footer() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=StaticPart(("body",)),
        footer="footer",
        separator_after_header=True,
    )

    assert plain_lines(scaffold, width=12, height=5) == (
        "header",
        "------------",
        "body",
        "",
        "footer",
    )


def test_page_scaffold_reserves_footer_height_under_long_body_content() -> None:
    scaffold = PageScaffold(
        body=StaticPart(tuple(f"row {index}" for index in range(10))),
        footer="footer",
    )

    lines = plain_lines(scaffold, width=20, height=4)

    assert lines[-1] == "footer"
    assert "row 0" in lines
    assert "row 9" not in lines


def test_page_scaffold_tiny_heights_prioritize_header_body_then_footer() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=StaticPart(("body",)),
        footer="footer",
    )

    assert plain_lines(scaffold, width=20, height=1) == ("header",)
    assert plain_lines(scaffold, width=20, height=2) == ("header", "body")


def test_page_scaffold_offsets_body_cursor_after_header_and_separator() -> None:
    scaffold = PageScaffold(
        header=StaticPart(("header",)),
        body=CursorPart(("body",), CursorDeclaration(row=0, column=2)),
        footer="footer",
        focused=True,
        focus_region="body",
        separator_after_header=True,
    )

    result = scaffold.render(RenderConstraints(width=20, max_height=5))

    assert result.cursor == CursorDeclaration(row=2, column=2)


def test_page_scaffold_uses_header_cursor_without_body_offset() -> None:
    scaffold = PageScaffold(
        header=CursorPart(("header",), CursorDeclaration(row=0, column=1)),
        body=CursorPart(("body",), CursorDeclaration(row=0, column=2)),
        focused=True,
        focus_region="header",
        separator_after_header=True,
    )

    result = scaffold.render(RenderConstraints(width=20, max_height=4))

    assert result.cursor == CursorDeclaration(row=0, column=1)
```

- [ ] **Step 2: Run rendering tests and verify they fail because PageScaffold is missing**

Run:

```bash
uv run pytest tests/tui/test_widgets_page_scaffold.py -q
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `page_scaffold` / `PageScaffold`.

- [ ] **Step 3: Implement minimal rendering support**

Create `src/loushang/tui/ui_parts/widgets/page_scaffold.py` with the public classes and rendering helpers. Keep it plain and slot-based:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import CursorDeclaration, RenderConstraints, RenderLine, RenderResult

PageScaffoldFocusRegion = Literal["header", "body"]


@dataclass(frozen=True, slots=True)
class PageScaffoldContext:
    focus_region: PageScaffoldFocusRegion
    header_focused: bool
    body_focused: bool


PageScaffoldFooter = str | Callable[[PageScaffoldContext], str]


@dataclass(slots=True)
class PageScaffold:
    body: object
    header: object | None = None
    footer: PageScaffoldFooter = ""
    focused: bool = False
    focus_region: PageScaffoldFocusRegion = "body"
    separator_after_header: bool = False
    reserve_footer: bool = True

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = autowrap_safe_width(constraints.width)
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)
        footer_text = self._footer_text(width)
        rows: list[RenderLine] = []
        header_result = _render_part(
            self.header,
            RenderConstraints(
                width=width,
                max_height=constraints.max_height,
                visible_height=constraints.visible_height,
            ),
            missing_render_lines=0,
        )
        header_lines = list(header_result.lines)
        if header_lines:
            rows.extend(header_lines[: constraints.max_height])
        if self.separator_after_header and header_lines and len(rows) < constraints.max_height:
            rows.append(RenderLine("-" * max(1, width)))
        remaining_after_chrome = constraints.max_height - len(rows)
        footer_reserved = 1 if self.reserve_footer and footer_text and remaining_after_chrome >= 2 else 0
        body_budget = max(0, constraints.max_height - len(rows) - footer_reserved)
        if body_budget <= 0 and not rows and constraints.max_height > 0:
            body_budget = constraints.max_height
        body_start = len(rows)
        if body_budget > 0 and len(rows) < constraints.max_height:
            body_result = _render_part(
                self.body,
                RenderConstraints(
                    width=width,
                    max_height=body_budget,
                    visible_height=constraints.visible_height,
                ),
                missing_render_lines=1,
            )
            rows.extend(list(body_result.lines[:body_budget]))
        else:
            body_result = RenderResult.from_lines([], constraints=constraints)
        if footer_text and len(rows) < constraints.max_height:
            if self.reserve_footer:
                while len(rows) < constraints.max_height - 1:
                    rows.append(RenderLine(""))
            if len(rows) < constraints.max_height:
                rows.append(RenderLine(footer_text))
        cursor = self._offset_cursor(
            header_result.cursor,
            body_result.cursor,
            body_start,
            constraints.max_height,
        )
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)
```

Then add the remaining helpers:

```python
    def _context(self) -> PageScaffoldContext:
        return PageScaffoldContext(
            focus_region=self.focus_region,
            header_focused=self.focused and self.focus_region == "header",
            body_focused=self.focused and self.focus_region == "body",
        )

    def _footer_text(self, width: int) -> str:
        value = self.footer(self._context()) if callable(self.footer) else self.footer
        return truncate_to_width(str(value), max_width=width, ellipsis="") if value else ""

    def _offset_cursor(
        self,
        header_cursor: CursorDeclaration | None,
        body_cursor: CursorDeclaration | None,
        body_start: int,
        max_height: int,
    ) -> CursorDeclaration | None:
        cursor = header_cursor if self.focus_region == "header" else body_cursor
        if cursor is None:
            return None
        row = cursor.row if self.focus_region == "header" else body_start + cursor.row
        if row < 0 or row >= max_height:
            return None
        return CursorDeclaration(row=row, column=cursor.column)


def _render_part(
    part: object | None,
    constraints: RenderConstraints,
    *,
    missing_render_lines: int,
) -> RenderResult:
    render = getattr(part, "render", None)
    if callable(render):
        return render(constraints)
    line_count = min(max(0, missing_render_lines), max(0, constraints.max_height))
    return RenderResult.from_lines([RenderLine("") for _ in range(line_count)], constraints=constraints)
```

This first implementation may not yet satisfy focus/input tests; those come in Task 2.

- [ ] **Step 4: Run rendering tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_page_scaffold.py -q
```

Expected: the rendering tests from Task 1 pass. If later focus tests do not exist yet, all tests in this file should pass at this point.

- [ ] **Step 5: Commit rendering foundation**

```bash
git add src/loushang/tui/ui_parts/widgets/page_scaffold.py tests/tui/test_widgets_page_scaffold.py
git commit -m "feat(tui): add page scaffold rendering foundation"
```

---

### Task 2: Focus, Input, Footer Context, And Editor Target

**Files:**
- Modify: `tests/tui/test_widgets_page_scaffold.py`
- Modify: `src/loushang/tui/ui_parts/widgets/page_scaffold.py`

- [ ] **Step 1: Add failing focus/input tests**

Append these helpers/tests to `tests/tui/test_widgets_page_scaffold.py`:

```python
@dataclass(slots=True)
class FocusablePart(StaticPart):
    focused: bool = False
    blurred: bool = False
    handled_keys: tuple[str, ...] = ()
    editor_target: object | None = None

    def focus(self) -> None:
        self.focused = True
        self.blurred = False

    def blur(self) -> None:
        self.focused = False
        self.blurred = True

    def handle_input(self, event: object) -> object:
        key = getattr(event, "key", "")
        if key in self.handled_keys:
            return f"handled:{key}"
        return None

    def editor_input_target(self) -> object | None:
        return self.editor_target if self.focused else None


def test_page_scaffold_focus_and_blur_delegate_to_active_slot() -> None:
    header = FocusablePart(("header",))
    body = FocusablePart(("body",))
    scaffold = PageScaffold(header=header, body=body, focus_region="body")

    scaffold.focus()
    assert scaffold.focused is True
    assert body.focused is True
    assert header.focused is False

    scaffold.blur()
    assert scaffold.focused is False
    assert body.blurred is True
    assert header.blurred is True


def test_page_scaffold_down_and_enter_from_header_focus_body_before_header_delegation() -> None:
    header = FocusablePart(("header",), handled_keys=("enter", "down"))
    body = FocusablePart(("body",))
    scaffold = PageScaffold(header=header, body=body, focused=True, focus_region="header")
    scaffold.focus_header()

    assert scaffold.handle_input(InputEvent(kind="key", key="enter")) is True
    assert scaffold.focus_region == "body"
    assert body.focused is True
    assert header.focused is False


def test_page_scaffold_unhandled_up_and_shift_tab_from_body_focus_header() -> None:
    header = FocusablePart(("header",))
    body = FocusablePart(("body",))
    scaffold = PageScaffold(header=header, body=body, focused=True, focus_region="body")
    scaffold.focus_body()

    assert scaffold.handle_input(InputEvent(kind="key", key="up")) is True
    assert scaffold.focus_region == "header"
    assert header.focused is True
    assert body.focused is False

    assert scaffold.handle_input(InputEvent(kind="key", key="down")) is True
    assert scaffold.handle_input(InputEvent(kind="key", key="shift+tab")) is True
    assert scaffold.focus_region == "header"


def test_page_scaffold_does_not_steal_handled_body_input() -> None:
    header = FocusablePart(("header",))
    body = FocusablePart(("body",), handled_keys=("up",))
    scaffold = PageScaffold(header=header, body=body, focused=True, focus_region="body")
    scaffold.focus_body()

    assert scaffold.handle_input(InputEvent(kind="key", key="up")) == "handled:up"
    assert scaffold.focus_region == "body"


def test_page_scaffold_editor_target_delegates_to_current_focus_region() -> None:
    header_target = object()
    body_target = object()
    header = FocusablePart(("header",), editor_target=header_target)
    body = FocusablePart(("body",), editor_target=body_target)
    scaffold = PageScaffold(header=header, body=body, focused=True, focus_region="body")

    scaffold.focus_body()
    assert scaffold.editor_input_target() is body_target

    scaffold.focus_header()
    assert scaffold.editor_input_target() is header_target


def test_page_scaffold_footer_callable_receives_focus_context() -> None:
    body = FocusablePart(("body",))
    header = FocusablePart(("header",))

    def footer(context):
        return f"{context.focus_region}:{context.header_focused}:{context.body_focused}"

    scaffold = PageScaffold(header=header, body=body, footer=footer, focused=True, focus_region="body")

    assert plain_lines(scaffold, width=40, height=4)[-1] == "body:False:True"
    scaffold.focus_header()
    assert plain_lines(scaffold, width=40, height=4)[-1] == "header:True:False"


def test_page_scaffold_missing_optional_methods_do_not_crash() -> None:
    scaffold = PageScaffold(header=object(), body=object(), footer="footer", focused=True)

    assert plain_lines(scaffold, width=20, height=3)[-1] == "footer"
    assert scaffold.handle_input(InputEvent(kind="key", key="up")) in {False, None}
    assert scaffold.editor_input_target() is None
```

Remember to add `InputEvent` to the existing import from `loushang.tui`.

- [ ] **Step 2: Run focus/input tests and verify they fail**

Run:

```bash
uv run pytest tests/tui/test_widgets_page_scaffold.py -q
```

Expected: FAIL because `PageScaffold` does not yet implement focus/input/editor delegation methods.

- [ ] **Step 3: Implement focus and input methods**

Add `InputEvent` handling utilities to `page_scaffold.py`:

```python
from loushang.tui.keybindings import normalize_key_id
```

Add methods on `PageScaffold`:

```python
    def focus(self) -> None:
        self.focused = True
        if self.focus_region == "header" and self.focus_header():
            return
        if self.focus_body():
            return
        self.focus_header()

    def blur(self) -> None:
        self.focused = False
        _call(self.header, "blur")
        _call(self.body, "blur")

    def focus_header(self) -> bool:
        if self.header is None or not _has_method(self.header, "focus"):
            return False
        _call(self.body, "blur")
        _call(self.header, "focus")
        self.focused = True
        self.focus_region = "header"
        return True

    def focus_body(self) -> bool:
        if not _has_method(self.body, "focus"):
            return False
        _call(self.header, "blur")
        _call(self.body, "focus")
        self.focused = True
        self.focus_region = "body"
        return True

    def editor_input_target(self) -> object | None:
        if not self.focused:
            return None
        target = self.header if self.focus_region == "header" else self.body
        method = getattr(target, "editor_input_target", None)
        return method() if callable(method) else None

    def handle_input(self, event: object) -> object:
        if not self.focused:
            return None
        key = normalize_key_id(getattr(event, "key", "")) if getattr(event, "kind", "") == "key" else ""
        if self.focus_region == "header":
            if key in {"down", "enter"}:
                return True if self.focus_body() else False
            return _handle(self.header, event)
        result = _handle(self.body, event)
        if result is not None:
            return result
        if key in {"up", "shift+tab"}:
            return True if self.focus_header() else False
        return None
```

Add helpers:

```python
def _has_method(part: object | None, name: str) -> bool:
    return callable(getattr(part, name, None))


def _call(part: object | None, name: str) -> object:
    method = getattr(part, name, None)
    return method() if callable(method) else None


def _handle(part: object | None, event: object) -> object:
    method = getattr(part, "handle_input", None)
    return method(event) if callable(method) else None
```

This explicitly intercepts header `enter` before `Tabs.handle_input()`, per spec.

- [ ] **Step 4: Run PageScaffold unit tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_page_scaffold.py -q
```

Expected: all PageScaffold unit tests pass.

- [ ] **Step 5: Run Ruff on the new files**

Run:

```bash
uv run ruff check src/loushang/tui/ui_parts/widgets/page_scaffold.py tests/tui/test_widgets_page_scaffold.py
```

Expected: no lint failures.

- [ ] **Step 6: Commit focus/input behavior**

```bash
git add src/loushang/tui/ui_parts/widgets/page_scaffold.py tests/tui/test_widgets_page_scaffold.py
git commit -m "feat(tui): add page scaffold focus orchestration"
```

---

### Task 3: Public Exports

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Modify: `tests/tui/test_widgets_page_scaffold.py`

- [ ] **Step 1: Add failing public export test**

Add to `tests/tui/test_widgets_page_scaffold.py`:

```python
def test_page_scaffold_public_exports() -> None:
    from loushang.tui import PageScaffold as PublicPageScaffold
    from loushang.tui import PageScaffoldContext as PublicPageScaffoldContext
    from loushang.tui import PageScaffoldFooter as PublicPageScaffoldFooter
    from loushang.tui.ui_parts import PageScaffold as UiPageScaffold
    from loushang.tui.ui_parts import PageScaffoldContext as UiPageScaffoldContext
    from loushang.tui.ui_parts import PageScaffoldFooter as UiPageScaffoldFooter
    from loushang.tui.ui_parts.widgets import PageScaffold as WidgetPageScaffold
    from loushang.tui.ui_parts.widgets import PageScaffoldContext as WidgetPageScaffoldContext
    from loushang.tui.ui_parts.widgets import PageScaffoldFooter as WidgetPageScaffoldFooter
    from loushang.tui.ui_parts.widgets.page_scaffold import PageScaffoldContext
    from loushang.tui.ui_parts.widgets.page_scaffold import PageScaffoldFooter

    assert PublicPageScaffold is PageScaffold
    assert UiPageScaffold is PageScaffold
    assert WidgetPageScaffold is PageScaffold
    assert PublicPageScaffoldContext is PageScaffoldContext
    assert PublicPageScaffoldContext is WidgetPageScaffoldContext
    assert UiPageScaffoldContext is WidgetPageScaffoldContext
    assert PublicPageScaffoldFooter is PageScaffoldFooter
    assert PublicPageScaffoldFooter is WidgetPageScaffoldFooter
    assert UiPageScaffoldFooter is WidgetPageScaffoldFooter
```

- [ ] **Step 2: Run export test and verify it fails**

Run:

```bash
uv run pytest tests/tui/test_widgets_page_scaffold.py::test_page_scaffold_public_exports -q
```

Expected: FAIL because exports are not wired.

- [ ] **Step 3: Add public exports**

In `src/loushang/tui/ui_parts/widgets/__init__.py`, import and add to `__all__`:

```python
from .page_scaffold import PageScaffold as PageScaffold
from .page_scaffold import PageScaffoldContext as PageScaffoldContext
from .page_scaffold import PageScaffoldFooter as PageScaffoldFooter
```

In `src/loushang/tui/ui_parts/__init__.py`, import from `.widgets` and add to `__all__`:

```python
from .widgets import PageScaffold as PageScaffold
from .widgets import PageScaffoldContext as PageScaffoldContext
from .widgets import PageScaffoldFooter as PageScaffoldFooter
```

In `src/loushang/tui/__init__.py`, add `PageScaffold`, `PageScaffoldContext`, and `PageScaffoldFooter` to the existing widget import block and `__all__`.

- [ ] **Step 4: Run export test and import-boundary tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_page_scaffold.py::test_page_scaffold_public_exports tests/tui/test_import_boundaries.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit exports**

```bash
git add src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_page_scaffold.py
git commit -m "feat(tui): export page scaffold widget"
```

---

### Task 4: Example 53 And Playback

**Files:**
- Create: `examples/tui/53_widgets_page_scaffold.py`
- Modify: `tests/tui/test_widgets_page_scaffold.py`

- [ ] **Step 1: Add failing example playback tests**

Add imports to `tests/tui/test_widgets_page_scaffold.py`:

```python
import runpy

from tests.tui.widget_example_playback import play_example
```

Add tests:

```python
def test_page_scaffold_example_imports_and_renders() -> None:
    namespace = runpy.run_path("examples/tui/53_widgets_page_scaffold.py", run_name="__test__")
    app = namespace["build_app"]()
    result = app.render(RenderConstraints(width=96, max_height=20))

    assert result.lines


def test_page_scaffold_example_playback_switches_focus_and_keeps_footer() -> None:
    frames = play_example(
        "examples/tui/53_widgets_page_scaffold.py",
        events=(
            ("up to header", InputEvent(kind="key", key="up")),
            ("right models", InputEvent(kind="key", key="right")),
            ("down to body", InputEvent(kind="key", key="down")),
            ("down list", InputEvent(kind="key", key="down")),
            ("page down", InputEvent(kind="key", key="pageDown")),
        ),
        width=96,
        height=20,
    )

    initial = frames[0].lines
    header = frames[1].lines
    models = frames[2].lines
    body = frames[3].lines
    scrolled = frames[-1].lines

    assert initial[0].startswith("*[Config]")
    assert initial[-1].startswith("Body |")
    assert header[0].startswith(">[Config]")
    assert header[-1].startswith("Header |")
    assert ">[Models]" in models[0]
    assert body[0].startswith("*[Models]")
    assert body[-1].startswith("Body |")
    assert scrolled[-1].startswith("Body |")
    assert any("more below" in line.lower() or "more above" in line.lower() for line in scrolled)
    assert frames[-1].cursor[0] < 19
```

- [ ] **Step 2: Run example tests and verify they fail because example 53 is missing**

Run:

```bash
uv run pytest tests/tui/test_widgets_page_scaffold.py -k page_scaffold_example -q
```

Expected: FAIL with missing `examples/tui/53_widgets_page_scaffold.py`.

- [ ] **Step 3: Create example 53**

Create `examples/tui/53_widgets_page_scaffold.py`.

Use this structure:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    InputEvent,
    PageScaffold,
    PageScaffoldContext,
    RenderConstraints,
    RenderLine,
    RenderResult,
    SearchableList,
    SearchableListItem,
    SearchableListSelect,
    TabItem,
    Tabs,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)
```

Create a small app:

```python
@dataclass(slots=True)
class PageScaffoldDemo:
    tabs: Tabs = field(init=False)
    bodies: dict[str, object] = field(init=False)
    scaffold: PageScaffold = field(init=False)
    status: str = "Ready"

    def __post_init__(self) -> None:
        self.tabs = Tabs(
            (
                TabItem("config", "Config"),
                TabItem("models", "Models"),
                TabItem("activity", "Activity"),
            ),
            on_change=self._select_tab,
        )
        self.bodies = {
            "config": _settings_list("Search settings...", _config_items()),
            "models": _settings_list("Search models...", _model_items()),
            "activity": StaticLinesPage(("Activity", "", "Recent actions", "Build succeeded")),
        }
        self.scaffold = PageScaffold(
            header=self.tabs,
            body=self.bodies[self.tabs.value],
            footer=self._footer,
            focused=True,
            focus_region="body",
            separator_after_header=True,
        )
        self.scaffold.focus()

    def _select_tab(self, value: str) -> bool:
        self.scaffold.body = self.bodies[value]
        self.scaffold.focus_region = "header"
        self.status = f"Selected: {value}"
        return True

    def _footer(self, context: PageScaffoldContext) -> str:
        if context.focus_region == "header":
            return f"Header | {self.status} | Left/Right switch | Down/Enter body | q quit"
        return f"Body | {self.status} | Type filter | Up tabs | Enter select | q quit"

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return self.scaffold.render(constraints)

    def handle_input(self, event: InputEvent) -> object:
        result = self.scaffold.handle_input(event)
        if isinstance(result, SearchableListSelect):
            self.status = f"Selected: {result.label}"
            return True
        return True if result is not None else None
```

Provide `StaticLinesPage`, `_settings_list()`, item factories, `build_app()`, `_should_quit()`, and `main()` following the style of example 52. Keep it non-product and self-contained.

Important: do not import or modify example 52.

- [ ] **Step 4: Run example playback tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_page_scaffold.py -k page_scaffold_example -q
```

Expected: example tests pass.

- [ ] **Step 5: Run example import/render smoke**

Run:

```bash
uv run python -c "import runpy; from loushang.tui import RenderConstraints; ns = runpy.run_path('examples/tui/53_widgets_page_scaffold.py', run_name='__test__'); app = ns['build_app'](); result = app.render(RenderConstraints(width=96, max_height=20)); print(len(result.lines))"
```

Expected: command exits successfully and prints a positive line count.

- [ ] **Step 6: Commit example 53**

```bash
git add examples/tui/53_widgets_page_scaffold.py tests/tui/test_widgets_page_scaffold.py
git commit -m "test(tui): add page scaffold example playback"
```

---

### Task 5: Internals Documentation And Final Verification

**Files:**
- Modify: `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`

- [ ] **Step 1: Add PageScaffold to internals UI part inventory**

Update the table row:

```markdown
| Navigation | Tabs, [TabGroup, TabPage](./tabgroup-content-switcher.md), PageScaffold |
```

Add a short section after the table:

```markdown
## Page-Level Scaffolding

`ScreenRegionStack` is the screen-level region allocator used by larger terminal
frames. `PageScaffold` is a widget-level page shell for reusable page content:
it arranges optional header, body, and footer slots and owns focus movement
between header and body. Concrete product pages still own business state,
selected content, and actions.
```

- [ ] **Step 2: Run focused PageScaffold tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_page_scaffold.py -q
```

Expected: all PageScaffold tests pass.

- [ ] **Step 3: Run focused widget tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_page_scaffold.py tests/tui/test_widgets_searchable_list.py tests/tui/test_widgets_light_controls.py -q
```

Expected: selected widget tests pass.

- [ ] **Step 4: Run TUI tests**

Run:

```bash
uv run pytest tests/tui -q
```

Expected: all TUI tests pass.

- [ ] **Step 5: Run focused lint**

Run:

```bash
uv run ruff check src/loushang/tui/ui_parts/widgets/page_scaffold.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_page_scaffold.py examples/tui/53_widgets_page_scaffold.py
```

Expected: no lint failures.

- [ ] **Step 6: Commit docs**

```bash
git add docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md
git commit -m "docs(tui): document page scaffold boundary"
```

- [ ] **Step 7: Final status check**

Run:

```bash
git status --short --branch
git log --oneline -8
```

Expected: branch includes the PageScaffold spec, plan, implementation, example, and docs commits; working tree is clean.

---

## Manual Validation Notes

After automated tests pass, manually run the new example when practical:

```bash
uv run python examples/tui/53_widgets_page_scaffold.py
```

Expected behavior:

- initial focus is in the body and the header selected tab uses the selected-content marker
- up from search/body moves focus to the header
- enter or down from header enters the body before primitive `Tabs` can consume enter
- left/right in header switches tabs
- footer text changes between header and body focus
- long list body keeps footer pinned to the bottom

Use `q` or `ctrl+c` to exit.
