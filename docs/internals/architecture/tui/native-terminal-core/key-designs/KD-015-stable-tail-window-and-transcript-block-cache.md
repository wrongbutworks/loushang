# KD-015: Stable Tail Window And Transcript Block Cache

## Purpose

Keep input echo and timer-driven updates responsive when transcript history is
long, without making the managed viewport jump or flash.

## Problem

The native coding TUI already renders transcript content from the tail, but the
render loop still plans against an effectively unbounded `max_height`. In a long
session, that makes each input edit or working-timer tick materialize thousands
of logical transcript lines before diffing. The result is that transient updates
scale with historical transcript size instead of visible viewport size.

The issue is not that committed transcript records are still changing. For a
stable record, rendered lines are functionally stable as long as these inputs do
not change:

- transcript record data
- render width
- theme and terminal capabilities
- transcript presentation policy such as thinking visibility
- cwd-dependent display normalization
- transcript window generation

That stability allows the runtime to cache historical transcript blocks and plan
only against an active tail window.

## Design

The transcript source of truth remains the full display-record sequence. The
runtime must add a second layer between transcript records and render planning:

- stable transcript block cache: cached rendered lines for committed blocks
- transcript block index: block boundaries plus cumulative logical line counts
- active tail window: the only transcript logical lines exposed to the render
  loop during steady-state planning

The render loop must no longer require the screen root to materialize the full
logical transcript on every tick. Instead, the transcript region provides a
stable tail window composed from cached historical blocks plus transient tail
content.

Transcript window generation is a monotonic invalidation token owned by the
product-facing transcript window. It changes whenever transcript window
membership or transcript presentation state is replaced in a way that makes
previous stable-block cache entries unsafe to reuse as-is. Typical generation
changes include transcript window replacement, transcript compaction replacement,
resume-time transcript projection rebuild, or explicit transcript presentation
policy replacement.

## Stable And Transient Content

Stable content includes:

- user prompt records
- committed assistant message records
- committed tool execution records
- committed thinking records
- worked divider and compaction records

Transient content includes:

- streaming assistant draft buffers
- active tool-progress rows if they are still mutating
- bottom-frame content such as working line, composer, pending queue, and
  statusline

Only transient content may re-render on every frame by default. Stable content
must be reused from cache whenever its render key remains unchanged.

## Block Boundaries

The runtime must cache transcript content by stable block, not by the final
flattened logical line array.

A block is the smallest committed transcript unit whose rendered lines are
expected to remain internally consistent across steady-state frames. In the
native coding TUI, the default block boundary is one committed display record.
If future product rendering composes multiple records into one semantic unit,
that unit must still render and invalidate as one block.

The product adapter or transcript projection layer owns block-boundary
definition. The runtime consumes committed blocks and must not invent new
multi-record semantic blocks by inspecting rendered lines. The runtime may index
and cache blocks, but block identity and grouping come from transcript
projection, not from render-time heuristics.

The active tail window must be selected in block units. It must never slice into
the middle of a block only because a raw line budget was hit. If the window
budget boundary falls inside a block, the runtime must include the entire block
or exclude it entirely according to bottom-anchored window selection policy.

## Tail Window Policy

The transcript region must expose an active tail window with these properties:

- bottom anchored: the newest committed or transient transcript content stays at
  the bottom edge of the transcript window
- visible-height preserving: the visible transcript rows always come from the
  active tail window
- guard-banded: the runtime keeps additional historical rows above the visible
  viewport so small tail changes do not force immediate window replacement
- block-stable: window membership changes only on block boundaries

For coding mode, the initial sizing target is:

- visible transcript height driven by layout and commonly reaching about 80
  rows, as a tunable default rather than a hard-coded invariant
- guard band of roughly one additional visible-height above the viewport
- active tail window of about two visible-heights, subject to tuning

Exact line counts are policy, not API, but the guard band must be large enough
that ordinary input edits, streaming chunk completion, and working-line timer
updates do not churn window membership.

On extremely short terminals, the active tail window may collapse to only a few
rows because it remains derived from current visible layout height. This is
acceptable as long as the same bottom-anchored and block-stable rules still
apply.

## Render Planning Contract

During steady-state diff planning, the render loop must only see:

- active transcript tail window logical lines
- current bottom-frame logical lines
- active overlays

Historical transcript content outside the active tail window remains part of the
product state, but not part of the render loop's steady-state logical line
buffer.

The runtime must still retain enough metadata to:

- rebuild a larger or different tail window after resize or policy changes
- rebuild the active window after theme or capability invalidation
- export or inspect the full transcript outside the live render path

Window selection must avoid per-frame linear rescans over the entire transcript.
The expected mechanism is a block index with cumulative logical line counts so
tail-window selection is driven by indexed lookup plus a bounded walk over the
blocks that actually enter the active window. The exact data structure is an
implementation choice, but steady-state selection must scale with active-window
size rather than total transcript history length.

## Invalidation Rules

Stable block cache entries must be invalidated when any render key input changes:

- width change
- theme change
- terminal capability change
- transcript presentation policy change such as thinking visibility
- cwd-dependent display normalization change
- transcript window generation reset or replacement
- block data replacement by transcript reprojection

Steady-state transient updates such as:

- composer edits
- working timer ticks
- pending-queue changes
- streaming draft chunk appends

must not invalidate unrelated historical stable blocks.

Committed blocks remain immutable in place. Block data replacement means that a
new transcript projection replaces a previously committed block at the transcript
state level; it does not authorize mutating a committed block instance after
commit.

Height-only resize does not invalidate stable block cache entries by itself. It
may change visible transcript height, guard-band sizing, and active tail window
membership, but cached block renderings remain reusable when width and other
render-key inputs are unchanged. Width resize invalidates stable block cache
entries and follows the KD-007 reflow path.

The block index must cover the full committed transcript. The stable block cache
does not need to hold rendered lines for the full transcript indefinitely.
Implementations may evict cached renderings outside the active window, guard
band, or recent reuse set, as long as the index remains sufficient to rebuild
them deterministically on demand.

## Window Replacement And Repaint Policy

When the active tail window membership stays within the current guard band, the
runtime should continue using line-diff updates normally.

When membership must change because the tail moved beyond the guard band, the
runtime must treat that as a managed tail-window replacement, not as an ordinary
small changed-range update. In that case:

- the new active window is selected on block boundaries
- the viewport remains bottom anchored
- the runtime may use a managed baseline repaint of runtime-owned visible rows
  instead of a fine-grained diff against the previous window contents

This repaint is a controlled runtime repaint, not a resize clear-scrollback
operation. It must preserve the no-flash and no-history-duplication guarantees
already defined by the managed viewport design.

The runtime must use a deterministic, testable policy for deciding between
tail-window replacement repaint and ordinary diff. The design does not require a
single global threshold constant, but the default policy must be anchored in
window-membership change and guard-band exhaustion rather than ad hoc judgment.

## Non-Goals

This design does not require:

- replaying terminal scrollback as runtime state
- character-level incremental transcript diff
- preserving full historical logical lines inside the steady-state render loop
- solving width-reflow by partial reuse across resize

Resize remains a separately defined repaint path.

## Relationship To Existing Designs

- KD-001 remains responsible for scheduling, line diffing, and terminal writes.
  KD-015 narrows what logical lines are presented to that render loop during
  steady state.
- KD-004 remains responsible for managed viewport ownership, recovery repaint,
  and scrollback policy. KD-015 adds a tail-window replacement path that uses
  those repaint rules.
- KD-006 remains responsible for stable versus transient transcript lifecycle.
  KD-015 builds on that distinction to define what may be cached and what must
  stay live.
- KD-007 remains responsible for resize-stable reflow. KD-015 relies on KD-007
  for width-driven cache invalidation and repaint, while allowing height-only
  resize to resize the active tail window without invalidating stable block
  renderings.
- KD-008 remains responsible for visible transcript height after bottom-frame
  layout. KD-015 uses that visible height to size the tail window and guard
  band.

## Test Obligations

- steady-state composer edits do not scale render planning with total transcript
  history size
- working-timer ticks do not invalidate historical stable transcript blocks
- render diagnostics or perf probes can prove that steady-state planning touches
  only the active tail window plus bounded block-index lookup work
- active tail window membership changes only on block boundaries
- tail-window replacement preserves bottom anchoring and does not duplicate
  transcript content
- guard band prevents immediate window replacement on small transient tail
  changes
- width/theme/capability/cwd invalidation rebuilds cached stable blocks
  deterministically
- resize still uses the existing repaint path rather than stale stable-block
  reuse
