# Layout Requirements

## Purpose

This document describes the required screen layout for the native terminal core.
It defines regions and ownership. It does not prescribe concrete Python classes.

## LR-001: Terminal Is Not Fullscreen Alternate Screen

The TUI must run in the user's normal terminal scrollback. It must not require an
alternate-screen fullscreen application for the primary coding workflow.

## LR-002: Screen Regions

The screen is organized into conceptual regions:

```text
header_area
transcript_render_area
pending_queue_area
working_line_area
widget_slot_above_composer
surface_area
composer_area
widget_slot_below_composer
separator_area
status_area
```

The header and transcript render areas are backed by normal terminal scrollback
unless an explicit layout policy makes them transient. The remaining regions are
runtime-owned transient UI.

The screen root composes these regions through a screen region stack. Product
adapters may omit optional regions, but the bottom status area remains the last
visible row in the default coding layout.

## LR-003: Status Area

The status area is the last visible row by default. It must stay one terminal
line. Lower-priority fields are omitted or truncated when space is constrained.
The status row must not wrap, and the default renderer must avoid writing into
the final terminal cell to prevent bottom-row autowrap artifacts.

## LR-004: Composer Area

The composer area is directly above the separator and status areas. It is
prefixed with `>` or the configured product prompt marker and supports both soft
wrapping and explicit newlines.

When the input grows to multiple visual lines, the composer grows upward. The
status row remains fixed at the bottom.

## LR-005: Separator Area

The default coding layout keeps one blank separator line between composer and
status. Product adapters may hide the separator only through explicit layout
configuration.

## LR-006: Working Line

While a run is active, a transient working line appears above the composer block.
It is not committed transcript content while active.

When queued follow-up, pending steering, or other pending actions are visible,
they appear in a pending queue area above the working line. The pending queue
grows upward as items are added so the composer, separator, and status rows
remain anchored at the bottom.

Example:

```text
Working 3.01s
```

When the run completes, the product adapter may commit a stable worked divider to
the transcript.

## LR-007: Surface Area

Surfaces such as autocomplete, command palette, settings, selectors, and dialogs
are hosted above the composer. Non-overlay surfaces render in the surface area.
Overlay surfaces are positioned by the surface host according to layout policy.
A surface may capture focus, but it must not own the terminal writer.
If surface content exceeds available height, it must scroll internally, paginate,
or truncate without displacing the composer and status minimum rows.

## LR-008: Height-Constrained Layout

When terminal height is constrained, the default coding layout preserves the
status row and at least one composer row before optional regions. Separator,
widget slots, pending queue, working line, surface area, transcript render area,
and header area shrink or hide according to KD-008.

## LR-009: Extension Widget Slots

Optional widget slots may appear above or below the composer for product or
extension-provided transient UI. Widget slots must remain runtime-owned regions:
they receive renderables or UI parts and must not write to the terminal.

## LR-010: Transcript Block Layout

Stable transcript content is rendered as readable blocks:

```text
> user prompt

* assistant response

- Worked for 4m 56s ---------------------------------------------
```

The exact markers are theme/product configurable, but their meanings must remain
stable.
