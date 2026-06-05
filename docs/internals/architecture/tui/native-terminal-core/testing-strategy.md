# Testing Strategy

## Purpose

The native terminal core must be tested at the render-operation level. Manual
testing remains useful, but flicker, duplicated transcript, resize instability,
and cursor mapping need deterministic tests.

## Test Layers

### 1. Pure Renderable Tests

Render UI parts with fixed constraints and assert logical lines, cursor markers,
and overflow behavior.

Examples:

- composer soft wrap and explicit newline
- multi-line paste insertion and paste-marker editing
- status truncation
- select list navigation
- markdown wrapping
- tool execution record rendering

### 2. Render Loop Tests

Drive RenderLoop with previous rendered lines, current logical lines, terminal
size, and viewport tracking. Assert terminal operations, changed line ranges, and
recovery repaint reasons.

Examples:

- append update
- changed bottom-frame line update
- first changed line above viewport triggers recovery repaint
- width resize triggers full recompose plus resize repaint
- height resize triggers full recompose plus resize repaint by default
- resize repaint emits clear scrollback by default
- disabled clear-scrollback policy is observable on resize
- explicit clear-scrollback policy is observable for recovery repaint when enabled
- user scrollback movement invalidates stale row mapping
- external stdout forces repaint recovery instead of stale diff
- render tick coalescing preserves responsive input
- failed flush does not update previous rendered lines

### 3. Terminal Playback Tests

Use the playback harness to script input, product events, streaming chunks,
surface events, and resize events. Assert both logical transcript and terminal
operations.

Examples:

- submit prompt, stream assistant, commit worked divider
- resize during streaming
- resize with clear scrollback disabled
- user scrolls up while streaming continues
- paste multi-line content without submitting
- paste content with terminal control sequences without executing it
- queue follow-up while running
- steer while running
- Esc with active approval surface
- stacked surfaces restore focus in order
- constrained-height bottom frame follows priority rules
- concise error without traceback
- composer selection stress with wide text, paste markers, kill/yank, undo,
  completion refresh, and selection key priority

Composer selection playback should be run directly when changing composer input,
selection, paste marker, completion, keybinding, or render-highlight behavior:

```bash
uv --cache-dir .uv-cache run --extra dev python -m loushang.coding.ui.playback_runner composer-selection-stress --artifacts /tmp/loushang-selection-playback --include-frames
```

The trace should include `composer-selection-stress` as a passing scenario. Use
the generated JSONL artifact when diagnosing selection regressions because the
final screen cannot show transient selected ranges after replacement or undo.

### 4. Boundary Tests

Import and integration tests enforce module boundaries.

Examples:

- importing `loushang.tui` does not import coding modules
- raw runtime imports do not require prompt_toolkit, Rich, or Pygments
- extensions cannot receive TerminalPort
- extensions receive normalized input events rather than raw terminal bytes
- v1 prompt_toolkit modules are not on the new public API path

## Manual Smoke Tests

Manual testing should focus on terminal behavior that is hard to assert
visually:

- startup below existing shell output
- resizing during long streaming output
- scrolling up while output continues
- IME candidate window placement
- terminal restoration after Ctrl-C, Esc abort, exception, and normal exit
- narrow terminal status truncation
- composer selection in a real terminal:
  - type `abc`, press `Shift+Left`, verify the final `c` is visibly selected,
    then type `x` and verify the draft becomes `abx`
  - type `你🙂a`, press `Shift+Left` twice, type `x`, and verify the draft
    becomes `你x` without splitting the emoji grapheme
  - type a short draft, use `Shift+Home` and `Shift+End` from opposite line
    ends, and verify typing replaces exactly the selected text
  - press `Ctrl+-` after a selection replacement and verify undo restores the
    previous content and clears the visible selection

Manual smoke tests should be run after the playback harness and unit tests pass.
