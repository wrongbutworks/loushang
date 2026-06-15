# Development Slices

## Purpose

Development should proceed in large TDD slices. Each slice covers a coherent
behavioral surface rather than one helper function.

## Slice 1: Core Data And Width Model

Deliver:

- cell-width model
- logical line representation
- render constraints and render results
- cursor marker support
- explicit cursor declaration support

Verify:

- CJK, emoji, combining marks, ANSI SGR, and OSC 8 hyperlinks measure correctly
- render results reject or report overflow deterministically

## Slice 2: Terminal Playback Harness

Deliver:

- fake terminal port
- scripted event driver
- render diagnostics capture

Verify:

- logical lines, operations, viewport tracking, and cursor mapping are assertable
- failed flush behavior is testable

## Slice 3: Runtime Render Loop

Deliver:

- TerminalPort
- RenderLoop
- managed viewport tracking
- synchronized flush planning
- recovery repaint reasons
- resize repaint and clear-scrollback policy separation

Verify:

- no direct stdout writes outside TerminalPort
- append update and changed range update work
- resize-stable reflow has deterministic operation classes
- width and height changes prefer full recompose plus resize repaint
- resize repaint emits clear scrollback by default, and disabled policy is tested
- user scrollback and external stdout invalidate stale viewport mapping
- render tick coalescing preserves responsive input
- render scheduler tuning parameters are recorded for review, including minimum
  render interval, maximum coalescing delay, and input echo deadline

## Slice 4: Render Framework

Deliver:

- Renderable
- Container
- Focusable
- SurfaceHost shell
- ScreenRoot shell

Verify:

- focus capture and restore
- constraints propagate through containers
- surface output composes before diffing

## Slice 5: Composer And Bottom Frame

Deliver:

- Composer
- paste marker representation
- undo stack
- kill ring
- StatusBar
- WorkingLine
- PendingQueueView
- BottomFrame layout

Verify:

- long input soft-wraps
- explicit newlines grow upward
- multi-line paste inserts text without submitting
- paste markers are atomic for cursor movement and deletion
- long single-line paste can be represented by a paste marker
- path-like paste after a word character inserts one readability space
- undo/redo and kill-ring operations preserve cursor mapping
- status remains bottom row
- queued messages render above working line
- constrained height follows the bottom-frame priority table

## Slice 6: Input Routing

Deliver:

- InputReader
- keybinding router
- bracketed paste handling
- paste safety handling for terminal control sequences
- Esc/Ctrl-C routing

Verify:

- surface Esc priority
- paste does not submit unexpectedly
- pasted terminal control sequences are not executed
- CSI-u Ctrl+letter encodings inside bracketed paste are decoded before paste
  filtering
- abort, follow-up, and steer intents route correctly

## Slice 7: Surfaces

Deliver:

- AutocompleteSurface
- CommandSurface
- SelectionSurface
- ApprovalSurface
- DialogSurface

Verify:

- close reasons
- selection intents
- approval intents
- overlay and non-overlay presentation

## Slice 8: Coding Transcript Adapter

Deliver:

- display record projection
- assistant draft lifecycle
- worked divider
- tool execution view
- thinking view
- concise error view

Verify:

- streaming draft commits once
- tool elapsed/took markers are per-tool
- thinking visibility policy is enforced

## Slice 9: Content And Theme

Deliver:

- MarkdownRenderer
- CodeBlock
- DiffBlock
- ImageBlock fallback
- ThemeResolver

Verify:

- markdown wraps by cell width
- optional highlighter imports are lazy
- theme changes invalidate cached output

## Slice 10: Extension Hooks

Deliver:

- extension widget slots
- extension status fields
- extension surface requests
- extension renderable/UI part adapter
- lifecycle disposal

Verify:

- extensions cannot write terminal output
- extensions do not receive raw terminal bytes or TerminalPort
- removing an extension removes its UI
- extension surfaces obey focus and close-reason rules
