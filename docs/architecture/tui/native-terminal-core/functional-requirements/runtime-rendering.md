# Functional Requirements: Runtime Rendering

## FR-RR-001: Native Terminal Runtime

The TUI must run as a native terminal application in the user's normal screen and
scrollback. It must not require fullscreen alternate-screen operation for the
primary coding workflow. Native terminal history preservation is best effort;
visual stability is prioritized for resize and recovery repaint.

Related: LR-001, NFR-SI-001, SC-START-001

## FR-RR-002: Logical Screen Composition

The runtime must compose a full logical screen from renderable output before
writing terminal operations.

Related: NFR-VS-001

## FR-RR-003: Differential Rendering

The runtime must compare current logical lines against previous logical lines and
write only the terminal operations required for the next frame when safe.

Related: NFR-VS-001, SC-RR-001

## FR-RR-004: Bottom Frame Ownership

The runtime must own the bottom frame used for transient UI, including surfaces,
composer, separator, working line, and status.

Related: LR-002, LR-003, LR-004, LR-006, LR-007

## FR-RR-005: Resize And Reflow

The runtime must observe terminal size changes and reflow logical content without
duplicating previously committed transcript blocks, losing user input, or
displacing the composer and status areas.

Related: SC-RR-001, NFR-SI-001, NFR-VS-003

## FR-RR-006: Terminal Restore

The runtime must restore terminal state on normal exit, error, cancellation, and
keyboard interrupt.

Related: NFR-TC-002

## FR-RR-007: User Scrollback Interaction

The runtime must allow users to use native terminal scrollback. If user
scrollback movement makes managed viewport row mapping unsafe, the runtime must
stop assuming previous rendered rows are still writable in place and must
re-anchor with a repaint or another safe update path before the next managed
update.

Related: SC-RR-003, KD-004, NFR-SI-001

## FR-RR-008: External Stdout Recovery

Writes to stdout from outside the runtime terminal writer must be treated as an
unsafe viewport transition. The runtime must not keep applying differential
updates based on stale row mapping after such writes are detected or reported.

Related: SC-EX-002, KD-004, NFR-EX-001

## FR-RR-009: Resize Repaint

The runtime may full recompose and full repaint runtime-managed visible UI after
terminal width or height changes. The default resize repaint policy is stable:
clear screen, home cursor, clear scrollback, then render current logical lines.
Products may opt into a history-preserving policy that disables clear scrollback.

Related: SC-RR-001, SC-RR-002, NFR-VS-003, NFR-PORT-002

## FR-RR-010: Clear Scrollback Policy

Clear scrollback operations must be controlled by render policy and reported
through diagnostics. Resize repaint defaults to clear scrollback for visual
stability; recovery repaint and steady-state diff updates must not clear
scrollback unless an explicit policy enables it.

Related: SC-RR-004, NFR-PORT-002, NFR-OBS-001

## FR-RR-011: Exit-Time Bottom Frame Cleanup

Before returning control to the parent shell, the runtime must clear the
transient bottom frame rows that it owns, including composer, completion,
surface, blank spacer, working, pending, footer, and status rows. These rows are
runtime UI, not committed transcript content, and must not remain below the
shell prompt in terminal scrollback.

The cleanup must leave the hardware cursor at the start of the cleared composer
or bottom-frame anchor row so the parent shell prompt appears on a clean line.
It must not clear committed transcript rows above the bottom frame, must not
clear scrollback, and must be safe after normal exit, slash-command exit, EOF,
and local-command exit.

Related: FR-RR-004, FR-RR-006, LR-002, LR-003, NFR-SI-001
