# TUI Editor Buffer Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a shared TUI editing core without regressing Composer, TextInput, terminal width, or completion behavior.

**Architecture:** Build the refactor in independently reviewable stages. Stage 1 adds an internal `EditorBuffer` with no runtime integration. Later stages migrate existing components and shared editing concerns only after focused regressions prove current behavior is preserved. Editing cursor units remain grapheme clusters; terminal cell width remains a rendering concern handled by `visible_width()`.

**Tech Stack:** Python 3.11+, dataclasses, `loushang.tui.cell_width.grapheme_clusters`, pytest, ruff.

**Tracking:** Refs #78.

---

## File Structure

- Create `src/loushang/tui/editor_buffer.py`: internal pure editing buffer for grapheme-cluster text state, cursor movement, deletion, undo, and redo.
- Create `src/loushang/tui/undo_stack.py`: reusable snapshot stack for undo/redo state.
- Create `src/loushang/tui/kill_ring.py`: reusable Emacs-style kill/yank ring.
- Create `src/loushang/tui/word_navigation.py`: reusable word-boundary helpers for grapheme and atom sequences.
- Create `tests/tui/test_editor_buffer.py`: focused regression coverage for the new buffer.
- Later modify `src/loushang/tui/ui_parts/text_input.py`: optional stage 3 migration after buffer hardening is green and reviewed.
- Later modify `src/loushang/tui/ui_parts/composer.py`: stage 5 atom-buffer migration after shared editing infrastructure is green and reviewed.

## Stage 1: Internal EditorBuffer

- [x] **Step 1: Write failing tests**

  Add tests in `tests/tui/test_editor_buffer.py` for:

  - insertion and `__len__` using grapheme cluster count
  - CJK, combining mark, and emoji cluster atomic edits
  - line start/end movement including empty-line no-op behavior
  - delete backward/forward changed status
  - undo/redo for text edits only
  - `set_text()` and `clear()` as programmatic resets that clear undo/redo
  - cursor bounds never escaping `[0, len(buffer)]`

  Run:

  ```bash
  uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_editor_buffer.py -q
  ```

  Expected: FAIL because `loushang.tui.editor_buffer` does not exist yet.

- [x] **Step 2: Implement minimal buffer**

  Create `src/loushang/tui/editor_buffer.py` with:

  - `EditorSnapshot`
  - `EditorBuffer`
  - `value`, `cursor`, `__len__`
  - `set_text`, `clear`, `insert_text`, `insert_newline`
  - `delete_backward`, `delete_forward`
  - `move_left`, `move_right`, `move_to_start`, `move_to_end`
  - `move_to_line_start`, `move_to_line_end`
  - `undo`, `redo`

  Do not export it from `loushang.tui.__init__`.

- [x] **Step 3: Verify stage 1**

  Run:

  ```bash
  uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_editor_buffer.py -q
  uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/editor_buffer.py tests/tui/test_editor_buffer.py
  ```

  Expected: all pass.

- [x] **Step 4: Focused regression**

  Run:

  ```bash
  uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_cell_width.py tests/tui/test_text_input.py tests/tui/test_composer_bottom_frame.py tests/tui/test_input_routing.py -q
  ```

  Expected: all pass.

- [x] **Step 5: Commit**

  ```bash
  git add src/loushang/tui/editor_buffer.py tests/tui/test_editor_buffer.py docs/internals/plans/2026-06-04-tui-editor-buffer-refactor.md
  git commit -m "feat: add tui editor buffer" -m "Refs #78"
  ```

## Stage 2: EditorBuffer Hardening

- [x] Keep `TextInput` and `Composer` unchanged in this stage.
- [x] Add `max_undo_depth` with validation for positive integers or `None`.
- [x] Add `text_before_cursor` and `text_after_cursor` grapheme-cursor helpers.
- [x] Add `delete_range()` and `replace_range()` primitives that return removed text and avoid no-op undo entries.
- [x] Add `move_word_left()` and `move_word_right()` with behavior aligned to existing `TextInput` word movement.
- [x] Add regression tests for undo depth, range edit no-ops, word movement, wide grapheme clusters, and terminal-width independence.
- [x] Run focused TextInput, Composer, cell-width, input-routing, and full TUI regression tests.

## Stage 3: Optional TextInput Migration

- [x] Confirm `TextInput` should migrate behind `EditorBuffer`.
- [x] Add regression tests before changing component internals.
- [x] Preserve existing public behavior, including `on_change`, single-line normalization, scroll, word movement, kill/yank, and undo/redo.
- [x] Keep direct `TextInput.insert_text()` / delete helpers as unrecorded programmatic edits while `handle_input()` edits still create undo entries.
- [x] Align `TextInput.set_text()` and `TextInput.clear()` with `EditorBuffer` programmatic reset semantics by clearing undo/redo history.
- [x] Run focused TextInput, Composer, cell-width, and input-routing tests before committing.

## Stage 4: Reusable Editing Infrastructure

- [x] Add reusable `UndoStack[T]` with max-depth support and empty pop semantics.
- [x] Add reusable `KillRing` with accumulation, rotation, max entries, and tuple-style iteration.
- [x] Add reusable `word_navigation` helpers for cluster/atom kind based word movement.
- [x] Migrate `EditorBuffer` undo/redo and word movement to shared infrastructure.
- [x] Migrate `TextInput` kill/yank state to shared `KillRing`.
- [x] Migrate Composer undo/redo, kill/yank state, and word movement to shared infrastructure without changing atom storage.
- [x] Keep the modules internal to `loushang.tui` and avoid exporting them from `loushang.tui.__init__` until their API has settled.

## Stage 5: ComposerEditBuffer Integration

- [x] Re-map Composer state boundaries before editing: atoms, paste markers, completion cursor columns, render cell widths, history, kill ring, and visual movement.
- [x] Add focused `ComposerEditBuffer` regressions for paste marker value/display semantics, atomic marker deletion, word movement, cursor mapping, and completion prefix replacement.
- [x] Add atom-aware `ComposerEditBuffer` and migrate Composer `_atoms/_cursor/_undo_stack/_redo_stack` to it as the branch final state.
- [x] Do not add feature flags, dual-write state, or long-lived compatibility layers.
- [x] Run full `tests/tui -q`.
- [x] Run native TUI playback before considering merge.
- [x] Run manual smoke before considering merge.

## Cleanup Gate

Do not delete the branch or worktree until:

- all intended stages for this branch are complete,
- focused and full TUI regression suites pass,
- native TUI playback and manual smoke pass,
- the PR is merged,
- the user approves cleanup.
