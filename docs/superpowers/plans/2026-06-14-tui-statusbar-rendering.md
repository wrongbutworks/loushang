# TUI Status Bar Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable semantic styling and separator support to `StatusBar` without changing default unstyled behavior.

**Architecture:** Keep the feature contained in `src/loushang/tui/ui_parts/status.py`. `StatusField` carries optional semantic metadata, while `StatusBar` owns separator joining, style-mode selection, theme fallback, and built-in default styles. Coding/product settings work is explicitly deferred to a later code-lane PR.

**Tech Stack:** Python dataclasses, existing `loushang.tui.theme.ThemeResolver`, `ThemeStyle`, `apply_theme_style`, pytest, Ruff.

---

## References

- Spec: `docs/superpowers/specs/2026-06-14-tui-statusbar-rendering-design.md`
- Lane split: `docs/superpowers/specs/2026-06-14-tui-statusline-settings-tab-design.md`
- Existing implementation: `src/loushang/tui/ui_parts/status.py`
- Existing footer tests: `tests/tui/test_footer_statusline.py`
- Existing composer bottom-frame tests: `tests/tui/test_composer_bottom_frame.py`
- Existing theme API: `src/loushang/tui/theme.py`

## File Structure

- Modify: `src/loushang/tui/ui_parts/status.py`
  - Extend `StatusField`.
  - Extend `StatusBar`.
  - Add local helpers for joining, token normalization, token candidate order,
    built-in styles, and final segment styling.
  - Preserve `StatusField.token` in `_render_extension_statuses()`.
- Verify: `src/loushang/tui/ui_parts/__init__.py`
  - No source change expected because it already re-exports `StatusBar` and
    `StatusField`.
- Verify: `src/loushang/tui/__init__.py`
  - No source change expected because it already re-exports `StatusBar` and
    `StatusField`.
- Create: `tests/tui/test_status_bar.py`
  - Focused tests for the reusable renderer API and styling behavior.
- Modify: `tests/tui/test_footer_statusline.py`
  - Add a focused regression test for `_render_extension_statuses()` because
    token preservation is otherwise not observable through the current
    unthemed `FooterView` public API.

## Implementation Notes

- Do not touch `src/loushang/coding/...` in this plan.
- Do not add Settings UI, `/statusline` behavior, persistence, or product
  status-line field builders.
- Keep `StatusBar.style_mode` default as `"plain"` so existing callers remain
  unstyled.
- Apply styling only after field selection and truncation. Field fitting must
  use raw text and the raw separator.
- Import theme primitives directly in `status.py`:

```python
from loushang.tui.theme import ThemeResolver, ThemeStyle, apply_theme_style
```

- Use local helpers rather than changing the global theme system.

## Task 1: Compatibility, Token Field, and Custom Separator

**Files:**
- Create: `tests/tui/test_status_bar.py`
- Modify: `src/loushang/tui/ui_parts/status.py`

- [ ] **Step 1: Write failing tests for default compatibility and separator**

Add `tests/tui/test_status_bar.py`:

```python
from __future__ import annotations

from loushang.tui import RenderConstraints, StatusBar, StatusField, visible_width


def rendered_text(status: StatusBar, *, width: int = 40) -> str:
    result = status.render(RenderConstraints(width=width, max_height=1))
    return result.lines[0].text


def test_status_bar_default_output_is_unchanged() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100),
            StatusField("running", priority=80),
        ]
    )

    assert rendered_text(status, width=30) == "model | running"


def test_status_bar_accepts_optional_field_token() -> None:
    field = StatusField("model", priority=100, token="model")

    assert field.text == "model"
    assert field.priority == 100
    assert field.token == "model"


def test_status_bar_custom_separator_changes_joined_text() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100),
            StatusField("running", priority=80),
        ],
        separator=" · ",
    )

    assert rendered_text(status, width=30) == "model · running"


def test_status_bar_priority_fitting_uses_custom_separator() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100),
            StatusField("very-long-branch-name", priority=10),
            StatusField("running", priority=80),
        ],
        separator=" · ",
    )

    line = rendered_text(status, width=16)

    assert line == "model · running"
    assert visible_width(line) == 15
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/tui/test_status_bar.py -q
```

Expected: FAIL because `StatusField` has no `token` parameter and `StatusBar`
has no `separator` parameter.

- [ ] **Step 3: Implement minimal compatibility and separator support**

In `src/loushang/tui/ui_parts/status.py`:

```python
@dataclass(frozen=True, slots=True)
class StatusField:
    text: str
    priority: int = 0
    token: str = ""


@dataclass(slots=True)
class StatusBar:
    fields: list[StatusField] | tuple[StatusField, ...] = field(default_factory=list)
    separator: str = " | "

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        ordered = sorted(self.fields, key=lambda status_field: status_field.priority, reverse=True)
        selected: list[StatusField] = []
        for status_field in ordered:
            candidate = selected + [status_field]
            text = _join_status(candidate, separator=self.separator)
            if visible_width(text) <= target_width:
                selected = candidate
        text = _join_status(selected, separator=self.separator)
        if not text and ordered:
            text = ordered[0].text
        line = truncate_to_width(text, max_width=target_width)
        return RenderResult.from_lines([RenderLine(line)], constraints=constraints)


def _join_status(fields: list[StatusField], *, separator: str) -> str:
    return separator.join(field.text for field in fields)
```

Update any internal calls to `_join_status(...)` to pass `separator=...`.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/tui/test_status_bar.py tests/tui/test_composer_bottom_frame.py::test_status_bar_omits_low_priority_fields_before_wrapping -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/loushang/tui/ui_parts/status.py tests/tui/test_status_bar.py
git commit -m "feat(tui): add status bar separator metadata"
```

## Task 2: Plain Mode API

**Files:**
- Modify: `src/loushang/tui/ui_parts/status.py`
- Modify: `tests/tui/test_status_bar.py`

- [ ] **Step 1: Write a failing test for `plain` mode**

Add the import near the top of `tests/tui/test_status_bar.py`:

```python
from loushang.tui.theme import ThemeResolver
```

Append to `tests/tui/test_status_bar.py`:

```python

def test_status_bar_plain_mode_ignores_theme_tokens() -> None:
    theme = ThemeResolver(
        defaults={
            "statusBar.model": {"foreground": "red"},
            "statusBar.field": {"foreground": "green"},
            "statusBar.separator": {"foreground": "yellow"},
        }
    )
    status = StatusBar(
        [
            StatusField("model", priority=100, token="model"),
            StatusField("running", priority=80, token="runtime.running"),
        ],
        theme=theme,
        style_mode="plain",
    )

    assert rendered_text(status, width=30) == "model | running"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/tui/test_status_bar.py::test_status_bar_plain_mode_ignores_theme_tokens -q
```

Expected: FAIL because `StatusBar` has no `theme` or `style_mode` parameters.

- [ ] **Step 3: Implement minimal `plain` mode API**

In `src/loushang/tui/ui_parts/status.py`:

```python
from loushang.tui.theme import ThemeResolver


StatusBarStyleMode = Literal["plain", "muted", "codex-like"]


@dataclass(slots=True)
class StatusBar:
    fields: list[StatusField] | tuple[StatusField, ...] = field(default_factory=list)
    separator: str = " | "
    style_mode: StatusBarStyleMode = "plain"
    theme: ThemeResolver | None = None
```

Keep rendering unstyled for now when `style_mode == "plain"`.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/tui/test_status_bar.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/loushang/tui/ui_parts/status.py tests/tui/test_status_bar.py
git commit -m "feat(tui): add status bar plain style mode"
```

## Task 3: Styled Modes, Built-In Defaults, and Theme Overrides

**Files:**
- Modify: `src/loushang/tui/ui_parts/status.py`
- Modify: `tests/tui/test_status_bar.py`
- Modify: `tests/tui/test_footer_statusline.py`

- [ ] **Step 1: Write failing tests for built-in styled output**

Append to `tests/tui/test_status_bar.py`:

```python
def test_status_bar_codex_like_mode_applies_builtin_field_styles_without_theme() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100, token="model"),
            StatusField("idle", priority=80, token="runtime.idle"),
        ],
        style_mode="codex-like",
    )

    line = rendered_text(status, width=30)

    assert "\x1b[36mmodel\x1b[39m" in line
    assert "\x1b[2midle\x1b[22m" in line


def test_status_bar_codex_like_mode_styles_separator_without_theme() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100, token="model"),
            StatusField("branch", priority=80, token="branch"),
        ],
        style_mode="codex-like",
    )

    line = rendered_text(status, width=30)

    assert "\x1b[2m | \x1b[22m" in line


def test_status_bar_muted_mode_applies_builtin_styles_without_theme() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100, token="model"),
            StatusField("branch", priority=80, token="branch"),
        ],
        style_mode="muted",
    )

    line = rendered_text(status, width=30)

    assert "\x1b[2mmodel\x1b[22m" in line
    assert "\x1b[2m | \x1b[22m" in line


def test_status_bar_theme_override_beats_builtin_style() -> None:
    theme = ThemeResolver(defaults={"statusBar.codexLike.model": {"foreground": "red"}})
    status = StatusBar(
        [StatusField("model", priority=100, token="model")],
        style_mode="codex-like",
        theme=theme,
    )

    assert rendered_text(status, width=20) == "\x1b[31mmodel\x1b[39m"
```

Add imports near the top of `tests/tui/test_footer_statusline.py`:

```python
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.status import _render_extension_statuses
```

Append to `tests/tui/test_footer_statusline.py`:

```python
def test_footer_view_preserves_extension_status_tokens_when_sanitizing() -> None:
    theme = ThemeResolver(defaults={"statusBar.model": {"foreground": "red"}})
    lines = _render_extension_statuses(
        (
            StatusField("bad\nmodel\ttext", priority=100, token="model"),
        ),
        RenderConstraints(width=40, max_height=1),
        style_mode="codex-like",
        theme=theme,
    )

    assert lines == ["\x1b[31mbad model text\x1b[39m"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/tui/test_status_bar.py tests/tui/test_footer_statusline.py::test_footer_view_preserves_extension_status_tokens_when_sanitizing -q
```

Expected: FAIL because styled modes do not yet apply ANSI output and
`_render_extension_statuses()` has no optional styling parameters yet.

- [ ] **Step 3: Implement token styling helpers**

In `src/loushang/tui/ui_parts/status.py`, add helpers with this shape:

```python
from loushang.tui.theme import ThemeResolver, ThemeStyle, apply_theme_style


_MODE_TOKEN_PREFIX = {
    "codex-like": "codexLike",
    "muted": "muted",
}

_CODEX_LIKE_DEFAULTS: dict[str, ThemeStyle] = {
    "model": {"foreground": "cyan"},
    "workspace": {"foreground": "green"},
    "branch": {"foreground": "yellow"},
    "session": {"foreground": "bright_black"},
    "runtime.running": {"foreground": "green"},
    "runtime.idle": {"dim": True},
    "queue": {"foreground": "magenta"},
    "message": {"foreground": "bright_white"},
    "separator": {"dim": True},
}

_MUTED_DEFAULTS: dict[str, ThemeStyle] = {
    "field": {"dim": True},
    "separator": {"dim": True},
}
```

Add a style lookup that:

- returns `None` immediately for `style_mode == "plain"`
- resolves theme token candidates first
- falls back to built-in defaults only when no theme style resolves
- falls back to generic built-ins for unknown muted fields

Implementation outline:

```python
def _style_for_status_part(
    *,
    theme: ThemeResolver | None,
    style_mode: StatusBarStyleMode,
    token: str,
    separator: bool = False,
) -> ThemeStyle | None:
    if style_mode == "plain":
        return None
    semantic_token, exact_tokens = _normalize_status_token(token, style_mode=style_mode)
    for candidate in _status_token_candidates(
        semantic_token,
        style_mode=style_mode,
        exact_tokens=exact_tokens,
        separator=separator,
    ):
        style = theme.resolve(candidate) if theme is not None else {}
        if style:
            return style
    return _builtin_status_style(style_mode, semantic_token, separator=separator)
```

Render by joining already-styled segments after selection:

```python
def _render_status_segments(
    fields: list[StatusField],
    *,
    separator: str,
    style_mode: StatusBarStyleMode,
    theme: ThemeResolver | None,
) -> str:
    rendered: list[str] = []
    for index, field in enumerate(fields):
        if index:
            rendered.append(_style_status_text(separator, theme, style_mode, "separator", separator=True))
        rendered.append(_style_status_text(field.text, theme, style_mode, field.token))
    return "".join(rendered)
```

For the fallback single-field truncation path, style the truncated field text
with the winning field's token.

Update `_render_extension_statuses(...)` to preserve `token` and accept optional
private styling parameters:

```python
def _render_extension_statuses(
    statuses: list[StatusField] | tuple[StatusField, ...],
    constraints: RenderConstraints,
    *,
    separator: str = " | ",
    style_mode: StatusBarStyleMode = "plain",
    theme: ThemeResolver | None = None,
) -> list[str]:
    sanitized = [
        StatusField(
            _sanitize_footer_text(status.text),
            priority=status.priority,
            token=status.token,
        )
        for status in statuses
        if _sanitize_footer_text(status.text)
    ]
    ...
    return [
        line.text
        for line in StatusBar(
            sanitized,
            separator=separator,
            style_mode=style_mode,
            theme=theme,
        ).render(constraints).lines
    ]
```

Use these optional private-helper parameters only for tests and future internal
callers. Do not add `theme` or `style_mode` fields to `FooterView` in this
task; that would broaden public footer behavior beyond the current slice.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/tui/test_status_bar.py tests/tui/test_footer_statusline.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/loushang/tui/ui_parts/status.py tests/tui/test_status_bar.py tests/tui/test_footer_statusline.py
git commit -m "feat(tui): style status bar semantic tokens"
```

## Task 4: Width Safety, Unknown Tokens, and Fully Qualified Tokens

**Files:**
- Modify: `src/loushang/tui/ui_parts/status.py`
- Modify: `tests/tui/test_status_bar.py`
- Modify: `tests/tui/test_composer_bottom_frame.py` only if existing
  expectations need a compatible import or helper adjustment.

- [ ] **Step 1: Write failing tests for fitting and token normalization**

Append to `tests/tui/test_status_bar.py`:

```python
def test_status_bar_width_fitting_ignores_ansi_sequences() -> None:
    status = StatusBar(
        [
            StatusField("model", priority=100, token="model"),
            StatusField("very-long-branch-name", priority=10, token="branch"),
            StatusField("running", priority=80, token="runtime.running"),
        ],
        style_mode="codex-like",
    )

    line = rendered_text(status, width=16)

    assert "very-long-branch-name" not in line
    assert visible_width(line) == 15
    assert "model" in line
    assert "running" in line


def test_status_bar_unknown_token_falls_back_to_generic_field_style() -> None:
    theme = ThemeResolver(defaults={"statusBar.field": {"foreground": "blue"}})
    status = StatusBar(
        [StatusField("custom", priority=100, token="unknown")],
        style_mode="codex-like",
        theme=theme,
    )

    assert rendered_text(status, width=20) == "\x1b[34mcustom\x1b[39m"


def test_status_bar_fully_qualified_token_behaves_like_semantic_token() -> None:
    status = StatusBar(
        [StatusField("model", priority=100, token="statusBar.model")],
        style_mode="codex-like",
    )

    assert rendered_text(status, width=20) == "\x1b[36mmodel\x1b[39m"


def test_status_bar_mode_qualified_token_resolves_exact_token_first() -> None:
    theme = ThemeResolver(defaults={"statusBar.codexLike.model": {"foreground": "red"}})
    status = StatusBar(
        [StatusField("model", priority=100, token="statusBar.codexLike.model")],
        style_mode="codex-like",
        theme=theme,
    )

    assert rendered_text(status, width=20) == "\x1b[31mmodel\x1b[39m"
```

- [ ] **Step 2: Run tests to verify failures or current gaps**

Run:

```bash
uv run pytest tests/tui/test_status_bar.py -q
```

Expected: FAIL for any missing token normalization or width-safety behavior.

- [ ] **Step 3: Tighten normalization and fitting implementation**

Update helper behavior:

```python
def _normalize_status_token(
    token: str,
    *,
    style_mode: StatusBarStyleMode,
) -> tuple[str, tuple[str, ...]]:
    normalized = token.strip()
    if not normalized:
        return "field", ()
    mode_prefix = _MODE_TOKEN_PREFIX.get(style_mode, "")
    if mode_prefix and normalized.startswith(f"statusBar.{mode_prefix}."):
        semantic = normalized[len(f"statusBar.{mode_prefix}.") :]
        return semantic or "field", (normalized,)
    if normalized.startswith("statusBar."):
        semantic = normalized[len("statusBar.") :]
        return semantic or "field", ()
    return normalized, ()
```

Mode-qualified tokens apply to the active style mode. Any token in the form
`statusBar.<mode>.<token>` for the current style mode should try the exact token
first, then continue through the semantic `<token>` fallback chain. For example,
`statusBar.codexLike.model` in `codex-like` mode tries
`statusBar.codexLike.model` first, then continues as `model`.

Ensure the selected field set is determined before applying
`apply_theme_style(...)`. Never call `visible_width()` on styled candidate
strings.

- [ ] **Step 4: Run focused and existing status-bar tests**

Run:

```bash
uv run pytest tests/tui/test_status_bar.py tests/tui/test_composer_bottom_frame.py::test_status_bar_omits_low_priority_fields_before_wrapping tests/tui/test_composer_bottom_frame.py::test_status_bar_reserves_last_column_to_avoid_terminal_autowrap -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/loushang/tui/ui_parts/status.py tests/tui/test_status_bar.py tests/tui/test_composer_bottom_frame.py
git commit -m "test(tui): lock status bar token fallback behavior"
```

## Task 5: Public Export and Regression Verification

**Files:**
- Modify: `tests/tui/test_status_bar.py`
- Verify: `src/loushang/tui/__init__.py`
- Verify: `src/loushang/tui/ui_parts/__init__.py`

- [ ] **Step 1: Add public export tests if not already covered**

Add these imports near the top of `tests/tui/test_status_bar.py`:

```python
from loushang.tui import StatusBar as PublicStatusBar
from loushang.tui import StatusField as PublicStatusField
from loushang.tui.ui_parts.status import StatusBar as ModuleStatusBar
from loushang.tui.ui_parts.status import StatusField as ModuleStatusField
```

Append to `tests/tui/test_status_bar.py`:

```python

def test_status_bar_public_exports_are_updated_classes() -> None:
    assert PublicStatusBar is ModuleStatusBar
    assert PublicStatusField is ModuleStatusField
    assert PublicStatusField("x", token="model").token == "model"
```

- [ ] **Step 2: Run export test**

Run:

```bash
uv run pytest tests/tui/test_status_bar.py::test_status_bar_public_exports_are_updated_classes -q
```

Expected: PASS. If it fails, update the public export modules without changing
their existing public names.

- [ ] **Step 3: Run full TUI status regression**

Run:

```bash
uv run pytest tests/tui/test_status_bar.py tests/tui/test_footer_statusline.py tests/tui/test_composer_bottom_frame.py -q
```

Expected: PASS.

- [ ] **Step 4: Run focused lint**

Run:

```bash
uv run ruff check src/loushang/tui/ui_parts/status.py tests/tui/test_status_bar.py tests/tui/test_footer_statusline.py tests/tui/test_composer_bottom_frame.py
```

Expected: PASS.

- [ ] **Step 5: Commit final verification changes**

If Step 1 changed only tests:

```bash
git add tests/tui/test_status_bar.py src/loushang/tui/__init__.py src/loushang/tui/ui_parts/__init__.py
git commit -m "test(tui): verify status bar public exports"
```

If no file changed in this task, skip the commit and record the verification
commands in the final implementation report.

## Final Handoff

After all tasks pass:

1. Run:

```bash
git status --short
git log --oneline -5
```

2. Confirm no `src/loushang/coding/...` files changed.
3. Summarize the final public API for the code lane:
   - `StatusField(token=...)`
   - `StatusBar(separator=...)`
   - `StatusBar(style_mode=...)`
   - `StatusBar(theme=...)`
   - `plain` default compatibility
   - `statusBar.*` token fallback behavior
4. State that the code lane should start from `main` after the TUI PR merges
   and should depend only on public `StatusBar` / `StatusField` APIs.
