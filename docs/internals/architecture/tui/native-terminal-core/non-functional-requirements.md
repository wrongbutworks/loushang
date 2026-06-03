# Non-Functional Requirements

## NFR-VS-001: No Steady-State Flicker

Normal steady-state render updates must not clear the full screen. Full repaint
of runtime-managed visible UI is allowed for first render, terminal resize,
explicit recovery, or a documented unsafe viewport transition.

Acceptance:

- steady streaming updates do not emit clear-screen or clear-scrollback
  operations
- changed bottom-frame lines are updated without visible whole-screen repaint
- resize may use full repaint of runtime-managed UI when that is the most stable
  path

## NFR-VS-002: Synchronized Terminal Updates

Each runtime render flush should be emitted as one synchronized terminal update
when the terminal supports it.

## NFR-VS-003: Resize-Stable Reflow

Terminal resize must not cause full-screen flicker, duplicated transcript
blocks, lost user input, or status/composer displacement. The runtime should
prefer full recompose plus resize repaint for width and height changes unless it
can prove a smaller line-level diff is equally stable.

Acceptance:

- width changes recompute wrapping and cursor mapping before terminal writes
- height changes preserve visible bottom-frame coherence
- resize during streaming does not create repeated assistant or tool blocks
- resize repaint uses clear scrollback by default to rebuild row
  mappings deterministically
- clear scrollback can be disabled by explicit policy for history-preserving
  deployments

## NFR-SI-001: Steady-State History Integrity

Steady-state streaming and transient UI updates must not duplicate transcript
blocks, reorder them, or partially erase visible user input. Terminal history
preservation is best effort during resize, unsafe viewport transitions, and
explicitly configured clear-scrollback policies.

## NFR-SI-002: Streaming Draft Integrity

Assistant streaming output must update a draft record or product-owned draft
state until completion. It must not append a new transcript block for every token
or chunk.

## NFR-TC-001: Terminal Width Correctness

All rendered lines must be measured with one shared terminal cell-width model
that handles:

- ANSI SGR sequences
- OSC 8 hyperlinks
- CJK wide characters
- combining marks
- emoji and grapheme clusters

## NFR-TC-002: Terminal Restoration

Terminal mode, cursor visibility, and input state must be restored on normal
exit, error, cancellation, and keyboard interrupt.

## NFR-EX-001: Runtime Is The Only Terminal Writer

Renderables, UI parts, product adapters, and extensions must not write directly
to stdout, move the hardware cursor, or clear terminal lines. They return render
data, intents, or events to the runtime.

## NFR-LAT-001: Responsive Input

Input echo and cursor movement should feel immediate. High-frequency assistant
or status updates should be coalesced so they do not starve keyboard handling.

## NFR-PORT-001: Capability Degradation

The UI must degrade gracefully when the terminal lacks hyperlinks, truecolor,
image protocols, or synchronized output support.

## NFR-PORT-002: Clear Scrollback Is Policy-Controlled

The runtime must report every clear-scrollback operation in render diagnostics.
Resize repaint clears scrollback by default for deterministic visual stability; this
must be disableable by explicit history-preserving policy. Steady-state diff
updates and ordinary recovery repaint must not clear scrollback unless explicit
policy enables it.

## NFR-OBS-001: Deterministic Render Diagnostics

The runtime must expose deterministic render diagnostics for tests and optional
debug logs: current logical lines, previous rendered lines, changed line range,
viewport top, cursor mapping, terminal operations, repaint kind, clear-scrollback
policy, and recovery repaint reasons.
