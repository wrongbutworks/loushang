# Native TUI Smoke Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact native TUI smoke harness and an automatic playback test that exercises the user-facing native loop path without requiring a real model call.

**Architecture:** Keep product commands in `loushang.coding.ui` and terminal/render mechanics in `loushang.tui`. The smoke test should route input through `InputReader`, `NativeInputRouter`, `NativeSurfaceManager`, runtime overlays, and `RenderLoop` so it catches wiring regressions that unit-level component tests miss.

**Tech Stack:** Python, pytest, ruff, `NativeCodingTuiApp`, `NativeSurfaceManager`, `TuiRuntime`, `InputReader`, playback helpers.

---

### Task 1: Add Native Interactive Playback Smoke Test

**Files:**
- Modify: `tests/coding/test_native_coding_tui_playback.py`

- [x] **Step 1: Write failing test**
  - Verify slash completion can apply `/terminal`.
  - Verify `/terminal` opens the terminal diagnostics overlay.
  - Verify Escape closes the overlay without residue.
  - Verify `/model` opens the model selector overlay and Escape closes it.
  - Verify Alt+< and Alt+> route through composer movement.
  - Verify image fallback remains textual when no image protocol is available.

- [x] **Step 2: Run test and verify failure**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/coding/test_native_coding_tui_playback.py -q
```

- [x] **Step 3: Implement minimal playback harness support**
  - Add a test-local playback helper that wires `TuiRuntime.overlay_host()` into `NativeCodingTuiApp`.
  - Forward `local_text` and `surface_intent` results to `NativeSurfaceManager`.
  - Keep the helper synchronous by using `asyncio.run()` around surface manager calls.

### Task 2: Add Manual Native Coding Smoke Example

**Files:**
- Add: `examples/tui/38_native_coding_smoke.py`

- [x] **Step 1: Add example**
  - Start native coding TUI with a fake session and fake model response.
  - Include slash command completion, `/terminal`, `/model`, and normal prompt submission.
  - Avoid real provider/API dependencies.

- [x] **Step 2: Verify**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/coding/test_native_coding_tui_playback.py -q
uv --cache-dir .uv-cache run ruff check tests/coding/test_native_coding_tui_playback.py examples/tui/38_native_coding_smoke.py
```

- [ ] **Step 3: Commit**

Commit:
```bash
git add docs/superpowers/plans/2026-05-28-native-tui-smoke-playback.md tests/coding/test_native_coding_tui_playback.py examples/tui/38_native_coding_smoke.py
git commit -m "test(coding): add native tui smoke playback"
```

### Task 3: Add Real Native Loop Scripted Replay Guard

**Files:**
- Modify: `tests/coding/test_native_coding_tui_loop.py`
- Modify: `docs/superpowers/plans/2026-05-28-native-tui-smoke-playback.md`

- [x] **Step 1: Write regression test**
  - Run `run_native_coding_tui` with a scripted prompt followed by `/quit`.
  - Verify the prompt and assistant response are rendered.
  - Verify the process exits with the terminal clear-line newline sequence.
  - Verify no status line text appears after the final clear-line sequence.

- [x] **Step 2: Run test and verify existing pass**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/coding/test_native_coding_tui_loop.py::test_native_loop_scripted_prompt_then_quit_exits_without_status_residue -q
```

- [x] **Step 3: Implement minimal fix if required**
  - If the test fails, adjust `run_native_coding_tui` exit cleanup only.
  - Do not change normal render loop behavior unless the failure proves it is needed.
  - Result: no production fix required; current cleanup behavior already satisfies the guard.

- [x] **Step 4: Verify and commit**

Run:
```bash
uv --cache-dir .uv-cache run pytest tests/coding/test_native_coding_tui_loop.py tests/coding/test_native_coding_tui_playback.py -q
uv --cache-dir .uv-cache run ruff check tests/coding/test_native_coding_tui_loop.py tests/coding/test_native_coding_tui_playback.py examples/tui/38_native_coding_smoke.py
git diff --check
```

Commit:
```bash
git add docs/superpowers/plans/2026-05-28-native-tui-smoke-playback.md tests/coding/test_native_coding_tui_loop.py
git commit -m "test(coding): guard native tui scripted exit cleanup"
```
