# Functional Requirements: Input And Composer

## FR-IC-001: Editable Composer

The TUI must provide an editable composer for user prompt text. It must support
basic insertion, deletion, cursor movement, and submission.

Related: LR-004

## FR-IC-002: Soft Wrapping

Long composer lines must soft-wrap instead of showing only the trailing portion
of the input.

Related: SC-LAYOUT-001, NFR-TC-001

## FR-IC-003: Explicit Newlines

The composer must support explicit newlines through a configured keybinding.
Multi-line input grows upward and preserves the bottom status line.

Related: SC-LAYOUT-002

## FR-IC-003A: Configurable Editor Keybindings

The product adapter may provide a keybinding map from settings. Configured
bindings override default editor, input, selection, and queue bindings for the
native TUI session without changing component internals.

Related: KD-002

## FR-IC-004: Cursor Declaration

Focusable input renderables must declare the logical cursor position so the
runtime can map it to the physical terminal cursor.

Related: SC-LAYOUT-001, SC-LAYOUT-002

## FR-IC-005: Slash Command Trigger

Composer text beginning with slash command syntax must be able to request command
suggestions from the product adapter.

Suggestion UI must preserve composer focus, render selection state without
entering transcript history, and follow the command completion interaction
contract.

Related: SC-SO-001, KD-011

## FR-IC-006: Input While Running

The composer remains usable while a run is active. Submitted text is routed as
follow-up or steering according to product policy.

Related: FR-CI-004, FR-CI-005

## FR-IC-007: Bracketed Paste

The runtime must enable bracketed paste when supported and deliver pasted text as
a paste input event rather than ordinary key events.

Pasted newlines must insert explicit newlines into the composer buffer and must
not submit the prompt.

Related: SC-LAYOUT-003, NFR-TC-001

## FR-IC-008: Paste Safety

Pasted terminal control sequences must not be executed by the terminal. The
runtime or composer must insert them as inert text, escape them for display,
filter them, or reject them with a concise error according to product policy.

Related: SC-LAYOUT-005, NFR-EX-001

## FR-IC-009: Large Paste Representation

Large pasted content may be represented in the composer as a paste marker while
retaining the full pasted text for editing, submission, and undo. Paste markers
must behave as atomic grapheme-like units for cursor movement and deletion.

Related: SC-LAYOUT-004, NFR-TC-001

## FR-IC-010: Paste Undo

One paste input event must be undoable as one editing operation unless the user
subsequently edits inside the pasted content.

Related: SC-LAYOUT-003, SC-LAYOUT-004

## FR-IC-011: Paste While Running

Pasted text while a run is active must enter the composer first. It is routed as
follow-up, steering, or rejected input only when the user explicitly submits it.

Related: SC-CI-004, SC-CI-005, SC-LAYOUT-003

## FR-IC-012: Editor Undo Stack And Kill Ring

The composer should support terminal-native editor primitives: undo/redo, delete word,
delete to line start/end, yank, and a kill ring for cut text. These editor
features are local composer state and must not create transcript records until
the user submits.

Related: SC-LAYOUT-001, SC-LAYOUT-002

## FR-IC-013: Submit Transition Clears Live Composer

When idle composer text is submitted as a new prompt, the runtime must be able to
render the composer-cleared frame before the product adapter appends the submitted
prompt to transcript and starts the run. This prevents the previous live composer
draft from being scrolled into terminal history as if it were committed
transcript.

Related: SC-CI-001, NFR-SI-001
