# TUI RenderLoop Strategy Design

## Status

Draft for implementation planning.

## Context

`loushang.tui` already has a strong native terminal rendering model: line-level
diffing, managed viewport tracking, append fast paths, protected append for
streaming content above a bottom frame, cursor-only updates, synchronized flushes,
and playback-based tests. The main maintainability issue is that
`RenderLoop.plan()` encodes all render-path selection in one long decision chain.

That shape makes the behavior hard to change safely. The implementation works,
but the priority order between repaint, append, protected append, shrink, and
changed-range paths is implicit in source order. New contributors must read a
large function and several helpers to understand why a frame used a given
`operation_class`.

Long-session rendering is no longer the primary blocker. Coding mode now trims
the active transcript window on resume and renders active transcript tail rows
with stable line caches. The remaining performance work is regression protection,
not a full reactive render rewrite.

## Goals

- Make render-path selection explicit, testable, and easier to review.
- Preserve all existing terminal behavior and `operation_class` values.
- Keep `RenderLoop.commit()` as the only state-advancing step.
- Make strategy priority visible in one ordered declaration.
- Document the decision model well enough that a maintainer can diagnose a frame
  from `operation_class` without first reading `render_loop.py`.
- Add regression guards for active-window long-session rendering.

## Non-Goals

- Do not change public TUI APIs.
- Do not introduce character-level diffing.
- Do not rewrite the render system into a reactive framework.
- Do not refactor `Composer`, `InputRouter`, `SurfaceHost`, or widget APIs in
  this slice.
- Do not enable a production fallback that silently hides missing strategy
  coverage.

## Design Summary

Split `RenderLoop.plan()` into two phases:

1. Build a `RenderPlanContext` containing facts about the current frame.
2. Select a stateless strategy from an explicit `DEFAULT_STRATEGY_ORDER`.

The final shape is:

```python
def plan(self, size: TerminalSize) -> RenderDiagnostics:
    context = self._build_plan_context(size)
    runtime = self._plan_runtime()
    for kind in DEFAULT_STRATEGY_ORDER:
        strategy = DEFAULT_STRATEGIES[kind]
        if strategy.match(context, runtime=runtime):
            return strategy.plan(context, runtime=runtime)
    raise AssertionError("no render strategy matched")
```

The strategies are behavioral extraction, not a semantic rewrite. Existing helper
functions such as `_protected_append_plan()`, `_append_operations()`,
`_managed_viewport_repaint_operations()`, and `_changed_range_operations()` remain
available and should be moved only when doing so reduces coupling.

## Strategy Ordering

The priority order must be declared as data rather than hidden in list
construction:

```python
class RenderPlanStrategyKind(Enum):
    FIRST_RENDER = auto()
    TRANSCRIPT_WINDOW_TRIMMED_RESET = auto()
    BASELINE_RESET = auto()
    RESIZE_REPAINT = auto()
    UNSAFE_VIEWPORT = auto()
    NO_CHANGE = auto()
    APPEND = auto()
    PROTECTED_APPEND = auto()
    SHRINK_VIEWPORT_REPAINT = auto()
    SHRINK_CLEAR = auto()
    CHANGED_ABOVE_VIEWPORT = auto()
    CHANGED_RANGE = auto()


DEFAULT_STRATEGY_ORDER: tuple[RenderPlanStrategyKind, ...] = (
    RenderPlanStrategyKind.FIRST_RENDER,
    RenderPlanStrategyKind.TRANSCRIPT_WINDOW_TRIMMED_RESET,
    RenderPlanStrategyKind.BASELINE_RESET,
    RenderPlanStrategyKind.RESIZE_REPAINT,
    RenderPlanStrategyKind.UNSAFE_VIEWPORT,
    RenderPlanStrategyKind.NO_CHANGE,
    RenderPlanStrategyKind.APPEND,
    RenderPlanStrategyKind.PROTECTED_APPEND,
    RenderPlanStrategyKind.SHRINK_VIEWPORT_REPAINT,
    RenderPlanStrategyKind.SHRINK_CLEAR,
    RenderPlanStrategyKind.CHANGED_ABOVE_VIEWPORT,
    RenderPlanStrategyKind.CHANGED_RANGE,
)
```

`NO_CHANGE` intentionally covers both `cursor_update` and `noop`. Both paths
share the same admission condition, `changed_range is None`, and splitting them
would make priority more fragmented without improving clarity.

`SHRINK_VIEWPORT_REPAINT` covers the current
`viewport_top_decreased_after_shrink` managed viewport repaint path.
`SHRINK_CLEAR` covers the existing `operation_class="shrink_clear"` path.
`TRANSCRIPT_WINDOW_TRIMMED_RESET` is separate from ordinary baseline reset
because trimmed transcript windows currently use `managed_viewport_repaint`,
while other baseline resets use `baseline_repaint`.

## Strategy Contract

Strategies must be stateless. They can be shared across `RenderLoop` instances
and tests.

```python
class RenderPlanStrategy(Protocol):
    kind: ClassVar[RenderPlanStrategyKind]
    name: ClassVar[str]

    def match(
        self,
        context: RenderPlanContext,
        *,
        runtime: RenderPlanRuntime,
    ) -> bool: ...

    def plan(
        self,
        context: RenderPlanContext,
        *,
        runtime: RenderPlanRuntime,
    ) -> RenderDiagnostics: ...
```

Strategies may read runtime state through `RenderPlanRuntime`, but must not
mutate `RenderLoop`. They must not call `commit()`, clear reset reasons, or
advance cursor tracking. State changes remain in `RenderLoop.commit()`.

## RenderPlanContext

`RenderPlanContext` is eager in the first implementation. Lazy properties are not
part of this slice because active-window trimming already bounds the important
long-session path, and lazy cached properties would add complexity before a
measured need.

```python
@dataclass(frozen=True, slots=True)
class RenderPlanContext:
    size: TerminalSize
    result: RenderResult
    raw_current_lines: tuple[str, ...]
    current_lines: tuple[str, ...]
    previous_lines: tuple[str, ...]
    previous_size: TerminalSize | None
    declared_cursor: CursorDeclaration | None
    cursor: CursorDeclaration
    changed_range: tuple[int, int] | None
    first_changed: int | None
    last_changed: int | None
    appended_lines: int
    append_start: int | None
    viewport_top: int
    differential_viewport_top: int
    width_changed: bool
    height_changed: bool
    previous_kitty_delete_sequences: tuple[str, ...]
```

The context contains facts only. It should not expose helper methods that encode
strategy decisions. Derived fields such as `first_changed`, `last_changed`,
`appended_lines`, `append_start`, and `differential_viewport_top` are still facts:
they describe the frame once, so individual strategies do not recompute them and
accidentally drift from one another.

## RenderPlanRuntime

`RenderPlanRuntime` is a narrow facade over the loop. Passing the full
`RenderLoop` into strategies would make it too easy for strategies to rely on or
mutate unrelated internals.

It exposes:

- `previous_viewport_top`
- `previous_cursor_row`
- `previous_cursor_column`
- `hardware_cursor_row`
- `hardware_cursor_column`
- `working_area_high_water_mark`
- `termux_session`
- `clear_scrollback_policy`
- `baseline_reset_reason`
- `unsafe_viewport_reason`
- diagnostics builders for existing repaint and operation paths

The facade may delegate to private `RenderLoop` helpers during the initial
refactor. The important boundary is that strategies do not mutate loop state.

## Decision Cheat Sheet

| Scenario | Strategy | operation_class | Key condition |
| --- | --- | --- | --- |
| First render | `FirstRenderStrategy` | `first_render` | `previous_size is None` |
| Trimmed transcript reset | `TranscriptWindowTrimmedResetStrategy` | `managed_viewport_repaint` | `baseline_reset_reason.startswith("transcript_window_trimmed:")` |
| Ordinary internal baseline reset | `BaselineResetStrategy` | `baseline_repaint` | `baseline_reset_reason is not None` and not a trimmed transcript reset |
| Terminal resize | `ResizeRepaintStrategy` | `resize_repaint` | `width_changed or height_changed`, except Termux height-only |
| External unsafe viewport | `UnsafeViewportStrategy` | `recovery_repaint` | `unsafe_viewport_reason is not None` |
| No content change, cursor moved | `NoChangeStrategy` | `cursor_update` | `changed_range is None` and cursor differs |
| No content change, cursor stable | `NoChangeStrategy` | `noop` | `changed_range is None` and cursor stable |
| Pure tail append | `AppendStrategy` | `append_update` | first changed row is the old line count |
| Insert above protected bottom frame | `ProtectedAppendStrategy` | `protected_append_update` | protected append admission passes |
| Shrink would move viewport upward | `ShrinkViewportRepaintStrategy` | `managed_viewport_repaint` | current line count shrank and viewport top decreased |
| Shrink leaves stale trailing rows | `ShrinkClearStrategy` | `shrink_clear` | changed range starts past current line end after shrink |
| Changed row above visible viewport | `ChangedAboveViewportStrategy` | `managed_viewport_repaint` | `first_changed < previous_viewport_top` |
| Ordinary changed range | `ChangedRangeStrategy` | `changed_range_update` | normal diff path after earlier strategies decline |

Priority matters. For example, `transcript_window_trimmed + resize` must use the
trimmed-window managed repaint path, and ordinary `baseline_reset + resize` must
use baseline repaint, because internal transcript-window replacement is a
stronger signal than terminal-size repaint. `unsafe_viewport + append` must use
recovery repaint because appending against an unsafe physical viewport can
corrupt managed rows.

## Repaint Trigger Classes

Internal triggers come from application state:

- baseline reset requested by the app
- transcript window replaced
- transcript window trimmed
- compaction replacement

External triggers come from terminal or environment state:

- terminal resize
- inferred user scrollback movement
- external stdout writes
- any explicit viewport-unsafe marker

Docs and diagnostics should preserve this distinction. It explains why
`baseline_repaint`, `managed_viewport_repaint`, `resize_repaint`, and
`recovery_repaint` are separate even when they all rewrite runtime-owned rows.

## Protected Append Admission

`ProtectedAppendStrategy` uses the existing `_protected_append_plan()` rules.
All conditions must hold:

1. A cursor is declared.
2. `appended_lines > 0`.
3. `len(current_lines) >= size.rows`.
4. `inserted_start = first_changed`.
5. `inserted_end = inserted_start + appended_lines`.
6. `inserted_start > 0`.
7. `inserted_end < len(current_lines)`.
8. `inserted_start <= len(previous_lines)`.
9. `protected_start = inserted_end`.
10. `protected_height = len(current_lines) - protected_start`.
11. `protected_height > 0`.
12. `protected_height < size.rows`.
13. `cursor.row >= protected_start`.
14. `previous_lines[:inserted_start] == current_lines[:inserted_start]`.

If any condition fails, the render plan must continue to the next strategy.

## Fallback Strategy

Do not include fallback repaint in `DEFAULT_STRATEGY_ORDER`.

A `FallbackRepaintStrategy` may exist for explicit emergency or debug use, but a
missing match in the default registry should raise `AssertionError`. Silent
fallback repaint would hide strategy coverage bugs and make regressions harder to
find. Tests must prove the default registry is complete for the supported frame
states.

If implemented, fallback diagnostics should use
`operation_class="fallback_repaint"` and `repaint_reason="strategy_fallback"` so
it is visible in telemetry and playback output.

## Documentation Work

Add or update:

- `docs/internals/architecture/tui/native-terminal-core/render-framework/render-loop.md`
- `docs/internals/architecture/tui/native-terminal-core/render-framework/managed-viewport.md`

`render-loop.md` must cover:

- RenderLoop responsibilities
- frame construction
- strategy ordering
- Decision Cheat Sheet
- each `operation_class`
- failure and commit semantics
- cursor positioning model
- Kitty image cleanup interaction

`managed-viewport.md` must cover:

- viewport top and previous viewport top
- when partial diffing is unsafe
- protected append admission
- managed viewport repaint triggers
- shrink clear behavior
- resize repaint versus recovery repaint policy
- internal versus external repaint triggers

## Test Plan

Keep `tests/tui/test_render_loop.py` as the primary behavior regression suite.
Existing operation-class assertions should continue to pass.

Add focused tests for:

- `DEFAULT_STRATEGY_ORDER` matches the documented order.
- `transcript_window_trimmed + resize` chooses trimmed-window managed repaint
  before resize.
- ordinary `baseline_reset + resize` chooses baseline reset before resize.
- `unsafe_viewport + append` chooses recovery repaint before append.
- `changed_range is None` chooses `cursor_update` or `noop`.
- protected append admission conditions, preferably parameterized around the
  existing `_protected_append_plan()` rule set.
- shrink viewport repaint and shrink clear stay distinct.
- default strategy registry is complete for existing supported scenarios.
- optional `FallbackRepaintStrategy` is not in the default order.

Add or tighten performance guards in
`tests/coding/test_native_coding_tui_perf_probe.py`:

- after active window trim, composer input does not increase render-loop logical
  line count
- after active window trim, logical line count remains bounded by a fixed budget
  derived from `active_transcript_line_budget`
- stable historical transcript blocks are not re-rendered during ordinary
  composer edits or timer ticks, where that can be asserted without fragile
  timing thresholds

## Implementation Phases

Phase 1: Extract facts.

- Introduce `RenderPlanContext`.
- Keep `RenderLoop.plan()` behavior in one function.
- Replace local variables with context fields.
- Run render-loop and coding perf tests.

Phase 2: Extract simple strategies.

- Add strategy kinds, default order, and stateless strategy protocol.
- Extract first render, resize repaint, unsafe viewport, and no-change
  strategies.
- Keep baseline reset and complex diff paths inline until the simple path is
  proven. Baseline reset is intentionally delayed because trimmed transcript
  reset uses managed viewport repaint while ordinary baseline reset uses
  baseline repaint.
- Run render-loop tests after each extraction.

Phase 3: Extract complex strategies and docs.

- Extract transcript-window-trimmed reset, ordinary baseline reset, append,
  protected append, shrink viewport repaint, shrink clear, changed-above-viewport,
  and changed-range strategies.
- Add render-loop and managed-viewport docs.
- Add strategy boundary tests and performance guards.
- Run targeted TUI tests and coding perf probes.

## Success Criteria

- `RenderLoop.plan()` is small and delegates strategy selection.
- Strategy order is visible in one declaration and tested.
- Every existing `operation_class` remains compatible.
- Existing playback and render-loop tests pass.
- Long-session perf probes pass and include bounded logical-line assertions.
- A maintainer can map any frame's `operation_class` to the responsible strategy
  and key admission condition from docs without first reading `render_loop.py`.
