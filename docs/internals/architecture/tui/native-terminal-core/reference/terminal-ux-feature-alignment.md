# Reference Alignment: Terminal UX Capabilities

## Purpose

This is an internal alignment note. It records capabilities observed in mature
native terminal assistants so loushang can build comparable user-facing behavior
with its own terminology, APIs, and Python implementation.

The mapping is based on local reference surveys and loushang `main` as of
2026-06-05. It is not a compatibility contract and should not be treated as a
public claim about another project's internal implementation.

## Current Completion Snapshot

These percentages are qualitative engineering completion estimates against the
native terminal UX target in this document. They are not public compatibility
scores.

| Area | Loushang status | Completion |
| --- | --- | --- |
| Runtime, render loop, and terminal lifecycle | Public `TuiRunner`, managed runtime, terminal sessions, resize repaint, synchronized flush fallback, bottom-frame cleanup, and fake-terminal playback are in place. | 88% |
| Terminal input and protocol handling | Raw input parsing, bracketed paste, keybinding routing, control-event consumption, keyboard-protocol fallback, and playback coverage exist; terminal-specific edge cases still need broader live-terminal coverage. | 84% |
| Composer and editing foundation | `EditorBuffer`, `ComposerEditBuffer`, `UndoStack`, `KillRing`, word navigation, paste markers, completion refresh, and keyboard selection are reusable and tested. | 87% |
| Surfaces, overlays, and product UI patterns | Surface host, dialogs, selectors, overlays, status/footer, pending and working regions, and completion menus exist; product adapters still need more consistent reuse and smoke coverage. | 80% |
| Content, theme, and media rendering | Markdown, code, diff, thinking, tool records, structured theme tokens, image fallback, and selection highlighting exist; advanced terminal image/protocol paths remain partial. | 78% |
| Regression harness and playback | Native playback covers composer editing, completion, selection stress, fake terminal frames, and manual smoke paths; more consumer-specific playback remains useful. | 88% |
| Public API and reference documentation | Core exports and reference docs exist, including public lifecycle entry and editing primitives; public examples and consumer migration notes are still thin. | 82% |

Overall qualitative completion: about **84%**.

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
| Public lifecycle runner | `TuiRunner` as the reusable application lifecycle entry point. |

## Product UI Patterns

| Reference pattern | Loushang target |
| --- | --- |
| Header container | Optional header area for startup or onboarding content. |
| Chat container | Transcript render area backed by display records. |
| Pending messages container | Pending queue area with follow-up and steering visibility. |
| Status/loading container | Working line area for transient run progress. |
| Widget containers above/below editor | Extension widget slots above or below composer. |
| Editor container | Composer area and focused composer UI part. |
| Editor soft wrap, paste marker, undo, kill ring, and selection | Composer wrapping, paste marker representation, reusable edit buffers, undo/redo stacks, kill ring, selection controller, and selection highlight rendering. |
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
| Editor selection style | `editor.selection` token separate from list-selection styling. |

## Recently Closed Gaps

As of 2026-06-05, these gaps are no longer open in the native TUI core:

- public lifecycle entry through `TuiRunner`
- shared `EditorBuffer` for grapheme-indexed text editing
- reusable `UndoStack` and `KillRing`
- atom-aware `ComposerEditBuffer` for paste markers and composer text
- Composer migration onto the shared editing foundation
- `SelectionRange` and `SelectionController` for text selection state
- keyboard selection, range replacement/delete, kill/yank interaction, and undo
  interaction in Composer
- TextInput migration to shared selection and editing primitives
- frame-level playback for completion and composer-selection stress scenarios
- default redo keybinding policy through `ctrl+shift+z`

## Remaining Gaps

- Broader consumers such as command search, settings search, and model search
  should continue migrating toward the shared text-input and selection
  primitives instead of carrying bespoke edit state.
- Screen-buffer copy selection and mouse-driven transcript selection remain
  intentionally separate from composer text selection and are not implemented
  in the first keyboard-selection pass.
- Live-terminal coverage should be broadened for modifier-key variants,
  keyboard-protocol negotiation, IME cursor behavior, and image protocols.
- Public reference docs should add more small examples for `TuiRunner`,
  TextInput, Composer, selection-aware editing, and playback smoke tests.
- Product adapters still need additional manual smoke and playback coverage for
  long streaming transcripts, interruption, queued steering, and extension
  widgets.

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
