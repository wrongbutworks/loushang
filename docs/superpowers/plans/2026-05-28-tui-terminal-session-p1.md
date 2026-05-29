# TUI Terminal Session P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the next practical terminal-session capability layer: optional mouse protocol lifecycle and inspectable session runtime diagnostics.

**Architecture:** Keep `TerminalSession` as the owner of terminal lifecycle writes. Mouse mode is capability-gated and off by default; applications can opt in by setting `TerminalRuntimeCapabilities.enable_mouse=True`. Diagnostics are read-only snapshots from `TerminalSession`, not a second protocol controller.

**Tech Stack:** Python 3.13, pytest, `uv --cache-dir .uv-cache run --extra dev pytest`, existing `loushang.tui` terminal/session modules.

---

### Task 1: Optional Mouse Mode Lifecycle

**Files:**
- Modify: `src/loushang/tui/terminal_session.py`
- Test: `tests/tui/test_terminal_session.py`

- [ ] **Step 1: Write failing tests**

Add tests showing:

- `enable_mouse=True` writes SGR mouse startup sequences during session enter.
- session exit disables only mouse modes that were enabled.
- mouse mode remains off by default.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_session.py -q
```

Expected: mouse lifecycle tests fail because `TerminalSession` does not yet write mouse protocol sequences.

- [ ] **Step 3: Implement minimal lifecycle**

In `TerminalSession`:

- define mouse enable sequences: `ESC[?1002h` and `ESC[?1006h`
- define mouse disable sequences: `ESC[?1006l` and `ESC[?1002l`
- write enable sequences only when `capabilities.enable_mouse` is true and terminal control writes are allowed
- remember whether mouse was enabled
- write disable sequences during `__exit__` only if mouse was enabled

- [ ] **Step 4: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_session.py tests/tui/test_terminal_input.py -q
git diff --check
git add src/loushang/tui/terminal_session.py tests/tui/test_terminal_session.py
git commit -m "feat(tui): add optional mouse mode lifecycle"
```

### Task 2: Terminal Session Runtime Diagnostics

**Files:**
- Modify: `src/loushang/tui/terminal_session.py`
- Test: `tests/tui/test_terminal_session.py`

- [ ] **Step 1: Write failing diagnostics tests**

Add tests showing diagnostics include:

- keyboard protocol state
- mouse mode active state
- cell size when available
- static capability flags such as image protocol, windows VT input, multiplexer, SSH, and Termux

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_session.py -q
```

Expected: diagnostics tests fail because `TerminalSession` does not yet expose runtime diagnostics.

- [ ] **Step 3: Implement read-only diagnostics**

Add a small frozen dataclass such as `TerminalSessionDiagnostics` in `terminal_session.py` and a `diagnostics()` method on `TerminalSession`.

Keep this method side-effect free. It should only report current state from:

- `self.capabilities`
- `self.cell_size`
- `self._keyboard_controller`
- mouse lifecycle state

- [ ] **Step 4: Verify and commit**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_session.py tests/tui/test_terminal_capabilities.py -q
git diff --check
git add src/loushang/tui/terminal_session.py tests/tui/test_terminal_session.py
git commit -m "feat(tui): expose terminal session diagnostics"
```

### Task 3: Integration Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run focused and broad checks**

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_terminal_session.py tests/tui/test_terminal_capabilities.py tests/tui/test_terminal_input.py tests/coding/test_native_coding_tui_playback.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run ruff check src/loushang/tui src/loushang/coding/ui tests/tui tests/coding/test_native_coding_tui_playback.py
```

- [ ] **Step 2: Commit formatting only if needed**

If ruff changes imports, commit separately:

```bash
git commit -m "chore(tui): format terminal session p1 imports"
```
