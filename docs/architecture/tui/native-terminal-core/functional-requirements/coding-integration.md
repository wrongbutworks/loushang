# Functional Requirements: Coding Integration

## FR-CI-001: Product Adapter Boundary

`loushang.coding.ui` is the only layer that may understand both generic TUI
primitives and coding product semantics.

The generic TUI must not import coding session, model, tool, diagnostics, or
provider modules.

Related: NFR-EX-001

## FR-CI-002: Transcript Display Records

Coding UI must project product events into stable display records before they are
rendered by the TUI.

The generic TUI core defines the record families and lifecycle rules. The coding
adapter owns projection from coding events into concrete record instances.

Initial record families:

- user prompt block
- assistant message block with text and optional thinking content blocks
- tool execution block with running/completed state, timing marker, output,
  truncation, and tool error state
- error block
- interrupted block
- divider block
- worked divider block

Related: LR-010, SC-CI-001, SC-CI-002, SC-ERR-001

## FR-CI-003: Running Turn Chrome

While a run is active, the UI shows a transient working line above the composer.
The line includes elapsed time and interrupt affordance according to product
configuration.

Related: LR-006, SC-CI-001

## FR-CI-004: Follow-Up Queue

When a run is active, regular submitted input may be queued as next-turn
follow-up. The composer clears after queuing and the queued text is visible in a
follow-up queue area.

Related: SC-CI-004

## FR-CI-005: Steering Messages

When a run is active and live steering is supported, configured steering input is
delivered to the active run and shown as pending steering instead of next-turn
follow-up.

Related: SC-CI-005, SC-CI-006

## FR-CI-006: Abort Interaction

Esc and Ctrl-C are abort controls while a run is active. Abort requests are
control actions, not prompt text.

Related: SC-CI-003

## FR-CI-007: Concise Errors

Recoverable errors are rendered as concise transcript blocks. Python tracebacks
are hidden unless verbose diagnostics are enabled.

Related: SC-ERR-001

## FR-CI-008: Status Snapshot

The product adapter supplies a status snapshot for the status area. Default field
priority:

1. model and thinking level
2. compact current working directory
3. context usage percentage
4. time/rate/quota information
5. weekly quota information
6. model context window
7. token usage
8. branch
9. session id

Related: LR-003
