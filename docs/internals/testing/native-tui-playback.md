# Native TUI Playback Regression Tests

Use `tests/coding/native_tui_playback.py` when a native TUI change can affect terminal behavior, not just pure component rendering.

Good candidates include:

- composer input echo
- Working timer frames
- streaming updates
- completion open and close
- overlay and surface interactions
- viewport or cursor positioning
- long transcript resume behavior
- product-composed interactions that combine transcript, running state,
  pending queues, surfaces, completion, and composer selection

Prefer focused component tests for pure rendering functions. Use the playback harness when the test needs a `NativeCodingTuiApp`, `TuiRuntime`, and `FakeTerminalPort` together.

Useful assertions:

- `assert_no_clear(step)` for no `clear_screen` and no `clear_scrollback`
- `assert_operation_class(step, "...")` for differential update expectations
- `assert_visible_contains(text)` and `assert_visible_not_contains(text)` for visible terminal output
- `assert_cursor_matches_diagnostics(step)` when cursor anchoring is part of the behavior

Avoid broad snapshot-only tests. Prefer targeted assertions on terminal operations, diagnostics, visible text, and cursor/viewport invariants.

Useful direct smoke commands:

```bash
uv --cache-dir .uv-cache run --extra dev python -m loushang.coding.ui.playback_runner composer-selection-stress --artifacts /tmp/loushang-selection-playback --include-frames
uv --cache-dir .uv-cache run --extra dev python -m loushang.coding.ui.playback_runner product-composed-interaction --artifacts /tmp/loushang-product-playback --include-frames
```
