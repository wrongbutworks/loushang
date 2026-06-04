# KD-008: Bottom Frame Layout

## Purpose

Specify the default coding layout so the bottom frame remains stable.

## Design

The default screen region stack is:

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

The status area is the last visible row. The separator area defaults to one blank
line above the status row. The composer grows upward. Pending queues and working
line appear above the composer without moving the status row.

Product adapters may omit optional regions or choose a custom layout policy, but
they must preserve runtime ownership of transient regions and terminal writer
rules.

## Height-Constrained Region Priority

The default coding layout uses this priority when height is constrained:

| Region | Minimum | Rule |
| --- | --- | --- |
| status_area | 1 row | Preserve as the last visible row unless status is explicitly disabled. |
| composer_area | 1 row | Preserve enough space for prompt marker and current cursor line. |
| separator_area | 0 rows | First region to collapse; default is one blank row when space allows. |
| widget_slot_below_composer | 0 rows | Hide before reducing composer minimum. |
| widget_slot_above_composer | 0 rows | Hide before reducing composer minimum. |
| pending_queue_area | 0 rows | Show newest/highest-priority pending items first; truncate or hide the rest. |
| working_line_area | 0 rows | May be hidden under extreme height pressure after status and composer are preserved. |
| surface_area | 0 rows | Surfaces must scroll internally, paginate, overlay, or close rather than displacing composer/status minimum rows. |
| transcript_render_area | 0 rows | May naturally scroll out of the visible viewport. |
| header_area | 0 rows | Startup/header content is lowest priority after it has been rendered. |

If the terminal is too short to show both status and a one-row composer, the
runtime enters a constrained emergency layout and must prefer preserving input
and terminal restoration over decorative UI.

Emergency layout still tries to preserve a one-row status and a one-row composer.
If even two rows are unavailable, the composer takes precedence and the status
row is omitted until height recovers.

## Status Truncation

Status fields are ordered by product-provided priority. The renderer omits
lower-priority fields before truncating a visible field. A visible field
truncates from the middle when it represents a path or identifier and from the
right for ordinary labels. The status row must not wrap. The default status
renderer reserves the last terminal cell instead of padding to full width so the
bottom row cannot trigger terminal autowrap before cursor repositioning.

## Test Obligations

- one-line composer leaves one blank separator above status
- multi-line composer grows upward
- working line appears above the composer with a preceding visual gap
- pending queue appears above working line and grows upward
- status truncates or omits fields instead of wrapping
- constrained height follows the region priority table
