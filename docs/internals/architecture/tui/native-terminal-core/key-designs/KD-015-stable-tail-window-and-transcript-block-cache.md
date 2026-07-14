# KD-015: Versioned Rendered Segments

Status: Accepted for phased implementation.

## Purpose

Keep Working ticks, composer input, and streaming updates responsive after a
long live session without dropping, trimming, or rewriting transcript history.

This design changes only the internal representation of a rendered frame. It
does not add a transcript window, change Markdown boundaries, or change terminal
scrollback behavior.

## Problem

Committed transcript records already cache their rendered lines. The hot path
still performs linear work over every cached line on each frame:

```text
transcript blocks
-> one flat list
-> one flat RenderResult
-> finalize every logical line
-> compare every logical line
-> emit a small terminal update
```

After a session has accumulated thousands of logical rows, a Working tick or a
single input character therefore scales with historical transcript length even
though only the bottom frame changed.

## Decision

The renderer represents a frame as immutable, versioned segments. The coding TUI
uses three stable slots:

```text
committed transcript | active draft | bottom frame
```

An unchanged slot reuses the exact segment object from the last successfully
committed frame. Layout and render planning use segment row counts without
flattening segment contents. Only changed segments are finalized and compared
line by line.

The canonical record sequence and canonical rendered lines remain unchanged.
Concatenating all segments must produce the exact output of the existing flat
renderer.

## Segment Contract

Each rendered segment is an immutable snapshot containing:

- occurrence identity;
- render revision;
- immutable rendered rows;
- row count;
- terminal-image metadata required by the existing planner.

A reused segment revision is valid only when all inputs affecting its rendered
bytes remain unchanged, including source revision, width, theme, terminal
capabilities, cwd, and transcript projection generation.

Two equal-valued record occurrences remain two occurrences in canonical output.
Record separators are part of canonical segment composition and are emitted in
exactly one place. Empty records do not create phantom separators.

## Frame Contract

A planned logical frame contains:

- the ordered segment references;
- aggregate logical row count;
- declared cursor;
- the revision of the committed frame on which the plan is based.

The render loop may take the segment fast path only when the base revision is the
last successfully committed revision. Terminal flush success is followed by one
atomic render-loop commit of the frame, viewport, logical and hardware cursor,
high-water mark, and terminal-image metadata. A failed flush leaves that state
unchanged.

## Dirty Range

Segment identity proves only content reuse. Absolute position still matters.

- A Working tick or composer edit changes the bottom segment.
- A streaming chunk changes the draft segment.
- If a changed segment gains or loses rows, all later segments whose absolute
  positions move are part of the affected suffix even when their content is
  unchanged.
- A clean prefix may be skipped only when its segment revisions, order, and
  absolute starting rows are unchanged.

The existing append, protected-append, shrink, viewport, cursor, and terminal
operation semantics remain authoritative. The segment path computes equivalent
line facts without reading the stable prefix.

## Terminal Images

Terminal-image IDs and their row offsets are cached with the immutable segment.
Image deletion and changed-range expansion preserve the existing behavior.

If a row shift can move an image and the segment path cannot prove equivalent
delete and repaint operations, planning uses the existing full fallback.

## Fallback

The existing complete render, finalize, diff, and terminal-plan path remains the
correctness fallback. It is used for the first frame and whenever reuse cannot be
proven, including relevant resize, render-context invalidation, transcript
replacement, or visible surface composition.

Fallback is allowed to be linear in full history. The following steady-state
frames are not:

| Frame | Allowed row work |
| --- | --- |
| Working tick | bottom frame |
| Composer input | bottom frame |
| New chunk | active draft plus shifted bottom frame |
| No-op | none |

A pathological unfinished Markdown construct may keep the active draft large.
This phase does not invent a new Markdown boundary to split it.

## Implementation Boundary

This phase changes only:

- immutable rendered-line segment and segmented-line containers;
- transcript, layout, and no-surface composition preservation of segments;
- segment-aware finalize, diff, terminal-image lookup, diagnostics, and committed
  render-loop baseline;
- focused equivalence and performance tests.

It does not introduce:

- active-window eviction;
- Markdown semantic-group changes;
- scheduler interval changes;
- new terminal operations or product behavior.

## Correctness Oracle

For every optimized test frame:

```text
flatten(segmented raw frame) == legacy raw frame
flatten(segmented finalized frame) == legacy finalized frame
```

The optimized and legacy planners must also agree on changed range, viewport,
logical and hardware cursor, terminal operations, and terminal-image deletes.

The focused fixtures cover duplicate equal records, empty records and
separators, draft growth, bottom-frame cursor movement, row-count shifts, flush
failure, and an affected suffix containing a terminal image.

## Performance Acceptance

After an initial `4000 -> 1000 -> 1000 -> 10` render has successfully committed,
reset the counters and render a Working tick, one input character, one new chunk,
and a no-op frame.

The hard requirements are:

```text
stable committed rows read           = 0
stable committed rows materialized   = 0
full frame flatten calls              = 0
Working/input dirty rows              = O(bottom frame)
chunk committed render misses         = 0
no-op terminal operations             = 0
```

Wall-clock time is supporting evidence. Steady-state Working and input cost must
remain approximately constant as committed history grows.
