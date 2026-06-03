# TUI Runtime Overlay, Diagnostics, Editor, And Image Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the next four native TUI slices: runtime overlay migration closure, terminal capability diagnostics, editor input P1 behavior, and terminal image protocol closure.

**Architecture:** Keep `loushang.tui` as the reusable terminal foundation and keep product commands in `loushang.coding.ui`. Runtime-owned overlay surfaces host interactive UI; coding surfaces only create product content and handle product intents. Terminal capability snapshots should drive diagnostics and image rendering without ad hoc product checks.

**Tech Stack:** Python, pytest, ruff, `loushang.tui` render/input/runtime modules, `loushang.coding.ui` native app/surface loop.

---

### Task 1: Close Runtime Overlay Surface Migration

**Files:**
- Modify: `src/loushang/coding/ui/native_surfaces.py`
- Modify: `src/loushang/coding/ui/native_input.py`
- Test: `tests/coding/test_native_coding_tui_surfaces.py`
- Test: `tests/coding/test_native_coding_tui_loop.py`

- [ ] **Step 1: Write failing tests**
  - Verify command/settings/info surfaces opened through `NativeSurfaceManager` use `app.surface_host` when present.
  - Verify Escape from a runtime overlay closes the overlay and does not route into composer.
  - Verify `NativeSurfaceManager.close_surface()` is idempotent after the host has already closed an entry.

- [ ] **Step 2: Run tests and verify failure**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_loop.py -q
```

Expected: new tests fail until closure behavior is implemented.

- [ ] **Step 3: Implement minimal closure**
  - Add a small helper for opening runtime overlay surfaces with stable geometry.
  - Keep `active_surface` only as a non-runtime fallback.
  - Ensure closing and Escape are idempotent.

- [ ] **Step 4: Verify and commit**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_loop.py -q
uv --cache-dir .uv-cache run ruff check src/loushang/coding/ui/native_surfaces.py src/loushang/coding/ui/native_input.py tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_loop.py
```

Commit:
```bash
git add src/loushang/coding/ui/native_surfaces.py src/loushang/coding/ui/native_input.py tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_loop.py
git commit -m "test(coding): cover runtime overlay surface closure"
```

### Task 2: Add Terminal Capability Diagnostics Surface

**Files:**
- Modify: `src/loushang/coding/ui/intent.py`
- Modify: `src/loushang/coding/ui/native_app.py`
- Modify: `src/loushang/coding/ui/native_loop.py`
- Modify: `src/loushang/coding/ui/native_surfaces.py`
- Test: `tests/coding/test_ui_controller.py`
- Test: `tests/coding/test_native_coding_tui_surfaces.py`
- Test: `tests/coding/test_native_coding_tui_loop.py`

- [ ] **Step 1: Write failing tests**
  - `/terminal` parses to a new terminal diagnostics intent.
  - `NativeSurfaceManager` opens a runtime overlay info panel for terminal diagnostics.
  - Native loop exposes `TerminalSession.diagnostics()` to the app while the loop is running.

- [ ] **Step 2: Run tests and verify failure**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/coding/test_ui_controller.py tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_loop.py -q
```

- [ ] **Step 3: Implement diagnostics**
  - Add `TerminalDiagnosticsIntent`.
  - Store a read-only diagnostics provider on `NativeCodingTuiApp`.
  - Wire native loop to update that provider from `TerminalSession`.
  - Render diagnostics as plain info text: protocol, color, images, cell size, multiplexer, ssh, platform hints.

- [ ] **Step 4: Verify and commit**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/coding/test_ui_controller.py tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_loop.py -q
uv --cache-dir .uv-cache run ruff check src/loushang/coding/ui/intent.py src/loushang/coding/ui/native_app.py src/loushang/coding/ui/native_loop.py src/loushang/coding/ui/native_surfaces.py tests/coding/test_ui_controller.py tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_loop.py
```

Commit:
```bash
git add src/loushang/coding/ui/intent.py src/loushang/coding/ui/native_app.py src/loushang/coding/ui/native_loop.py src/loushang/coding/ui/native_surfaces.py tests/coding/test_ui_controller.py tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_loop.py
git commit -m "feat(coding): add terminal diagnostics surface"
```

### Task 3: Finish Editor/Input P1 Behavior

**Files:**
- Modify: `src/loushang/tui/input.py`
- Modify: `src/loushang/tui/keybindings.py`
- Modify: `src/loushang/tui/ui_parts/composer.py`
- Test: `tests/tui/test_terminal_input.py`
- Test: `tests/tui/test_composer_bottom_frame.py`

- [ ] **Step 1: Write failing tests**
  - Alt-arrow legacy sequences normalize to `alt+up/down/left/right` in the parser and legacy adapter.
  - Character jump mode consumes the next typed character and clears on Escape.
  - Large paste marker deletes and undoes as a single atom.

- [ ] **Step 2: Run tests and verify failure**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/tui/test_terminal_input.py tests/tui/test_composer_bottom_frame.py -q
```

- [ ] **Step 3: Implement minimal fixes**
  - Complete legacy key alias normalization for Alt arrows.
  - Make jump mode cancellation explicit.
  - Keep paste marker behavior atomic.

- [ ] **Step 4: Verify and commit**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/tui/test_terminal_input.py tests/tui/test_composer_bottom_frame.py -q
uv --cache-dir .uv-cache run ruff check src/loushang/tui/input.py src/loushang/tui/keybindings.py src/loushang/tui/ui_parts/composer.py tests/tui/test_terminal_input.py tests/tui/test_composer_bottom_frame.py
```

Commit:
```bash
git add src/loushang/tui/input.py src/loushang/tui/keybindings.py src/loushang/tui/ui_parts/composer.py tests/tui/test_terminal_input.py tests/tui/test_composer_bottom_frame.py
git commit -m "feat(tui): tighten editor input behavior"
```

### Task 4: Close Terminal Image Protocol Loop

**Files:**
- Modify: `src/loushang/tui/terminal_image.py`
- Modify: `src/loushang/tui/runtime.py`
- Test: `tests/tui/test_content_theme.py`
- Test: `tests/tui/test_runtime_render_coalescing.py`

- [ ] **Step 1: Write failing tests**
  - Image rendering uses a supplied runtime capability snapshot instead of env auto-detection.
  - `Image.render()` keeps fallback textual output stable when images are disabled.
  - Runtime cleanup emits Kitty deletion only for rendered Kitty image ids and is idempotent.

- [ ] **Step 2: Run tests and verify failure**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/tui/test_content_theme.py tests/tui/test_runtime_render_coalescing.py -q
```

- [ ] **Step 3: Implement minimal closure**
  - Keep capability snapshot precedence over env detection.
  - Add helper coverage for fallback and iTerm2/Kitty protocol selection.
  - Ensure runtime cleanup remains tied to rendered logical lines.

- [ ] **Step 4: Full verification and commit**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/tui tests/coding/test_native_coding_tui_app.py tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_input.py tests/coding/test_native_coding_tui_loop.py tests/coding/test_ui_controller.py -q
uv --cache-dir .uv-cache run ruff check src/loushang/tui src/loushang/coding/ui tests/tui tests/coding/test_native_coding_tui_app.py tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_input.py tests/coding/test_native_coding_tui_loop.py tests/coding/test_ui_controller.py
git diff --check
```

Commit:
```bash
git add src/loushang/tui/terminal_image.py src/loushang/tui/runtime.py tests/tui/test_content_theme.py tests/tui/test_runtime_render_coalescing.py
git commit -m "test(tui): cover terminal image protocol closure"
```
