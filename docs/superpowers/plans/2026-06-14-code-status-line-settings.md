# Code Status Line Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add provider-owned Status Line settings for the native coding TUI using the public TUI `StatusBar` API.

**Architecture:** Product status-line state lives in `CodingTuiStatusProvider` as `StatusLineSettings`. `NativeCodingTuiApp.state` mirrors effective settings for rendering, while real and preview status lines share `status_line_fields(...)`.

**Tech Stack:** Python 3.11 dataclasses, pytest, existing `loushang.tui` `StatusBar`, `StatusField`, `SearchableList`, and `TabGroup`.

---

## File Structure

- Create `src/loushang/coding/ui/status_line.py`: settings dataclasses, preview snapshot, field builder, separator/style mappings, workspace label helper.
- Modify `src/loushang/coding/ui/status_provider.py`: provider owns `StatusLineSettings`; old visibility APIs become compatibility wrappers.
- Modify `src/loushang/coding/ui/native_state.py`: add mirrored `statusline_settings`.
- Modify `src/loushang/coding/ui/native_app.py`: add settings mirror methods, preview snapshot, and shared builder status bar rendering.
- Modify `src/loushang/coding/ui/settings_page.py`: add Status Line tab with rows, cycles, and live preview; remove old Config row.
- Modify `src/loushang/coding/ui/native_surfaces.py`: mirror provider-owned settings after `/statusline` and settings submits.
- Update focused tests under `tests/coding/`.

## Task 1: Status Line Model And Builder

**Files:**
- Create: `src/loushang/coding/ui/status_line.py`
- Test: `tests/coding/test_ui_status_line.py`

- [ ] **Step 1: Write failing tests**
  Cover default settings, priority/token order, queue/message `auto|true|false`, separator mapping, style mapping, and workspace label behavior.

- [ ] **Step 2: Verify RED**
  Run: `uv run pytest tests/coding/test_ui_status_line.py -q`
  Expected: import failure for `loushang.coding.ui.status_line`.

- [ ] **Step 3: Implement minimal module**
  Add frozen dataclasses:
  `StatusLineSettings`, `StatusLinePreviewSnapshot`.
  Add `status_line_fields(snapshot, settings)`, `status_line_separator(settings)`, `status_line_style_mode(settings)`, and `cwd_label(cwd)`.

- [ ] **Step 4: Verify GREEN**
  Run: `uv run pytest tests/coding/test_ui_status_line.py -q`
  Expected: pass.

## Task 2: Provider Ownership

**Files:**
- Modify: `src/loushang/coding/ui/status_provider.py`
- Test: `tests/coding/test_ui_status_provider.py`

- [ ] **Step 1: Write failing provider tests**
  Prove provider exposes effective `StatusLineSettings`, `set_visible()` updates `settings.enabled`, `apply_statusline_setting()` updates arbitrary Status Line rows, and legacy `settings_list()` remains compatible.

- [ ] **Step 2: Verify RED**
  Run: `uv run pytest tests/coding/test_ui_status_provider.py -q`
  Expected: missing settings API assertions fail.

- [ ] **Step 3: Implement provider settings ownership**
  Replace canonical `_visible` with `_statusline_settings`; expose `statusline_settings()`, `apply_statusline_settings(settings)`, and `apply_statusline_setting(item_id, value)`.

- [ ] **Step 4: Verify GREEN**
  Run: `uv run pytest tests/coding/test_ui_status_provider.py -q`
  Expected: pass.

## Task 3: Native App Mirror And Shared Rendering

**Files:**
- Modify: `src/loushang/coding/ui/native_state.py`
- Modify: `src/loushang/coding/ui/native_app.py`
- Test: `tests/coding/test_ui_status_line.py`

- [ ] **Step 1: Write failing app integration tests**
  Prove `NativeCodingTuiApp.statusline_preview_snapshot()` includes queue/message data and `_status_bar()` uses the same `status_line_fields(...)` output as preview.

- [ ] **Step 2: Verify RED**
  Run: `uv run pytest tests/coding/test_ui_status_line.py -q`
  Expected: missing app APIs fail.

- [ ] **Step 3: Implement app mirror**
  Add `statusline_settings` to native state, `set_statusline_settings(settings)`, `statusline_preview_snapshot()`, and update `_status_bar()` to use `StatusBar(fields, separator=..., style_mode=...)`.

- [ ] **Step 4: Verify GREEN**
  Run: `uv run pytest tests/coding/test_ui_status_line.py -q`
  Expected: pass.

## Task 4: Status Line Settings Tab

**Files:**
- Modify: `src/loushang/coding/ui/settings_page.py`
- Test: `tests/coding/test_native_settings_page.py`

- [ ] **Step 1: Write failing settings-page tests**
  Cover tab order, Config default focus, Config no longer showing old `Status line` row, Status Line rows, search, cycles, and live preview.

- [ ] **Step 2: Verify RED**
  Run: `uv run pytest tests/coding/test_native_settings_page.py -q`
  Expected: missing Status Line tab and old Config row assertions fail.

- [ ] **Step 3: Implement Status Line tab**
  Add a reusable settings-list page for Status Line rows, cycle values by id, refresh preview from provider settings, and render preview via `StatusBar(status_line_fields(...))`.

- [ ] **Step 4: Verify GREEN**
  Run: `uv run pytest tests/coding/test_native_settings_page.py -q`
  Expected: pass.

## Task 5: Surface Sync And Playback

**Files:**
- Modify: `src/loushang/coding/ui/native_surfaces.py`
- Test: `tests/coding/test_native_coding_tui_surfaces.py`
- Test: `tests/coding/test_native_coding_tui_playback.py`

- [ ] **Step 1: Write failing sync/playback tests**
  Cover settings submit mirroring provider settings into app, `/statusline on|off` compatibility, and `/settings` navigation to Status Line tab to toggle enabled/style/field.

- [ ] **Step 2: Verify RED**
  Run: `uv run pytest tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_playback.py -q`
  Expected: new sync/navigation assertions fail.

- [ ] **Step 3: Implement sync boundary**
  In `/statusline`, update provider first then call `app.set_statusline_settings(provider.statusline_settings())`. In settings submit, mirror returned effective settings into app.

- [ ] **Step 4: Verify GREEN**
  Run: `uv run pytest tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_playback.py -q`
  Expected: pass.

## Task 6: Final Verification

- [ ] Run `uv run pytest tests/coding/test_ui_status_line.py -q`
- [ ] Run `uv run pytest tests/coding/test_ui_status_provider.py tests/coding/test_native_settings_page.py -q`
- [ ] Run `uv run pytest tests/coding/test_native_coding_tui_surfaces.py tests/coding/test_native_coding_tui_playback.py -q`
- [ ] Run `uv run pytest tests -q`
- [ ] Run `uv run ruff check src/loushang/coding/ui tests/coding`
- [ ] Report any failures that cannot be fixed in scope.

## Out Of Scope

- Do not add `/config` alias in this implementation.
- Do not import private helpers from `loushang.tui.ui_parts.status`.
- Do not add persistence unless a later task explicitly requests it.
