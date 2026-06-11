# TUI Widgets P1E Toast Design

## Status

Draft for spec review.

## Context

`loushang.tui` now has a broad reusable widget catalog:

- P0A foundation widgets: buttons, choices, fields, forms, dialogs.
- P0B small controls: badges, status pills, progress, key-value lists, toolbar.
- P0C light controls: menu, tabs, spinner.
- P1A data controls: table.
- P1B/P1C text and dialog inputs: textarea and question dialog.
- P1D hierarchy controls: tree view.

The remaining planned widget catalog still includes `Popover` and `Toast`.
`Popover` requires anchored overlay lifecycle decisions. `Toast` can deliver
value earlier as a pure renderable notification stack: product code can embed it
in a layout or open it through `SurfaceHost` without the widget owning surfaces,
timers, or global focus.

## Goals

- Add public `Toast` and `ToastStack` types.
- Represent non-blocking notifications with stable values, kind, title,
  message, creation time, optional TTL, and dismissibility.
- Render a deterministic stack of visible toasts under width and height
  constraints.
- Support local queue operations: push, dismiss, dismiss oldest, prune expired,
  clear, and inspect visible toasts.
- Keep expiration deterministic by injecting `now_ms`.
- Keep `ToastStack` terminal-pure: no stdout writes, no hardware cursor moves,
  no timer scheduling, no automatic render invalidation, and no overlay opening.
- Export the new API through `loushang.tui.ui_parts.widgets`,
  `loushang.tui.ui_parts`, and top-level `loushang.tui`.
- Add focused tests, docs, and a runnable example.

## Non-Goals

- Do not add `show_toast()` or any helper that opens `SurfaceHost` overlays.
- Do not add a `ToastManager` or global notification bus.
- Do not change `SurfaceHost`, `Tui`, `InputRouter`, `RenderLoop`, or scheduler
  behavior.
- Do not schedule timers or request redraws automatically when a toast expires.
  Callers remain responsible for deciding when to render again.
- Do not add mouse support, clickable close buttons, keyboard focus, or global
  input intents in this slice.
- Do not render Markdown, rich wrapping, progress bars, action buttons, or
  nested widgets inside a toast.
- Do not introduce new `InputIntentKind` values.

## Public API

Add `src/loushang/tui/ui_parts/widgets/toast.py`.

```python
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

ToastKind = Literal["info", "success", "warning", "danger"]
_NowMs = Callable[[], int]


@dataclass(frozen=True, slots=True)
class Toast:
    message: str
    title: str = ""
    kind: ToastKind = "info"
    value: str = ""
    duration_ms: int | None = 4000
    created_at_ms: int | None = None
    dismissible: bool = True


@dataclass(slots=True)
class ToastStack:
    toasts: Sequence[Toast] = ()
    max_visible: int = 3
    newest_on_top: bool = True
    empty_height: int = 0
    theme: ThemeResolver | None = None
    now_ms: _NowMs = _monotonic_ms
```

`Toast` is the immutable data item. `ToastStack` is the renderable widget and
owns local queue state.

The first public API should expose:

- `push(toast: Toast | str, **overrides) -> str`
- `dismiss(value: str) -> bool`
- `dismiss_oldest() -> bool`
- `clear() -> None`
- `prune_expired() -> int`
- `visible_toasts() -> tuple[Toast, ...]`
- `all_toasts() -> tuple[Toast, ...]`
- `render(constraints) -> RenderResult`

`push()` accepts either a `Toast` or a message string. When a message string is
passed, `overrides` may set any `Toast` field except `message`, for example:

```python
stack.push("Saved", kind="success", title="Config")
```

When a `Toast` is passed with overrides, apply the overrides with
`dataclasses.replace()` before normalization:

```python
stack.push(Toast("Saved", value="save"), kind="success")
```

Invalid override names should raise the normal `TypeError` produced by
`Toast(...)` or `dataclasses.replace()`.

`push()` returns the stored toast value so callers can dismiss generated-value
toasts later.

## Toast Normalization

`ToastStack` normalizes initial toasts and pushed toasts into stored `Toast`
instances.

Normalization rules:

- `value` identifies a toast for dismissal.
- Empty `value` is replaced with a deterministic generated value:
  `toast-1`, `toast-2`, and so on, scoped to the stack.
- Non-empty duplicate values raise `ValueError`.
- Generated values must not collide with explicit values already in the stack.
- `created_at_ms is None` is replaced with the stack's current `now_ms()` value.
- A normalization batch should call `now_ms()` once so multiple initial toasts
  created without timestamps share the same creation time.
- `duration_ms` must be `None` or a non-negative integer. Negative values raise
  `ValueError`.
- Unknown `kind` values raise `ValueError`.

`created_at_ms` defaults to `None`, not `0`, so ad hoc toasts created under the
real monotonic clock do not expire immediately. Tests and deterministic callers
can still pass explicit timestamps such as `created_at_ms=0`.

## Expiration And Visibility

Expiration is computed only when callers ask for it through `visible_toasts()`,
`prune_expired()`, or `render()`.

Each expiration-sensitive operation must sample `now_ms()` exactly once and use
that sampled value for the full operation. This keeps boundary behavior stable
when a caller-provided clock changes between calls.

A toast is expired when:

- `duration_ms is not None`; and
- `now_ms() - created_at_ms >= duration_ms`.

At the exact duration boundary, the toast is expired.

Visibility rules:

- Expired toasts are hidden.
- `duration_ms=None` toasts never expire automatically.
- `max_visible <= 0` renders no toasts and returns an empty visible tuple.
- `newest_on_top=True` renders the newest visible toasts first.
- `newest_on_top=False` renders the oldest visible toasts first.
- `max_visible` is applied after filtering expired toasts and applying render
  order.

`visible_toasts()` does not mutate the queue. `prune_expired()` removes expired
toasts from the queue and returns the number removed.

## Queue Operations

`push(toast)` appends to the queue and returns the stored value.

`dismiss(value)`:

- removes the matching toast when it exists and `dismissible=True`;
- returns `True` when a toast was removed;
- returns `False` for unknown values;
- returns `False` for matching non-dismissible toasts.

`dismiss_oldest()`:

- removes the oldest visible dismissible toast, regardless of render order;
- skips expired toasts and non-dismissible toasts;
- returns `True` when a toast was removed;
- returns `False` when no visible dismissible toast exists.

`clear()` removes all toasts, including non-dismissible toasts. It is an
administrative reset, not a user dismissal.

`all_toasts()` returns the stored queue in insertion order, including expired
toasts that have not been pruned.

## Rendering

`ToastStack.render(constraints)` returns one rendered line per visible toast.
The stack does not render borders, cards, close icons, or blank separators in
the first slice.

Default row shape:

```text
[info] Message
[success] Title: Message
```

Where:

- the prefix is `[{kind}]`;
- title is optional;
- an empty title renders only the message;
- an empty message is allowed and renders the prefix plus title when present;
- rows are truncated with `truncate_to_width(..., ellipsis="")` against
  `autowrap_safe_width(constraints.width)`;
- rendered line count never exceeds `constraints.max_height`;
- if no toast is visible, render `empty_height` blank lines, capped by
  `constraints.max_height`.

`empty_height` defaults to `0` so embedding a stack with no visible toasts does
not consume layout space. A caller can set `empty_height=1` if it wants stable
layout height.

Plain rendering must remain ASCII-first and readable without theme support.

## Theme Tokens

`ToastStack` accepts `ThemeResolver | None`.

Initial theme tokens:

| Token | Applies to |
| --- | --- |
| `widget.toast.info` | Informational toast prefix. |
| `widget.toast.success` | Successful toast prefix. |
| `widget.toast.warning` | Warning toast prefix. |
| `widget.toast.danger` | Dangerous or failed toast prefix. |
| `widget.toast.title` | Toast title segment. |
| `widget.toast.message` | Toast message segment. |

Kind tokens style only the `[{kind}]` prefix. `widget.toast.title` and
`widget.toast.message` style their respective text segments. Theme application
must preserve visible width after stripping ANSI control sequences.

## SurfaceHost Composition

P1E intentionally stops at a pure widget. Callers can still compose it with
existing primitives:

```python
stack = ToastStack()
stack.push("Saved", kind="success")
tui.show_overlay(
    stack,
    presentation="overlay",
    anchor="top-right",
    captures_focus=False,
    non_capturing=True,
)
```

The widget does not create, close, hide, or focus surfaces by itself. This keeps
surface lifecycle behavior centralized in existing `Tui` / `SurfaceHost` APIs
and leaves `Popover` design independent.

## Public Exports And Docs

Export `Toast`, `ToastKind`, and `ToastStack` from:

- `loushang.tui.ui_parts.widgets`
- `loushang.tui.ui_parts`
- top-level `loushang.tui`

Docs should:

- add a `P1E Toast Controls` section to `docs/en/reference/tui-widgets.md`;
- mirror it in `docs/zh-CN/reference/tui-widgets.md`;
- document queue operations, expiration, and the fact that Toast does not open
  overlays automatically;
- add theme tokens;
- remove `Toast` from the planned catalog, leaving `Popover`;
- add `examples/tui/50_widgets_toast.py`.

## Testing Strategy

Add `tests/tui/test_widgets_toast.py`.

Focused tests should cover:

- public re-exports from all three public modules;
- construction and normalization of generated values and timestamps;
- duplicate explicit value rejection;
- invalid kind and negative duration rejection;
- `push(Toast(...), **overrides)` replacement semantics;
- single-sample `now_ms()` behavior for visibility, pruning, and render;
- `visible_toasts()` expiration filtering without mutation;
- `prune_expired()` mutation and return count;
- `duration_ms=None` persistence;
- expiration boundary at `created_at_ms + duration_ms`;
- `max_visible` and `newest_on_top` ordering;
- `dismiss(value)`, `dismiss_oldest()`, non-dismissible behavior, and `clear()`;
- deterministic rendering for title/no-title rows;
- empty stack rendering with `empty_height=0` and `empty_height=1`;
- width and height constraints, including very narrow widths;
- theme token application and visible width preservation;
- example importability.

Adjacent tests should include existing small-control and hardening suites:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_hardening.py -q
```

Run full TUI tests before PR:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/50_widgets_toast.py docs
```

## Implementation Outline

1. Add failing export and construction tests.
2. Implement `toast.py` skeleton, normalization, exports, and basic queue
   operations.
3. Add failing expiration, ordering, and dismissal tests.
4. Implement expiration, ordering, dismissal, and pruning.
5. Add failing render and theme tests.
6. Implement deterministic rendering and theme token application.
7. Add docs and runnable example.
8. Run focused, adjacent, full TUI, and Ruff verification.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Toast accidentally becomes an overlay manager. | Keep P1E scoped to `ToastStack`; no `SurfaceHost` changes or helper APIs. |
| Real-clock defaults make tests flaky or toasts expire immediately. | Use injectable `now_ms`; normalize `created_at_ms=None` to the current stack time. |
| Generated values are unstable. | Generate monotonic stack-local values and return them from `push()`. |
| Dismissal is ambiguous with duplicate values. | Reject duplicate values during normalization and push. |
| Expiration mutates unexpectedly during render. | `visible_toasts()` and `render()` filter without mutation; only `prune_expired()` mutates. |
| The stack consumes layout space when empty. | Default `empty_height=0`; allow callers to opt into stable empty height. |
| Theme styling breaks width calculations. | Use existing `style_text`, `truncate_to_width`, and visible-width tests. |

## Success Criteria

- `Toast`, `ToastKind`, and `ToastStack` are exported from public TUI modules.
- Toast normalization creates stable values and timestamps.
- Duplicate values, invalid kinds, and negative durations are rejected.
- Expiration filtering is deterministic and non-mutating unless
  `prune_expired()` is called.
- Dismissal methods have explicit return semantics and respect
  `dismissible=False`.
- Rendering obeys width, height, ordering, and empty-height constraints.
- Theme tokens are deterministic and covered.
- Docs and example import tests pass.
- Existing TUI tests remain green.
