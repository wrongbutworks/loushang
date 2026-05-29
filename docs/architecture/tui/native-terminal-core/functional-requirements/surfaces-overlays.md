# Functional Requirements: Surfaces And Overlays

## FR-SO-001: Surface Host

The TUI must provide a surface host for temporary interactive UI. The host owns
surface lifetime, focus capture, close reasons, and focus restore.

Surfaces use explicit presentation modes instead of ad-hoc component flags:

- `inline` appends the surface in normal layout flow.
- `overlay` draws the surface over the current logical screen.
- `modal` is an overlay presentation that captures focus unless configured
  otherwise.
- `bottom` is a bottom-frame surface that can coexist with composer/status rows.
- `bottom-exclusive` is a bottom-frame surface that owns the bottom area and
  suppresses ordinary composer/status rows while active.

Related: LR-007, SC-SO-001, SC-SO-002

## FR-SO-002: Autocomplete Surface

The TUI must support an autocomplete surface above or attached to the composer.
It displays suggestions, selection state, and scroll state.

Inline autocomplete must not create transcript records. Closing it must preserve
composer focus and visual anchoring.

Related: SC-SO-001, KD-011

## FR-SO-003: Command Surface

Slash command selection must be represented as a generic surface. The product
adapter owns command semantics; the TUI owns display, navigation, and selection
events.

Slash command completion uses a stable selection grammar: fixed `>` gutter,
aligned command/description columns, whole-row selected styling, Enter to execute
the highlighted command, Tab to apply without submitting, and Esc to close.

Related: SC-SO-001, KD-011

## FR-SO-004: Settings Surface

Settings UI must be represented as a surface or surface group hosted by the
runtime. It must not start a nested terminal application.

Related: SC-SO-002

## FR-SO-005: Dialog Surface

Confirm/cancel interactions must use dialog surfaces with explicit close reasons
such as confirm, cancel, escape, abort, or replaced.

Related: SC-SO-002

## FR-SO-006: Surface Esc Handling

When a surface is active, Esc is offered to the surface before it is interpreted
as an abort control for the active run.

Related: SC-CI-003, SC-SO-002

## FR-SO-007: Selection Surface

Temporary item selection must use selection surfaces that own display,
navigation, filtering, selection state, and close reasons. Product adapters own
the meaning of selected items.

Focused selection surfaces, such as model selection, must suppress the ordinary
composer/status rows while active and render their own confirmation hint.

Related: SC-SO-001, SC-SO-002, KD-011

## FR-SO-008: Approval Surface

Permission and authorization prompts must use approval surfaces. The surface
shows the guarded action and risk context, then returns an explicit approval
intent. The TUI does not execute the guarded action directly.

Related: SC-SO-002, SC-CI-003

## FR-SO-009: Surface Stacking

The surface host must support stacked surfaces. The top focused surface receives
keyboard input first, and z-order must follow the runtime-owned overlay stack.

Related: SC-SO-005, KD-005

## FR-SO-010: Constrained Surface Scrolling

Surfaces whose content exceeds available height must scroll internally or
truncate according to their surface type. They must not push the composer or
status area out of their reserved minimum layout.

Related: SC-SO-005, KD-005, KD-008
