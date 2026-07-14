# KD-019: Streaming Markdown Stable Prefix Cache

Status: Accepted. Implemented.

## Purpose

Keep Markdown streaming responsive as an assistant draft grows by parsing and
formatting only its mutable semantic tail, while reusing already rendered
semantic groups as immutable line segments. Terminal output, viewport, and
scrollback behavior do not change.

## Problem

`StreamingTextBuffer` receives append-only chunks, but each rendered version is
currently joined into the full draft and passed through the full Markdown
parser. The existing `MarkdownRenderCache` can reuse formatted stable blocks,
but it runs after the full parse, which remains the dominant growing cost.

## Decision

Borrow Claude Code's stable-prefix strategy, adapted to Loushang's flat
renderer.

Each active streaming draft keeps a small parse state:

- the draft buffer identity and previous source
- a source-line offset marking the end of the stable prefix
- parsed top-level block groups before that offset, including the source gap at
  the stable/tail boundary

For an append-only update:

1. Parse only the source at or after the stable offset.
2. Group markdown-it tokens by top-level Markdown block and rebase their local
   line ranges to full-source line numbers.
3. Keep the final two non-blank top-level groups at the mutable frontier: the
   growing tail plus one group of lookbehind.
4. Promote all earlier complete groups into the stable prefix and advance the
   source-line offset.
5. Render each promoted group once as an immutable line segment, and render the
   remaining groups as one versioned mutable frontier segment.

Stable groups and the frontier are internal render segments, not separate
transcript records or terminal regions. Concatenating their rows must equal the
ordinary complete Markdown render exactly.

Each group owns its left boundary: either the source-gap blank before it or the
Pi-style blank implied by the previous and current block kinds. It never owns a
trailing blank that depends on future input. This makes a promoted group safe
to freeze without duplicating or dropping boundary rows.

## Semantic Boundary

The stable boundary comes from top-level markdown-it token line ranges. It is
never selected by a fixed line count, byte count, chunk count, or timer.

The last top-level list, table, block quote, fenced code block, or paragraph
remains mutable as one unit. A single continuously growing block therefore
remains correct but receives little or no incremental benefit.

The one-group lookbehind handles Markdown constructs that can merge backward
at the input frontier. For example, a partial ordered-list marker is initially
a paragraph and may join the preceding list when its punctuation arrives.

Promotion is allowed only where parsing the prefix and tail separately is
equivalent to parsing the complete source. If a construct has document-wide
effects, such as a reference definition that can change an earlier block, the
implementation keeps the stable offset at zero and uses the existing full
parse path.

## Reset And Completion

Discard the incremental state when:

- the active buffer changes
- the source is no longer an append of the previous source
- the parser cannot provide a safe top-level source boundary

When streaming completes with the same buffer identity, version, and text as
the last rendered frame, flatten the proven-equivalent rendered segments once
into the stable record cache. Replaced or not-yet-rendered final text uses the
ordinary full Markdown path. Then discard the streaming state.

Width, theme, and terminal-capability changes continue to invalidate rendered
line caches through their existing keys. They do not change Markdown source
boundaries and do not require a new terminal protocol.

## Scope

This design changes Markdown parse and rendered-line reuse for an active draft.
It does not introduce:

- an active transcript window or logical-row eviction
- terminal diff, viewport, scrollback, or terminal-protocol changes
- fixed-size Markdown fragments or artificial line boundaries

The resulting group segments use KD-015's existing finalize and diff reuse.
That cache retains every cacheable segment in the latest frame and no segments
from older frames, so its memory remains bounded by the current rendered frame.

## Implementation Shape

The implementation stays narrow:

- add a per-draft streaming parse state beside the Markdown renderer
- use top-level token source maps to advance the stable offset
- reuse the existing `_MarkdownBlock` rendering and semantic group boundaries
- expose immutable stable rendered segments plus one mutable frontier segment
- connect the state only to `StreamingTextBuffer` rendering
- fall back to the current full parse whenever safety is uncertain

Claude Code's React component split is not copied. Loushang keeps its existing
assistant chrome and terminal planner, with exact flat rendering as the
correctness oracle.

## Acceptance

- Supported streaming fixtures produce exactly the same logical lines as a
  full parse at every checked boundary.
- Lists, tables, block quotes, and fenced code blocks are never split in the
  middle of a top-level group.
- Replacement and document-wide Markdown constructs safely reset or fall back.
- In a fixed-width, fixed-cadence benchmark, the 1,000-line example with
  20-line independent Markdown blocks reduces Markdown render CPU by at least
  30 percent. This is benchmark evidence, not a cross-machine CI timing gate.
- Continuous single-block input remains correct even when it cannot be made
  faster by this strategy.
- Working ticks and composer input do not read or materialize stable draft
  rows. A new chunk materializes the mutable frontier and newly promoted
  groups, not the complete draft.
- The 10,000-line, 20-lines-per-block fixture remains exact after the number of
  semantic groups exceeds both the Markdown block-cache capacity and 512
  rendered segments.
