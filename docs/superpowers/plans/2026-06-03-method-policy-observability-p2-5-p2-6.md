# MethodPolicy And Method Observability P2.5/P2.6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-turn method policy controls and method observability for work-log inspection without changing default coding behavior.

**Architecture:** Keep method resources in `loushang.method`; put usage policy in `loushang.coding.domain`. CLI maps flags to `MethodPolicy`, `CodingDomainApp` prepares the turn, and work-log inspect only reads existing event metadata.

**Tech Stack:** Python dataclasses, existing CLI parser, existing `CodingDomainApp`, existing `JsonlEventLogBackend`, pytest, ruff.

---

### Task 1: MethodPolicy Core

**Files:**
- Modify: `src/loushang/coding/domain/types.py`
- Modify: `src/loushang/coding/domain/__init__.py`
- Test: `tests/coding/domain/test_coding_domain_app.py`

- [x] Write failing tests for `MethodPolicy` defaults, `MethodPolicy.off()`, and `MethodPolicy.explicit("review")`.
- [x] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/domain/test_coding_domain_app.py -q` and verify it fails because `MethodPolicy` does not exist.
- [x] Add frozen `MethodPolicy` dataclass with `mode: str = "explicit"` and `selected_method: str | None = None`.
- [x] Add `off()` and `explicit(selected_method)` classmethods.
- [x] Export `MethodPolicy` from `loushang.coding.domain`.
- [x] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/domain/test_coding_domain_app.py -q`.
- [x] Commit with `feat: add coding method policy`.

### Task 2: CodingDomainApp Policy Resolution

**Files:**
- Modify: `src/loushang/coding/domain/types.py`
- Modify: `src/loushang/coding/domain/app.py`
- Test: `tests/coding/domain/test_coding_domain_app.py`

- [x] Write failing tests for `CodingDomainRequest(method_policy=MethodPolicy.off())` suppressing a method, `method_policy` taking precedence over `method`, and unsupported policy mode raising `ValueError`.
- [x] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/domain/test_coding_domain_app.py -q` and verify expected failures.
- [x] Add `method_policy: MethodPolicy | None = None` to `CodingDomainRequest`.
- [x] In `CodingDomainApp.prepare_turn(...)`, resolve policy as `request.method_policy or MethodPolicy.explicit(request.method)`.
- [x] Implement mode handling:
  - `off`: return original prompt unchanged with no method metadata.
  - `explicit` with no selected method: return original prompt unchanged.
  - `explicit` with selected method: current P2 lookup/compile/project behavior.
  - otherwise raise `ValueError("unsupported method policy mode: <mode>")`.
- [x] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/domain/test_coding_domain_app.py tests/method -q`.
- [x] Commit with `feat: apply method policy in coding domain app`.

### Task 3: CLI `--no-method`

**Files:**
- Modify: `src/loushang/coding/cli/args.py`
- Modify: `src/loushang/coding/cli/__main__.py`
- Test: `tests/coding/test_cli.py`

- [ ] Write failing parser test for `--no-method`.
- [ ] Write failing CLI tests for:
  - `--no-method -p "hello"` dispatches original prompt and `method_id is None`.
  - `--method review --no-method -p "hello"` exits `2`.
  - existing `--method review -p "hello"` still applies method guidance.
- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_cli.py tests/coding/domain -q` and verify expected failures.
- [ ] Add `no_method: bool` to `CliArgs`.
- [ ] Add `--no-method` to parser and `_BUILTIN_FLAG_NAMES`.
- [ ] Add static conflict validation for `args.method and args.no_method`.
- [ ] Map CLI flags to `MethodPolicy.off()` or `MethodPolicy.explicit(args.method)` before calling `CodingDomainApp.prepare_turn(...)`.
- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_cli.py tests/coding/domain -q`.
- [ ] Commit with `feat: add no-method cli switch`.

### Task 4: Work-Log Method Observability

**Files:**
- Modify: `src/loushang/coding/cli/__main__.py`
- Test: `tests/coding/test_cli.py`

- [ ] Write failing tests for `work-log inspect` text output including `method_id` when an operation or event payload contains method metadata.
- [ ] Write failing test for `work-log inspect --work-log-inspect-format json` including `method_id` only when present.
- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_cli.py -q` and verify expected failures.
- [ ] Add helper `_work_log_entry_method_id(entry) -> str`.
- [ ] Add trailing `method_id` column to `_write_work_log_text(...)`.
- [ ] Add `method_id` conditionally to `_work_log_entry_summary(...)`.
- [ ] Keep entries without method metadata readable with an empty text column and no JSON key.
- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_cli.py -q`.
- [ ] Commit with `feat: expose method id in work log inspect`.

### Task 5: Missing Method Error Hint

**Files:**
- Modify: `src/loushang/coding/cli/__main__.py`
- Test: `tests/coding/test_cli.py`

- [ ] Write failing test asserting missing method error includes `Run 'loushang method list' to inspect available methods.`
- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_cli.py -q` and verify expected failure.
- [ ] Add a small formatter/helper for method lookup failures or special-case the `ValueError` from `CodingDomainApp`.
- [ ] Keep exit code `1`.
- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_cli.py -q`.
- [ ] Commit with `feat: add missing method cli hint`.

### Task 6: Regression And PR Prep

**Files:**
- Modify previous files only.

- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/domain tests/coding/test_cli.py tests/method tests/work -q`.
- [ ] Run `uv --cache-dir .uv-cache run ruff check src/loushang/coding/domain src/loushang/coding/cli tests/coding/domain tests/coding/test_cli.py`.
- [ ] Run a manual CLI fake-runner or work-log focused verification if needed by changed behavior.
- [ ] Commit any final fixes.
- [ ] Push branch and create PR referencing issues #42 and #43.
