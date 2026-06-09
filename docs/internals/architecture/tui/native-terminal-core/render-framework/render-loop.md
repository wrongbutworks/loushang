# Render Loop

## Purpose

Define how the native terminal core turns a renderable tree into a stable
terminal frame.

The render loop owns render planning and terminal operation selection. It does
not own product state, transcript history, input routing, or terminal writes.
Terminal writes remain the responsibility of the runtime and terminal port.

## Responsibilities

Each frame:

1. Renders the screen root with terminal width and visible height.
2. Captures raw rendered lines from the `RenderResult`.
3. Finalizes lines by preserving terminal reset state across frames.
4. Normalizes the declared cursor into a logical cursor.
5. Computes changed-line facts against the previous successful frame.
6. Selects one render planning strategy in priority order.
7. Returns `RenderDiagnostics` with terminal operations and frame metadata.

`RenderLoop.commit()` is the only step that advances render-loop state. A plan
that is never flushed or never committed must not update previous rendered
lines, viewport tracking, hardware cursor tracking, or reset reasons.

## Frame Facts

`RenderPlanContext` contains facts about the current frame:

- current and previous logical lines
- current and previous terminal size
- declared cursor and normalized logical cursor
- changed-line range
- append counts and append start
- natural viewport top and differential viewport top
- resize flags
- previous Kitty image cleanup sequences

These are facts, not decisions. Strategy code may consume them, but should not
recompute them independently.

`RenderPlanRuntime` exposes prior loop state and diagnostic builders:

- previous viewport top
- previous logical cursor position
- previous hardware cursor position
- clear-scrollback policy
- baseline reset reason
- unsafe viewport reason
- diagnostic construction helpers

Strategies must be stateless and must not mutate `RenderLoop`.

## Strategy Order

Render strategy priority is explicit:

| Order | Strategy | operation_class |
| --- | --- | --- |
| 1 | `FirstRenderStrategy` | `first_render` |
| 2 | `TranscriptWindowTrimmedResetStrategy` | `managed_viewport_repaint` |
| 3 | `BaselineResetStrategy` | `baseline_repaint` |
| 4 | `ResizeRepaintStrategy` | `resize_repaint` |
| 5 | `UnsafeViewportStrategy` | `recovery_repaint` |
| 6 | `NoChangeStrategy` | `cursor_update` or `noop` |
| 7 | `AppendStrategy` | `append_update` |
| 8 | `ProtectedAppendStrategy` | `protected_append_update` |
| 9 | `ShrinkViewportRepaintStrategy` | `managed_viewport_repaint` |
| 10 | `ShrinkClearStrategy` | `shrink_clear` |
| 11 | `ChangedAboveViewportStrategy` | `managed_viewport_repaint` |
| 12 | `ChangedRangeStrategy` | `changed_range_update` |

The default strategy registry must not include an emergency fallback strategy.
If no default strategy matches, the render loop should raise an assertion. That
exposes missing coverage instead of silently turning logic gaps into repaint
behavior.

## Decision Cheat Sheet

| Scenario | Strategy | Key condition |
| --- | --- | --- |
| First render | `FirstRenderStrategy` | `previous_size is None` |
| Trimmed transcript reset | `TranscriptWindowTrimmedResetStrategy` | reset reason starts with `transcript_window_trimmed:` |
| Ordinary baseline reset | `BaselineResetStrategy` | reset reason exists and is not a trimmed transcript reset |
| Terminal resize | `ResizeRepaintStrategy` | width changed, or height changed outside Termux |
| Unsafe viewport | `UnsafeViewportStrategy` | unsafe viewport reason exists |
| Cursor-only update | `NoChangeStrategy` | no changed range and logical cursor changed |
| No-op | `NoChangeStrategy` | no changed range and logical cursor stayed put |
| Pure append | `AppendStrategy` | append starts exactly at the old line count |
| Protected append | `ProtectedAppendStrategy` | appended content fits above protected bottom rows |
| Shrink moves viewport up | `ShrinkViewportRepaintStrategy` | line count shrank and natural viewport top decreased |
| Shrink clears stale rows | `ShrinkClearStrategy` | changed range starts beyond current line end after shrink |
| Change above viewport | `ChangedAboveViewportStrategy` | first changed row is above previous viewport top |
| Ordinary diff | `ChangedRangeStrategy` | changed range remains after earlier strategies decline |

## Cursor Model

Renderable output may declare a cursor in `RenderResult`. The render loop also
normalizes a missing cursor to the end of the last logical line so cursor-only
updates can be compared consistently.

Hardware cursor movement is planned after render writes. Cursor row placement is
viewport-relative: the logical cursor row is mapped through the selected
viewport top before terminal cursor movement is emitted.

## Kitty Image Cleanup

Changed and repaint paths must delete previous Kitty image placements that can
be invalidated by the planned frame. Repaint paths use cleanup sequences from
the previous frame. Changed-range and shrink paths use range-specific cleanup.

## Failure And Commit Semantics

Planning is side-effect-light. It may cache the raw planned lines for a future
commit, but it must not advance previous rendered lines or clear reset reasons.

Only `commit()` updates:

- previous rendered lines
- previous raw lines
- previous terminal size
- previous viewport top
- hardware cursor row and column
- previous logical cursor row and column
- working-area high-water mark
- baseline reset and unsafe viewport reasons
