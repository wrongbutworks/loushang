# TUI Terminal Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `loushang.tui` so terminal environment detection, runtime capabilities, keyboard protocol negotiation, and input control-event routing are explicit, testable, and isolated from product UI code.

**Architecture:** Keep `InputReader` as the only terminal sequence assembler. Add pure terminal capability detection, then introduce `InputBatch` so terminal control responses are consumed by runtime/session code before ordinary app input reaches `NativeInputRouter`. Preserve existing public APIs during P0 with compatibility wrappers and small migration steps.

**Tech Stack:** Python 3.13, pytest, `uv --cache-dir .uv-cache run --extra dev pytest`, existing `loushang.tui` render/input modules.

---

## Reference Documents

- Spec: `docs/architecture/tui/native-terminal-core/key-designs/KD-013-terminal-runtime-capabilities.md`
- Input sequence design: `docs/architecture/tui/native-terminal-core/key-designs/KD-012-keyboard-protocol-and-escape-buffering.md`
- Glossary: `docs/architecture/tui/native-terminal-core/glossary.md`
- Current input reader: `src/loushang/tui/input.py`
- Current terminal mode/read helpers: `src/loushang/tui/terminal_input.py`
- Current native loop: `src/loushang/coding/ui/native_loop.py`
- Current image protocol detection: `src/loushang/tui/terminal_image.py`

## File Structure

- Create `src/loushang/tui/terminal_capabilities.py`
  - Owns `TerminalEnvironment`, capability dataclasses, environment normalization, and pure detection.
- Modify `src/loushang/tui/terminal_image.py`
  - Delegates `detect_image_protocol(env)` to the new capability detector while preserving the current API.
- Modify `src/loushang/tui/theme.py`
  - Keep the existing `TerminalCapabilities` class for P0. Later slices can either extend it or adapt from runtime capabilities.
- Modify `src/loushang/tui/input.py`
  - Adds `InputBatch`, pending-state accessors, and control/app event classification.
- Modify `src/loushang/coding/ui/native_loop.py`
  - Uses batch routing so control events do not enter `NativeInputRouter`.
  - Later owns pending ESC idle deadline.
- Create `src/loushang/tui/keyboard_protocol.py`
  - Owns keyboard protocol state, Kitty response consumption, modifyOtherKeys fallback state, and cleanup writes.
- Modify `src/loushang/tui/terminal_input.py`
  - Gradually narrows raw read helpers to transport/UTF-8 boundaries and moves ESC semantic buffering into `InputReader` + native loop scheduling.
- Create `src/loushang/tui/terminal_session.py`
  - Wraps current `TerminalInputMode` behavior behind a context-manager-compatible lifecycle.
- Create `tests/tui/test_terminal_capabilities.py`
  - Pure environment/capability detector tests.
- Extend `tests/tui/test_terminal_input.py`
  - InputBatch, split sequence, pending flush, and control-event tests.
- Create `tests/tui/test_keyboard_protocol.py`
  - Protocol negotiation and cleanup tests with fake writes and fake time.
- Extend `tests/coding/test_native_coding_tui_playback.py`
  - Verify terminal control responses do not appear in composer/product input.

---

### Task 1: Pure Terminal Capability Detection

**Files:**
- Create: `src/loushang/tui/terminal_capabilities.py`
- Create: `tests/tui/test_terminal_capabilities.py`
- Modify: `src/loushang/tui/__init__.py`

- [ ] **Step 1: Write failing detector tests**

Add table-driven tests for:

- Kitty: `TERM=xterm-kitty` or `KITTY_WINDOW_ID`
- Ghostty: `GHOSTTY_RESOURCES_DIR`
- WezTerm: `WEZTERM_PANE`
- iTerm2: `ITERM_SESSION_ID` or `TERM_PROGRAM=iTerm.app`
- VSCode: `TERM_PROGRAM=vscode`
- Windows Terminal: `WT_SESSION`
- tmux and screen: `TMUX` or `STY`
- SSH with known client terminal hints
- unknown terminal

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_capabilities.py -q
```

Expected: fail because `loushang.tui.terminal_capabilities` does not exist.

- [ ] **Step 2: Implement minimal pure detector**

Add immutable dataclasses:

```python
@dataclass(frozen=True, slots=True)
class TerminalEnvironment:
    term: str = ""
    term_program: str = ""
    colorterm: str = ""
    inside_tmux: bool = False
    inside_screen: bool = False
    inside_ssh: bool = False
    is_windows: bool = False
    is_macos: bool = False
    is_linux: bool = False
    is_wsl: bool = False
    has_kitty_env: bool = False
    has_iterm_env: bool = False
    has_wezterm_env: bool = False
    has_ghostty_env: bool = False
    has_windows_terminal_env: bool = False
    raw_env: Mapping[str, str] = field(default_factory=dict)
```

Use a separate runtime capability dataclass for P0 to avoid colliding with the
existing `theme.TerminalCapabilities`:

```python
ImageProtocol = Literal["kitty", "iterm2", "none"]
KeyboardProtocolStrategy = Literal["kitty_then_modify_other_keys", "modify_other_keys", "legacy"]

@dataclass(frozen=True, slots=True)
class TerminalRuntimeCapabilities:
    truecolor: bool = False
    hyperlinks: bool = False
    image_protocol: ImageProtocol = "none"
    keyboard_protocol_strategy: KeyboardProtocolStrategy = "legacy"
    query_cell_size: bool = False
    enable_bracketed_paste: bool = True
    enable_focus_events: bool = True
    enable_mouse: bool = False
    alternate_screen: bool = False
    windows_vt_input: bool = False
    termux_session: bool = False
    apple_terminal_normalization: bool = False
    is_multiplexer: bool = False
    capability_sources: tuple[str, ...] = ()
```

- [ ] **Step 3: Export public names**

Update `src/loushang/tui/__init__.py` so tests and downstream users can import
the detector without reaching into private modules.

- [ ] **Step 4: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_capabilities.py -q
git diff --check
git add src/loushang/tui/terminal_capabilities.py src/loushang/tui/__init__.py tests/tui/test_terminal_capabilities.py
git commit -m "feat(tui): detect terminal runtime capabilities"
```

Expected: detector tests pass.

---

### Task 2: Delegate Image Protocol Detection

**Files:**
- Modify: `src/loushang/tui/terminal_image.py`
- Modify: `tests/tui/test_content_theme.py`
- Modify: `tests/tui/test_terminal_capabilities.py`

- [ ] **Step 1: Write failing image compatibility tests**

Add tests that assert `detect_image_protocol(env)` still returns the current API
shape:

- `"kitty"` for Kitty, Ghostty, and WezTerm
- `"iterm2"` for iTerm2
- `None` for tmux/screen and unknown terminals

Also assert tmux wins over a Kitty terminal hint.

- [ ] **Step 2: Delegate implementation**

Change `terminal_image.detect_image_protocol(env)` to call the new detector and
translate `"none"` to `None`.

- [ ] **Step 3: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_capabilities.py tests/tui/test_content_theme.py -q
git diff --check
git add src/loushang/tui/terminal_image.py tests/tui/test_content_theme.py tests/tui/test_terminal_capabilities.py
git commit -m "refactor(tui): route image protocol detection through capabilities"
```

Expected: existing image behavior is preserved.

---

### Task 3: Add InputBatch Without Migrating Callers

**Files:**
- Modify: `src/loushang/tui/input.py`
- Modify: `src/loushang/tui/__init__.py`
- Extend: `tests/tui/test_terminal_input.py`

- [ ] **Step 1: Write failing InputBatch tests**

Add tests:

- `reader.feed_batch("\x1b[?7u")` produces one `control_event` and zero `app_events`.
- `reader.feed_batch("\x1b[6;18;9t")` produces a `cell_size` control event.
- `reader.feed_batch("\x1b[A")` produces an `up` app event and no control events.
- split Kitty response `"\x1b"` then `"[?7u"` yields no event first, then one control event.
- bracketed paste split across chunks yields one paste app event.

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_input.py -q
```

Expected: fail because `feed_batch` and `InputBatch` do not exist.

- [ ] **Step 2: Add InputBatch and classification**

Add:

```python
@dataclass(frozen=True, slots=True)
class InputBatch:
    app_events: tuple[InputEvent, ...] = ()
    control_events: tuple[InputEvent, ...] = ()
    has_pending: bool = False
```

Add `InputReader.feed_batch(data)` and keep `InputReader.feed(data)` as a
compatibility wrapper for existing callers.

Classification rule:

- `event.kind == "signal"` is a control event.
- all other events are app events for now.

- [ ] **Step 3: Add pending accessors**

Add:

```python
@property
def has_pending(self) -> bool: ...

def flush_pending_batch(self) -> InputBatch: ...
```

Keep `flush()` as a compatibility wrapper.

- [ ] **Step 4: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_input.py -q
git diff --check
git add src/loushang/tui/input.py src/loushang/tui/__init__.py tests/tui/test_terminal_input.py
git commit -m "feat(tui): separate input app and control events"
```

Expected: terminal input tests pass.

---

### Task 4: Consume Control Events Before Product Routing

**Files:**
- Modify: `src/loushang/coding/ui/native_loop.py`
- Extend: `tests/coding/test_native_coding_tui_playback.py`
- Extend: `tests/tui/test_terminal_input.py`

- [ ] **Step 1: Write failing routing test**

Use a fake input stream containing a Kitty response before normal text. Assert
that the response is not inserted into the composer and is not submitted as
prompt text.

- [ ] **Step 2: Migrate native loop to InputBatch**

Change `_input_events_for_chunk` into a batch-producing helper. It should:

- call `reader.feed_batch(data)`
- return batch app events to router
- hold control events for runtime/session consumption

At this stage, control events can be consumed by a no-op helper:

```python
def _consume_terminal_control_events(events: tuple[InputEvent, ...]) -> None:
    return None
```

The important P0 behavior is that controls do not enter `NativeInputRouter`.

- [ ] **Step 3: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_input.py tests/coding/test_native_coding_tui_playback.py -q
git diff --check
git add src/loushang/coding/ui/native_loop.py tests/coding/test_native_coding_tui_playback.py tests/tui/test_terminal_input.py
git commit -m "fix(tui): consume terminal controls before input routing"
```

Expected: control responses never reach product input.

---

### Task 5: Move ESC Idle Flush Out Of Raw Read Helpers

**Files:**
- Modify: `src/loushang/tui/terminal_input.py`
- Modify: `src/loushang/coding/ui/native_loop.py`
- Extend: `tests/tui/test_terminal_input.py`

- [ ] **Step 1: Write failing split ESC tests**

Cover:

- `ESC` then `[A` in two chunks becomes `up`.
- standalone `ESC` emits only after explicit idle flush.
- read helpers do not join ESC tails with a select timeout.

- [ ] **Step 2: Narrow raw read helpers**

Remove semantic ESC tail joining from `read_input_chunk()`,
`_read_tty_input_chunk()`, `_read_escape_tail()`, and StringIO-specific tail
helpers. Preserve UTF-8 tail handling.

- [ ] **Step 3: Add pending deadline in native loop**

Teach the input loop to flush pending input only after a short idle deadline
when `reader.has_pending` is true.

Use fake time or injectable timeout in tests. Do not add sleeps to ordinary key
handling.

- [ ] **Step 4: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_input.py tests/coding/test_native_coding_tui_playback.py -q
git diff --check
git add src/loushang/tui/terminal_input.py src/loushang/coding/ui/native_loop.py tests/tui/test_terminal_input.py tests/coding/test_native_coding_tui_playback.py
git commit -m "fix(tui): flush incomplete escape input after idle deadline"
```

Expected: split arrows work without relying on raw-read ESC tail joining.

---

### Task 6: KeyboardProtocolController

**Files:**
- Create: `src/loushang/tui/keyboard_protocol.py`
- Modify: `src/loushang/tui/terminal_input.py`
- Extend: `tests/tui/test_keyboard_protocol.py`

- [ ] **Step 1: Write failing protocol tests**

Test:

- startup sends Kitty query when strategy is `kitty_then_modify_other_keys`
- Kitty response marks protocol active and emits enable flags `ESC[>7u`
- no Kitty response before deadline enables modifyOtherKeys `ESC[>4;2m`
- shutdown disables only modes that were actually enabled
- shutdown is idempotent

- [ ] **Step 2: Implement controller**

Add a small state object:

```python
@dataclass(slots=True)
class KeyboardProtocolController:
    strategy: KeyboardProtocolStrategy
    kitty_active: bool = False
    modify_other_keys_active: bool = False
```

Expose methods:

- `startup_sequences()`
- `consume_control_event(event)`
- `fallback_sequences_if_due(now_ms)`
- `shutdown_sequences()`

- [ ] **Step 3: Wire to terminal input mode conservatively**

Do not replace all of `TerminalInputMode` yet. Replace the current unconditional
dual write of `ESC[?u` and `ESC[>4;2m` with controller-driven writes.

- [ ] **Step 4: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_keyboard_protocol.py tests/tui/test_terminal_input.py -q
git diff --check
git add src/loushang/tui/keyboard_protocol.py src/loushang/tui/terminal_input.py tests/tui/test_keyboard_protocol.py
git commit -m "feat(tui): negotiate keyboard protocol state"
```

Expected: protocol tests pass and previous input tests remain green.

---

### Task 7: TerminalSession Lifecycle Shell

**Files:**
- Create: `src/loushang/tui/terminal_session.py`
- Modify: `src/loushang/coding/ui/native_loop.py`
- Modify: `src/loushang/tui/terminal_input.py`
- Create: `tests/tui/test_terminal_session.py`

- [ ] **Step 1: Write failing lifecycle tests**

Use fake stdin/stdout objects to assert:

- session enters and exits as a context manager
- bracketed paste and focus modes are enabled/disabled according to capabilities
- keyboard protocol cleanup happens before drain
- cleanup is idempotent
- non-TTY stdin remains a no-op context manager

- [ ] **Step 2: Implement TerminalSession wrapper**

Wrap existing `TerminalInputMode` behavior rather than rewriting raw mode setup
from scratch. Keep the default `mode_factory` integration point.

- [ ] **Step 3: Use TerminalSession as default mode factory**

In `native_loop.py`, change the default factory to produce `TerminalSession`.
Keep the `terminal_mode_factory` parameter for tests.

- [ ] **Step 4: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_session.py tests/tui/test_terminal_input.py tests/coding/test_native_coding_tui_playback.py -q
git diff --check
git add src/loushang/tui/terminal_session.py src/loushang/tui/terminal_input.py src/loushang/coding/ui/native_loop.py tests/tui/test_terminal_session.py
git commit -m "feat(tui): add terminal session lifecycle"
```

Expected: lifecycle tests pass without changing product behavior.

---

### Task 8: Cell Size Query Integration

**Files:**
- Modify: `src/loushang/tui/terminal_session.py`
- Modify: `src/loushang/tui/terminal_capabilities.py`
- Extend: `tests/tui/test_terminal_session.py`
- Extend: `tests/tui/test_terminal_input.py`

- [ ] **Step 1: Write failing cell-size tests**

Assert:

- session sends `ESC[16t` only when `query_cell_size` is true
- `InputBatch.control_events` carries parsed cell-size response
- session stores cell size without entering app events

- [ ] **Step 2: Implement query and consume path**

Add `TerminalSession.consume_control_events()` and update cell size state when
it sees a `cell_size` control event.

- [ ] **Step 3: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_session.py tests/tui/test_terminal_input.py -q
git diff --check
git add src/loushang/tui/terminal_session.py src/loushang/tui/terminal_capabilities.py tests/tui/test_terminal_session.py tests/tui/test_terminal_input.py
git commit -m "feat(tui): query terminal cell size through session"
```

Expected: cell-size response remains internal runtime state.

---

### Task 9: Capability Snapshot Into Theme, Markdown, And Image

**Files:**
- Modify: `src/loushang/tui/theme.py`
- Modify: `src/loushang/tui/markdown/renderer.py`
- Modify: `src/loushang/tui/terminal_image.py`
- Extend: `tests/tui/test_content_theme.py`

- [ ] **Step 1: Write failing adapter tests**

Assert one runtime capability snapshot drives:

- truecolor degradation
- hyperlink stripping
- image protocol fallback

- [ ] **Step 2: Add adapter from runtime capabilities**

Add a small conversion helper rather than renaming existing theme classes in
this slice:

```python
def theme_capabilities_from_runtime(runtime: TerminalRuntimeCapabilities) -> TerminalCapabilities:
    return TerminalCapabilities(truecolor=runtime.truecolor, hyperlinks=runtime.hyperlinks)
```

- [ ] **Step 3: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_content_theme.py tests/tui/test_terminal_capabilities.py -q
git diff --check
git add src/loushang/tui/theme.py src/loushang/tui/markdown/renderer.py src/loushang/tui/terminal_image.py tests/tui/test_content_theme.py
git commit -m "refactor(tui): adapt render capabilities from terminal runtime"
```

Expected: renderers no longer need independent environment probes.

---

### Task 10: Diagnostics And Example Probe

**Files:**
- Create: `examples/tui/37_terminal_capabilities_probe.py`
- Extend: `tests/tui/test_terminal_capabilities.py`
- Optional docs: `docs/architecture/tui/native-terminal-core/testing-strategy.md`

- [ ] **Step 1: Add diagnostic formatter tests**

Assert diagnostics include terminal program, multiplexer status, color depth,
image protocol, keyboard strategy, Windows VT, Termux, Apple normalization, and
capability sources.

- [ ] **Step 2: Add example probe**

The example should print detected environment and capability fields. Do not add
unit tests for the example script unless explicitly requested.

- [ ] **Step 3: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_capabilities.py -q
uv --cache-dir .uv-cache run python examples/tui/37_terminal_capabilities_probe.py
git diff --check
git add src/loushang/tui/terminal_capabilities.py tests/tui/test_terminal_capabilities.py examples/tui/37_terminal_capabilities_probe.py
git commit -m "feat(tui): expose terminal capability diagnostics"
```

Expected: diagnostics are inspectable without a live TUI.

---

## Integration Checkpoint

After Task 10, run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_native_coding_tui_playback.py -q
uv --cache-dir .uv-cache run ruff check src/loushang/tui src/loushang/coding/ui tests/tui tests/coding/test_native_coding_tui_playback.py
git status --branch --short
```

Expected:

- all focused tests pass
- no lint issues
- branch contains small commits matching the task boundaries

## Deferred P2 Work

- tmux passthrough abstraction for image/hyperlink sequences
- alternate screen policy
- cursor style policy
- richer Kitty keyboard flags
- Apple Terminal modifier normalization if a tested implementation exists
- Termux resize behavior if real-world testing shows it is needed
