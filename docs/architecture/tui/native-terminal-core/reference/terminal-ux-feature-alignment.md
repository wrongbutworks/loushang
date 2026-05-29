# Reference Alignment: Terminal UX Capabilities

## Purpose

This is an internal alignment note. It records capabilities observed in mature
native terminal assistants so loushang can build comparable user-facing behavior
with its own terminology, APIs, and Python implementation.

The mapping is based on observed behavior as of 2026-05-23. It is not a
compatibility contract and should not be treated as a public claim about another
project's internal implementation.

## Runtime Mechanisms

| Reference capability | Loushang target |
| --- | --- |
| Render tree returns line arrays for a width | Renderables return render results constrained by width and height. |
| Full logical line buffer per render | Full recompose produces current logical lines before terminal planning. |
| Previous line snapshot | Previous rendered lines in RenderLoop diagnostics and diff planning. |
| Changed range diff | Changed line range terminal operations. |
| Append-friendly update path | Append update for natural terminal scrolling. |
| Resize full render for stability | Resize repaint of runtime-managed visible UI after width or height changes. |
| Viewport top and hardware cursor tracking | Managed viewport, previous viewport top, logical cursor row, hardware cursor row. |
| Synchronized terminal output | Synchronized flush when supported, graceful fallback otherwise. |
| Cursor marker inside focused render output | Cursor marker extracted by runtime for IME-aware hardware cursor placement. |
| Overlay stack and focus handling | SurfaceHost with surface area and overlay presentation modes. |
| Terminal raw input and restoration | InputReader plus terminal restoration on exit, error, cancellation, and interrupt. |

## Product UI Patterns

| Reference pattern | Loushang target |
| --- | --- |
| Header container | Optional header area for startup or onboarding content. |
| Chat container | Transcript render area backed by display records. |
| Pending messages container | Pending queue area with follow-up and steering visibility. |
| Status/loading container | Working line area for transient run progress. |
| Widget containers above/below editor | Extension widget slots above or below composer. |
| Editor container | Composer area and focused composer UI part. |
| Editor soft wrap, paste marker, undo, kill ring | Composer wrapping, paste marker representation, undo stack, and kill ring. |
| Footer | Status area as the bottom row by default. |
| Selectors and dialogs | Selection, settings, approval, dialog, help, and changelog surfaces. |

## Content Capabilities

| Reference capability | Loushang target |
| --- | --- |
| Markdown parser and terminal renderer | Markdown renderer with lazy optional adapters and shared cell-width wrapping. |
| Assistant message with thinking blocks | Assistant message records with thinking blocks and visibility policy. |
| Tool execution views | Tool execution records with elapsed/took timing, output, truncation, and errors. |
| Diff and code renderers | DiffBlock and CodeBlock UI parts with theme-controlled styles. |
| Terminal images with fallback | ImageBlock with text fallback and optional protocol adapters. |
| Structured themes | Theme tokens for markdown, status, thinking, tools, surfaces, and code. |

## Loushang Differences

- The public product API remains `loushang.tui`.
- Architecture docs use `Renderable` and `UI Part` instead of overloading
  "component."
- The raw runtime core must not require Rich, prompt_toolkit, or Pygments at
  import time.
- Loushang aligns with full logical buffers, line-level diff, append
  updates, synchronized flush, overlay-before-diff composition, cursor markers,
  screen region stack, and resize repaint.
- Loushang aligns with resize clear scrollback by default while keeping
  it policy-controlled for history-preserving deployments.
- Coding semantics live in `loushang.coding.ui`; the generic TUI core remains
  product-neutral.
