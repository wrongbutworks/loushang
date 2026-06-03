# Thinking Main Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the useful thinking event, state, and rendering capabilities from `loushang-thinking` into `main` without importing its aggressive default-thinking strategy or transcript-trimming experiments.

**Architecture:** Extend the existing `main` thinking primitives (`ThinkingRecord`, raw thinking events, transcript rendering) through the missing coding UI layers: event projection, native state, transcript styling, and renderer lifecycle. Then add provider/session compatibility checks so thinking is only enabled when models actually support reasoning, while preserving `main`'s current stability work on overflow recovery and transcript performance.

**Tech Stack:** Python, pytest, native TUI render pipeline, coding session/runtime, provider adapters

---

### Task 1: Add native/print thinking regression tests

**Files:**
- Modify: `tests/coding/test_native_coding_tui_events.py`
- Modify: `tests/coding/test_ui_renderer.py`
- Modify: `tests/coding/test_print_mode.py`

- [ ] **Step 1: Write failing tests for native thinking projection**
- [ ] **Step 2: Run targeted pytest to verify failures**
- [ ] **Step 3: Write failing tests for print/event renderer thinking lifecycle**
- [ ] **Step 4: Run targeted pytest to verify failures**

### Task 2: Implement thinking projection and native state support

**Files:**
- Modify: `src/loushang/coding/ui/native_events.py`
- Modify: `src/loushang/coding/ui/native_state.py`

- [ ] **Step 1: Add thinking event handling in native projector**
- [ ] **Step 2: Add thinking draft buffer lifecycle to native state**
- [ ] **Step 3: Run targeted pytest for native thinking tests**

### Task 3: Implement thinking rendering in native/print UI

**Files:**
- Modify: `src/loushang/coding/ui/native_app.py`
- Modify: `src/loushang/coding/ui/transcript_style.py`
- Modify: `src/loushang/coding/ui/events.py`
- Modify: `src/loushang/coding/ui/renderer.py`
- Modify: `src/loushang/tui/transcript.py`

- [ ] **Step 1: Add thinking draft/render support to native transcript region**
- [ ] **Step 2: Add thinking-specific transcript styling**
- [ ] **Step 3: Add thinking lifecycle APIs to coding renderer and event renderer**
- [ ] **Step 4: Run targeted pytest for native and print rendering tests**

### Task 4: Integrate model/provider compatibility

**Files:**
- Modify: `src/loushang/ai/providers/anthropic.py`
- Modify: `src/loushang/coding/bootstrap.py`
- Modify: `src/loushang/coding/session/agent_session.py`
- Modify: `src/loushang/coding/ui/mode.py`
- Modify: `tests/coding/test_bootstrap.py`
- Modify: `tests/coding/test_agent_session.py`

- [ ] **Step 1: Write failing tests for capability-aware thinking normalization**
- [ ] **Step 2: Run targeted pytest to verify failures**
- [ ] **Step 3: Implement provider/session normalization changes**
- [ ] **Step 4: Run targeted pytest for capability-aware thinking behavior**

### Task 5: Run focused regression suite

**Files:**
- Verify only

- [ ] **Step 1: Run targeted pytest for thinking integration**
- [ ] **Step 2: Run targeted pytest for overflow/timestamp regressions**
- [ ] **Step 3: Run ruff against modified files**
- [ ] **Step 4: Summarize remaining gaps before broader rollout**
