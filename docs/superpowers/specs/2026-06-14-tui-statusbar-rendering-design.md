# TUI Status Bar Rendering Design

## Status

Ready for TUI-lane implementation planning.

This is the TUI-lane execution spec for the reusable status-bar rendering
foundation. It intentionally excludes the coding settings tab and other product
integration work.

## Package Scope

Implement the feature in:

`src/loushang/tui/ui_parts/status.py`

Keep public exports through:

- `src/loushang/tui/ui_parts/__init__.py`
- `src/loushang/tui/__init__.py`

No `src/loushang/coding/...` files should be changed for product behavior in
this slice.

## Current Behavior

`StatusBar` currently:

- accepts a sequence of `StatusField(text, priority)`
- sorts fields by descending priority
- keeps adding fields while the joined text fits
- joins selected fields with `" | "`
- falls back to the highest-priority field if no joined candidate fits
- truncates to the available width
- returns a single `RenderLine`

This behavior is useful and should remain the default.

## Goals

- Add optional semantic tokens to `StatusField`.
- Add configurable separator support to `StatusBar`.
- Add optional status-bar styling through existing `ThemeResolver`.
- Keep default rendering byte-for-byte compatible for unstyled callers.
- Keep width fitting based on unstyled visible text.
- Preserve token metadata when footer extension status fields are sanitized.
- Provide stable public API for the later code-lane Status Line settings work.

## Non-Goals

- Do not add Settings UI.
- Do not add status-line product settings models.
- Do not change `/statusline`.
- Do not add persistence.
- Do not introduce a new global theme registry.
- Do not embed ANSI sequences in `StatusField.text`.
- Do not change transcript, composer input, or command behavior.

## Public API

Extend `StatusField` from:

```python
@dataclass(frozen=True, slots=True)
class StatusField:
    text: str
    priority: int = 0
```

to:

```python
@dataclass(frozen=True, slots=True)
class StatusField:
    text: str
    priority: int = 0
    token: str = ""
```

Extend `StatusBar` from:

```python
@dataclass(slots=True)
class StatusBar:
    fields: list[StatusField] | tuple[StatusField, ...] = field(default_factory=list)
```

to:

```python
@dataclass(slots=True)
class StatusBar:
    fields: list[StatusField] | tuple[StatusField, ...] = field(default_factory=list)
    separator: str = " | "
    style_mode: Literal["plain", "muted", "codex-like"] = "plain"
    theme: ThemeResolver | None = None
```

The default values are part of the compatibility contract.

## Rendering Rules

`StatusBar.render()` continues to choose fields using unstyled text:

1. sanitize is not added here; callers already pass display text
2. sort fields by descending priority
3. build joined candidates using the configured separator
4. choose the largest fitting priority-ordered set
5. if no set fits, use the highest-priority field text
6. truncate the unstyled selected text to target width
7. apply styles after selection and truncation

Because styling is applied after fitting, ANSI escape sequences must not affect
`visible_width()`.

Empty fields still render a blank single-line status result.

## Separator Behavior

`separator` is the exact string inserted between selected fields. The default is
`" | "`.

Examples:

- `separator=" | "` renders `model | branch | idle`
- `separator=" · "` renders `model · branch · idle`

Separators are omitted when only one field is selected.

When styling is enabled, separators are styled independently from fields.

## Styling Modes

`plain` is the compatibility mode:

- no field styling
- no separator styling
- no `statusBar.*` token resolution
- no default style fallback

`muted` and `codex-like` are styled modes:

- they resolve through the provided `ThemeResolver`
- they apply built-in default token styles when no theme override exists
- they must preserve readable output when `theme` is `None`

The TUI lane does not define product meaning for a token. It only treats token
strings as semantic identifiers used to build theme-token fallback chains.

## Theme Token Resolution

Status-bar token resolution uses existing theme primitives:

- `ThemeResolver`
- `ThemeStyle`
- `apply_theme_style`

For a field with `token="model"` and `style_mode="codex-like"`, resolve in this
order:

1. `statusBar.codexLike.model`
2. `statusBar.model`
3. `statusBar.codexLike.field`
4. `statusBar.field`
5. built-in style for `codex-like` and `model`
6. no style

For `style_mode="muted"` and `token="branch"`, resolve:

1. `statusBar.muted.branch`
2. `statusBar.branch`
3. `statusBar.muted.field`
4. `statusBar.field`
5. built-in muted style
6. no style

For separators in `codex-like`, resolve:

1. `statusBar.codexLike.separator`
2. `statusBar.separator`
3. built-in separator style
4. no style

For separators in `muted`, resolve:

1. `statusBar.muted.separator`
2. `statusBar.separator`
3. built-in separator style
4. no style

`plain` skips this whole process.

## Built-In Styled Defaults

The renderer must provide small built-in defaults so `style_mode` has visible
effect without requiring every app to define theme overrides. This is part of
the public behavior for `muted` and `codex-like`.

Required defaults:

- `codex-like` model: `{"foreground": "cyan"}`
- `codex-like` workspace: `{"foreground": "green"}`
- `codex-like` branch: `{"foreground": "yellow"}`
- `codex-like` session: `{"foreground": "bright_black"}`
- `codex-like` runtime running: `{"foreground": "green"}`
- `codex-like` runtime idle: `{"dim": True}`
- `codex-like` queue: `{"foreground": "magenta"}`
- `codex-like` message: `{"foreground": "bright_white"}`
- `codex-like` separator: `{"dim": True}`
- `muted` fields: `{"dim": True}`
- `muted` separator: `{"dim": True}`

If theme overrides are present, they take precedence over built-in defaults.
Built-ins are only used after the relevant theme-token fallback chain resolves
to no style.

## Token Normalization

The TUI API accepts token fragments without the `statusBar.` prefix:

- `model`
- `workspace`
- `runtime.idle`

If a caller passes a fully qualified token beginning with `statusBar.`, the
renderer strips exactly that prefix before constructing the normal status-bar
fallback chain. For example, `token="statusBar.model"` behaves the same as
`token="model"` and never resolves `statusBar.statusBar.model`.

If a caller passes a mode-qualified token such as `statusBar.codexLike.model`,
the renderer first tries that exact token, then strips `statusBar.codexLike.`
to the semantic fragment `model` and continues with the normal fallback chain.
This keeps exact custom tokens usable without making code-lane callers depend
on fully qualified tokens.

The implementation may de-duplicate repeated token probes. Observable behavior
must match the ordered fallback rules above.

Unknown tokens are allowed. They fall back to generic field styles or no style.

## Sanitized Extension Statuses

`FooterView._render_extension_statuses()` currently rebuilds `StatusField`
values after sanitizing text. It must preserve the new `token` field:

```python
StatusField(
    _sanitize_footer_text(status.text),
    priority=status.priority,
    token=status.token,
)
```

This keeps extension-provided status metadata intact.

## Error Handling

- `StatusBar.separator` may be an empty string; that is valid.
- Invalid `style_mode` values are rejected by type checking and should not need
  runtime normalization.
- Unknown tokens do not raise.
- If styling produces an empty style dict, render unstyled text.
- If a theme style includes unsupported keys, existing `apply_theme_style`
  behavior applies.

## Tests

Add or update tests in `tests/tui/test_footer_statusline.py` or a focused
`tests/tui/test_status_bar.py`.

Required coverage:

- default `StatusBar([StatusField("model")])` output is unchanged
- default separator remains `" | "`
- custom separator changes joined text
- priority fitting and fallback behavior remain unchanged
- `plain` mode ignores theme tokens and built-in styles
- tokenized fields render ANSI styling in `codex-like`
- tokenized separators render ANSI styling in `codex-like`
- `codex-like` renders built-in ANSI styling when `theme` is `None`
- `muted` renders built-in ANSI styling when `theme` is `None`
- theme overrides beat built-in styled defaults
- `token="statusBar.model"` behaves like `token="model"`
- `token="statusBar.codexLike.model"` resolves the exact token first, then
  falls back through the semantic `model` chain
- unknown tokens fall back safely
- width fitting ignores ANSI escape sequences
- `_render_extension_statuses()` preserves `StatusField.token`
- public exports still expose the updated classes

Regression command:

```bash
uv run pytest tests/tui/test_footer_statusline.py tests/tui/test_composer_bottom_frame.py -q
```

Focused lint:

```bash
uv run ruff check src/loushang/tui/ui_parts/status.py tests/tui/test_footer_statusline.py tests/tui/test_composer_bottom_frame.py
```

If a new focused status-bar test file is added, include it in both commands.

## Code Lane Handoff

The later code-lane product slice can rely on:

- `StatusField(token=...)`
- `StatusBar(separator=...)`
- `StatusBar(style_mode="plain" | "muted" | "codex-like")`
- `StatusBar(theme=ThemeResolver(...))`
- `plain` default compatibility
- styled token fallback under the `statusBar.*` namespace

The code lane should build product-specific fields outside `loushang.tui`, then
pass them into `StatusBar`. It should not import private helpers from
`status.py`.

## Acceptance Checklist

- Public API remains backward-compatible.
- Existing unstyled tests pass without expected-output churn.
- New styling tests prove semantic tokens work.
- The feature is fully contained in `loushang.tui.ui_parts`.
- The TUI PR documents that product settings work is deferred to the code lane.
