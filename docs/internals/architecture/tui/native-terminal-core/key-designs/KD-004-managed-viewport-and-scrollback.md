# KD-004: Managed Viewport And Scrollback

## Purpose

Define best-effort terminal history preservation while allowing deterministic visual
stability and resize repaint.

## Design

The runtime tracks a managed viewport: rows it has rendered and can prove remain
safe to update. Normal shell output that existed before TUI startup is outside
the managed viewport.

Committed transcript records may naturally move into terminal scrollback through
append updates. The runtime keeps display records as the source of truth for
future rendering; terminal scrollback is user-visible history, not the runtime's
state store.

Steady-state streaming should preserve terminal history by appending or updating
managed rows without duplicating transcript blocks. Resize and unsafe viewport
transitions may repaint runtime-managed visible UI to preserve visual stability.
Clear scrollback is policy-controlled: enabled by default for resize
repaint, disabled for steady-state updates and ordinary recovery repaint.

Unsafe viewport transitions include external stdout writes, user scrollback
movement that affects managed rows, width reflow that invalidates row mapping,
and height changes that make row mapping uncertain. Recovery repaint is allowed
only to re-establish runtime-owned rows.

## User Scrollback Interaction

The runtime must not prevent users from using native terminal scrollback. User
scrolling is external terminal state; the runtime cannot assume that rows it
previously rendered are still writable at the same physical positions after the
user scrolls.

If user scrollback movement is detected or inferred, the runtime marks managed
viewport mapping as unsafe. Until a safe bottom anchor is re-established, the
runtime must avoid in-place changed-range updates that depend on old physical row
mapping. The next managed update may:

- append new transcript content naturally if it does not require rewriting old
  rows
- request a recovery repaint of runtime-owned rows after returning to the bottom
  anchor
- defer cosmetic transient updates until a safe anchor exists

User text input, explicit submission, resize, or a product event that requires
bottom-frame interaction may re-anchor the runtime at the bottom. Re-anchoring
may repaint runtime-managed visible UI. Resize re-anchor defaults to clear
scrollback; non-resize recovery repaint must not clear scrollback unless policy
explicitly enables it.

## External Stdout Writes

All stdout writes must go through the runtime terminal writer. If external output
does occur, whether from a child process, product bug, or third-party code, it is
treated as an unsafe viewport transition. Render diagnostics must record the
reason when recovery repaint is used after external output.

## History Preservation Policy

Default policy:

- preserve startup shell history best effort
- preserve steady-state transcript history during normal streaming
- allow resize repaint of runtime-managed visible UI
- enable clear scrollback for resize repaint
- disable clear scrollback for steady-state and ordinary recovery repaint

Optional policy may disable resize clear scrollback for users who prefer shell
history preservation, or enable clear scrollback for panic recovery. That policy
must be explicit, testable, and visible in diagnostics.

## Test Obligations

- startup does not clear previous shell output by default
- steady-state transient updates do not duplicate committed transcript blocks
- external stdout invalidates managed viewport assumptions
- recovery repaint records a reason in render diagnostics
- user scrollback movement prevents stale changed-range updates
- input or submission after user scroll can re-establish a bottom anchor
- resize clear scrollback is enabled by default and separately testable when
  disabled
