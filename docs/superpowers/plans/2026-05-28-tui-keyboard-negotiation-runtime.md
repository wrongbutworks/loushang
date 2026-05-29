# TUI Keyboard Negotiation Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the runtime keyboard protocol negotiation loop so `TerminalSession` performs Kitty query, consumes Kitty response, falls back to modifyOtherKeys only after a deadline, and disables only the protocol modes actually enabled.

**Architecture:** Keep `InputReader` as the only parser and `KeyboardProtocolController` as the pure state machine. Move live protocol writes into `TerminalSession`, and let the native loop wake for protocol fallback deadlines just like it already wakes for pending ESC idle flushes.

**Tech Stack:** Python 3.13, pytest, `uv --cache-dir .uv-cache run --extra dev pytest`, existing `loushang.tui` terminal/session/native loop modules.

---

### Task 1: TerminalSession Owns Keyboard Protocol Writes

**Files:**
- Modify: `src/loushang/tui/terminal_session.py`
- Modify: `src/loushang/tui/terminal_input.py`
- Test: `tests/tui/test_terminal_session.py`

- [ ] **Step 1: Write failing tests**

Add tests showing:

- session startup writes `ESC[?u` only, not immediate `ESC[>4;2m`
- consuming `kitty_protocol` writes `ESC[>7u`
- session exit after Kitty activation writes `ESC[<u`
- fallback due writes `ESC[>4;2m`
- session exit after fallback writes `ESC[>4;0m`

- [ ] **Step 2: Implement session ownership**

Add `keyboard_controller` state to `TerminalSession`. The default raw mode factory should pass `keyboard_protocols=False` into `TerminalInputMode`, so `TerminalInputMode` does not duplicate protocol writes when used through `TerminalSession`.

- [ ] **Step 3: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_session.py tests/tui/test_keyboard_protocol.py tests/tui/test_terminal_input.py -q
git diff --check
git add src/loushang/tui/terminal_session.py src/loushang/tui/terminal_input.py tests/tui/test_terminal_session.py
git commit -m "feat(tui): run keyboard protocol negotiation from terminal session"
```

### Task 2: Native Loop Wakes For Keyboard Fallback Deadline

**Files:**
- Modify: `src/loushang/tui/terminal_input.py`
- Modify: `src/loushang/coding/ui/native_loop.py`
- Test: `tests/tui/test_terminal_input.py`
- Test: `tests/coding/test_native_coding_tui_playback.py`

- [ ] **Step 1: Write failing tests**

Add tests showing:

- `read_input_chunk_or_render_tick(..., idle_wakeup_ms=...)` returns `None` after that wakeup deadline
- native loop helper can poll terminal runtime fallback
- terminal control events still reach `TerminalSession.consume_control_events`

- [ ] **Step 2: Implement wakeup plumbing**

Add an optional idle wakeup deadline to `read_input_chunk_or_render_tick`. In native loop, pass the minimum of pending input idle timeout and `TerminalSession.next_wakeup_delay_ms()`.

- [ ] **Step 3: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_input.py tests/tui/test_terminal_session.py tests/coding/test_native_coding_tui_playback.py -q
git diff --check
git add src/loushang/tui/terminal_input.py src/loushang/coding/ui/native_loop.py tests/tui/test_terminal_input.py tests/coding/test_native_coding_tui_playback.py
git commit -m "feat(tui): wake native loop for keyboard protocol fallback"
```

### Task 3: Integration Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run focused checks**

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_session.py tests/tui/test_keyboard_protocol.py tests/tui/test_terminal_input.py tests/coding/test_native_coding_tui_playback.py -q
uv --cache-dir .uv-cache run ruff check src/loushang/tui src/loushang/coding/ui tests/tui tests/coding/test_native_coding_tui_playback.py
```

- [ ] **Step 2: Commit formatting only if needed**

If ruff fixes imports, commit that separately with:

```bash
git commit -m "chore(tui): format keyboard negotiation imports"
```
