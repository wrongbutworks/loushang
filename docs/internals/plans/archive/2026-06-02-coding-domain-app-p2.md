# Coding DomainApp P2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first `CodingDomainApp` slice so explicit `--method <id-or-name>` can guide one coding turn while preserving current behavior without `--method`.

**Architecture:** Add a small `loushang.coding.domain` facade that consumes P1 method APIs and returns a prepared prompt plus `method_id`. Keep `AgentSession` unchanged; CLI applies the prepared prompt and threads `method_id` through prompt/print work logging only.

**Tech Stack:** Python dataclasses, existing `loushang.method` APIs, existing coding CLI/prompt/print mode, pytest, ruff.

---

### Task 1: Coding Domain Types

**Files:**
- Create: `src/loushang/coding/domain/__init__.py`
- Create: `src/loushang/coding/domain/types.py`
- Test: `tests/coding/domain/test_coding_domain_app.py`

- [x] Write failing tests for `CodingDomainRequest` and `CodingDomainPreparedTurn` defaults.
- [x] Verify tests fail because `loushang.coding.domain` does not exist.
- [x] Implement frozen dataclasses and public exports.
- [x] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/domain/test_coding_domain_app.py -q`.
- [x] Commit with `feat: add coding domain p2 types`.

### Task 2: CodingDomainApp

**Files:**
- Create: `src/loushang/coding/domain/app.py`
- Modify: `src/loushang/coding/domain/__init__.py`
- Test: `tests/coding/domain/test_coding_domain_app.py`

- [x] Write failing tests for no-method unchanged prompt, explicit skill-backed method, explicit `methods/**/SKILL.md` method, missing method error, and empty guidance behavior.
- [x] Verify tests fail because `CodingDomainApp` does not exist.
- [x] Implement `DEFAULT_GUIDANCE_TEMPLATE`, `CodingDomainApp.prepare_turn(...)`, method lookup, compile/project, and prompt assembly.
- [x] Keep `prepare_turn(...)` synchronous.
- [x] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/domain/test_coding_domain_app.py tests/method -q`.
- [x] Commit with `feat: prepare method-guided coding turns`.

### Task 3: Prompt And Print Work Metadata Plumbing

**Files:**
- Modify: `src/loushang/coding/prompt_command.py`
- Modify: `src/loushang/coding/mode/print_mode.py`
- Modify: `src/loushang/coding/mode/base.py`
- Test: `tests/coding/test_print_mode.py`
- Test: `tests/coding/test_prompt_command.py`

- [x] Write failing tests showing `method_id` reaches `CodingWorkShell` when work logging is active in prompt and print paths.
- [x] Verify tests fail because prompt/print APIs do not accept `method_id`.
- [x] Add optional `method_id: str | None = None` to `run_prompt_command`, `_run_turn`, `_run_prompt_session`, `PrintMode`, `run_print_mode`, `create_mode_adapter`, and `run_mode`.
- [x] Pass `method_id` only to `CodingWorkShell.submit_coding_turn(...)`.
- [x] Run focused prompt/print tests.
- [x] Commit with `feat: thread method id through coding runners`.

### Task 4: CLI `--method`

**Files:**
- Modify: `src/loushang/coding/cli/args.py`
- Modify: `src/loushang/coding/cli/__main__.py`
- Test: `tests/coding/test_cli.py`

- [x] Write failing parse tests for `--method`.
- [x] Write failing CLI tests for `--method review -p`, `--method review --mode print`, missing method, unsupported TUI/RPC, and unchanged no-method behavior.
- [x] Add `method: str | None` to `CliArgs` and parser.
- [x] Add runtime validation for unsupported TUI/RPC mode.
- [x] Use `CodingDomainApp.prepare_turn(...)` after resolving print input and before dispatching prompt/print/mode runners.
- [x] Pass `prepared_prompt` and `method_id` into prompt/print/mode runners.
- [x] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_cli.py tests/coding/domain -q`.
- [x] Commit with `feat: add explicit method guided CLI turns`.

### Task 5: Regression

**Files:**
- Modify as needed from previous tasks only.

- [x] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/domain tests/coding/test_cli.py tests/method tests/work -q`.
- [x] Run the broad planned ruff target: `src/loushang/coding/domain`, `src/loushang/coding/cli`, `src/loushang/coding/mode`, `src/loushang/coding/prompt_command.py`, `tests/coding/domain`, and `tests/coding/test_cli.py`.
- [x] Manually verify method-guided CLI dispatch with a temporary `methods/task/review/SKILL.md` and a fake prompt runner to avoid real provider calls.
- [x] Remove temporary demo files.
- [x] Commit any final fixes.

Note: the broader planned `src/loushang/coding/mode` ruff target initially exposed import-order findings in `mode/__init__.py` and `mode/rpc_mode.py`; those were fixed as a mechanical follow-up.
