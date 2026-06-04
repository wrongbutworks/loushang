# Functional Requirements: Extension Integration

## FR-EX-001: Extension Boundary

Extensions may contribute commands, surfaces, renderers, status fields,
renderables, UI parts, and transient widgets through public TUI or
product-adapter APIs. They must not write directly to stdout, move the hardware
cursor, clear terminal lines, or receive TerminalPort.

Related: NFR-EX-001, SC-EX-001

## FR-EX-002: Extension Widget Slots

Extension widgets may render in configured widget slots above or below the
composer. They receive render constraints and return render data. They must obey
layout budget, focus, and terminal writer rules.

Related: LR-009, SC-EX-001

## FR-EX-003: Extension Surfaces

Extensions may request temporary surfaces such as selectors, dialogs, or
configuration views. The runtime surface host owns focus capture, close reasons,
overlay stacking, and focus restore.

Related: FR-SO-001, FR-SO-005, SC-SO-004

## FR-EX-004: Extension Status Fields

Extensions may contribute status fields with priorities and short labels. The
status renderer decides what fits and must omit low-priority fields before
wrapping the status row.

Related: LR-003, FR-CI-008

## FR-EX-005: Extension Lifecycle

Extension-provided UI must be disposable. Removing, disabling, or reloading an
extension must remove its widgets, close its surfaces, and invalidate affected
renderables without leaking terminal modes or input handlers.

Related: NFR-TC-002

## FR-EX-006: Extension Renderable Adapter

Extensions may provide renderable or UI part implementations, but the runtime
adapts them through the public renderable protocol. Extension renderables receive
render constraints and normalized input events; they return render results and
intents. They do not receive raw terminal bytes or terminal writer access.

Related: NFR-EX-001, FR-IC-004, FR-SO-001
