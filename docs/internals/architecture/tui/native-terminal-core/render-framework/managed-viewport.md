# Managed Viewport

## Purpose

Define when the render loop may update terminal rows in place and when it must
repaint runtime-owned visible rows.

The managed viewport is the range of terminal rows that the runtime can still
reason about after a successful frame. It is not the user's full terminal
scrollback and it is not the product transcript source of truth.

## Core Terms

- `viewport_top`: logical row shown at the top of the visible terminal viewport
  for the current frame.
- `previous_viewport_top`: viewport top from the last committed frame.
- `differential_viewport_top`: viewport top selected for partial diff updates
  that preserve the previous physical mapping when safe.
- managed viewport repaint: rewrite runtime-owned visible rows without clearing
  scrollback.
- resize repaint: rewrite runtime-owned visible rows after terminal size change;
  default policy may clear scrollback.
- recovery repaint: rewrite runtime-owned visible rows after an unsafe
  non-resize condition.

## Unsafe Partial Diff Cases

Partial changed-range updates are unsafe when the render loop cannot prove that
old logical rows still map to the same physical terminal rows.

Important unsafe cases:

- external stdout writes
- inferred user scrollback movement
- terminal width change
- non-Termux terminal height change
- changed range above the previous viewport top
- shrink that would move the natural viewport top upward
- explicit baseline reset from application state

## Repaint Trigger Classes

Internal triggers come from application state:

- transcript window replaced
- transcript window trimmed
- context compaction replacement
- explicit baseline reset

External triggers come from terminal or environment state:

- terminal resize
- external stdout
- inferred user scrollback movement
- explicit unsafe viewport marker

The distinction matters for diagnostics. Internal transcript-window trimming
uses `managed_viewport_repaint`, ordinary baseline reset uses
`baseline_repaint`, resize uses `resize_repaint`, and unsafe viewport recovery
uses `recovery_repaint`.

## Protected Append Admission

`protected_append_update` inserts newly appended rows above protected bottom
content, usually the composer or status area, while preserving bottom-frame
cursor placement.

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
14. The previous and current prefixes before `inserted_start` are equal.

If any condition fails, the render loop must continue to later strategies.

## Shrink Behavior

Shrinks have two distinct paths:

- `ShrinkViewportRepaintStrategy` uses `managed_viewport_repaint` when content
  shrink would move the natural viewport top above the previous viewport top.
  This avoids rewriting rows against a stale physical mapping.
- `ShrinkClearStrategy` uses `shrink_clear` when the changed range starts beyond
  the current line end and stale trailing rows must be cleared.

These paths remain separate because one protects viewport mapping, while the
other clears stale rows after a safe shrink.

## Changed Range Above Viewport

If the first changed row is above `previous_viewport_top`, partial diffing would
depend on rows that may no longer be visible or writable at the expected
physical position. The render loop must use `managed_viewport_repaint` with
reason `changed_range_above_viewport`.

## Clear Scrollback Policy

Steady-state managed viewport repaint and recovery repaint must not clear
scrollback unless policy explicitly allows it. Resize repaint may clear
scrollback by default for deterministic visual recovery.

Clear scrollback must remain visible in diagnostics through both policy and
whether the operation was emitted.
