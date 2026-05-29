# KD-001: Render Loop And Terminal Writer

## Purpose

Define the runtime mechanism that keeps terminal rendering stable.

## Design

The runtime owns the only terminal writer. Renderables and UI parts return render
results, intents, or state changes. They never write stdout, move the hardware
cursor, or clear lines directly.

## Tick Triggers And Coalescing

Render ticks are requested by:

- input events that change editor state, focus, surface state, or cursor position
- product events such as transcript records, streaming chunks, tool updates,
  status changes, and run lifecycle changes
- terminal signals such as resize, suspend/resume, and capability changes
- timer-driven UI such as loaders or elapsed-time indicators
- explicit invalidation after theme or layout policy changes

The scheduler must coalesce high-frequency product events and timer updates so a
burst of streaming chunks does not starve keyboard handling. Input echo and
cursor movement have priority over cosmetic timer updates. A render request may
be dropped only if a newer request supersedes it before a flush begins.

The render loop is line-diff based. It compares logical lines and emits
line-level terminal operations. It does not attempt character-level terminal diff
inside a line.

## Core Mechanisms

The render loop should use these stable terminal mechanisms:

- full logical-line buffer: every render produces current logical lines
- previous-line snapshot: successful flushes update previous rendered lines
- line-level changed range: first/last changed rows drive terminal operations
- append update: newly appended content lets the terminal scroll naturally
- synchronized flush: one buffered terminal update per render tick when supported
- overlay composition before diff: base lines and active overlays are composed
  before changed-range detection
- cursor marker extraction: focused input may declare cursor position by render
  result metadata or by a zero-width cursor marker that the runtime strips
- hardware cursor masking: when a focused input cursor is present, the runtime
  hides the hardware cursor before terminal writes, positions it after the
  synchronized render block, then restores visibility so intermediate cursor
  movement is not visible
- viewport-relative cursor placement: after a render frame, logical cursor row
  is mapped through `Viewport Top` to an absolute visible terminal row before
  moving the hardware cursor. This avoids terminal autowrap or IME behavior on
  the final written line from shifting the next input render one row off.
- non-padded logical lines: ordinary UI parts return actual content lines and
  rely on the render loop's clear-line operation to erase stale content. They
  should not pad every line to terminal width, because writing the final terminal
  cell can create autowrap drift in normal scrollback terminals.
- screen region stack: header, transcript, pending, working, widgets, composer,
  separator, and status are composed in a stable order

Each render tick:

1. Reads the current terminal size.
2. Renders the screen root into current logical lines.
3. Composites active overlays.
4. Extracts and strips cursor markers.
5. Normalizes ANSI reset state.
6. Compares current logical lines with previous rendered lines.
7. Plans terminal operations from the changed line range.
8. Emits one synchronized flush through TerminalPort.
9. Positions the hardware cursor after render writes have completed.
10. Updates previous rendered lines, viewport tracking, and cursor tracking only
   after the flush succeeds.

## Required Paths

- first render: write current logical lines without clearing previous shell
  scrollback
- first render may emit a leading newline when needed to avoid overwriting a
  non-empty shell cursor line
- append update: append only new lines when the changed range starts at the end
  of previous rendered lines
- changed range update: rewrite only visible changed rows
- viewport-shrink recovery: when content shrink would move the natural viewport
  above the previous viewport anchor, use synchronized recovery repaint of the
  managed viewport instead of a partial diff. This prevents stale composer or
  status rows from remaining after a transient working line becomes a committed
  worked divider.
- recovery repaint: rebuild runtime-owned managed rows when safe diffing is not
  possible
- resize repaint: full repaint of runtime-managed visible UI after terminal
  width or height changes
- clear scrollback: policy-controlled operation; enabled by default for
  resize repaint and disabled for steady-state diff updates

## Test Obligations

- renderables cannot reach TerminalPort
- no steady-state clear-screen or clear-scrollback operations
- changed line range updates only changed rows
- append update lets terminal scroll naturally
- overlays are composed before changed-range detection
- failed flush does not advance previous rendered lines
- high-frequency streaming chunks are coalesced without delaying input echo
