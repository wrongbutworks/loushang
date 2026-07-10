# Workspace Execution Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move neutral output truncation and process execution mechanics into `loushang.harness.workspace` while preserving coding SDK behavior and product policy ownership.

**Architecture:** Add focused `harness.workspace.truncation` and `harness.workspace.exec` owner modules. Convert existing coding modules into compatibility adapters, redirect product-internal imports to harness, and leave command policy, session resolution, tool projection, and user-facing wording in coding.

**Tech Stack:** Python 3.11+, dataclasses, asyncio subprocess, pytest, Ruff.

---

### Task 1: Define harness truncation behavior

**Files:**
- Create: `tests/harness/workspace/test_truncation.py`
- Create: `src/loushang/harness/workspace/truncation.py`
- Create: `src/loushang/harness/workspace/__init__.py`
- Modify: `src/loushang/coding/tools/truncate.py`

- [ ] Write harness-path tests for head/tail line limits, byte limits, UTF-8 suffixes, metadata, and validation.
- [ ] Run the new tests and verify import failure.
- [ ] Move the neutral implementation to harness and leave coding product helpers plus aliases in the compatibility module.
- [ ] Run harness truncation and coding compatibility tests.

### Task 2: Define harness exec behavior

**Files:**
- Create: `tests/harness/workspace/test_exec.py`
- Create: `src/loushang/harness/workspace/exec/__init__.py`
- Create: `src/loushang/harness/workspace/exec/types.py`
- Create: `src/loushang/harness/workspace/exec/service.py`
- Modify: `src/loushang/coding/exec/types.py`
- Modify: `src/loushang/coding/exec/service.py`
- Modify: `src/loushang/coding/exec/__init__.py`

- [ ] Write harness-path tests for records, backend validation, subprocess output, streaming, preview/artifact behavior, timeout, cancellation, and rolling capture.
- [ ] Run the new tests and verify import failure.
- [ ] Move exec records, protocols, and service to harness using harness truncation.
- [ ] Replace coding implementations with identity-preserving re-export shims.
- [ ] Run harness exec and coding exec tests.

### Task 3: Redirect product internals and prove compatibility

**Files:**
- Modify: coding modules that import `loushang.coding.exec`
- Modify: `tests/coding/test_tool_public_types.py`
- Modify: `tests/architecture/test_import_boundaries.py`

- [ ] Add compatibility identity and harness top-level export tests.
- [ ] Run focused tests and verify the new assertions fail before import rewiring.
- [ ] Redirect internal product imports to `loushang.harness.workspace.exec` while retaining public coding exports.
- [ ] Run exec, policy, extension, session, bash/tool, prompt, and architecture suites.

### Task 4: Update ownership documentation

**Files:**
- Modify: `docs/internals/architecture/harness/README.md`
- Modify: `docs/internals/architecture/harness/coding-to-harness-migration-inventory.md`
- Modify: `docs/internals/architecture/coding/component-interfaces/exec.md`
- Modify: `docs/superpowers/plans/2026-07-10-workspace-execution-substrate.md`

- [ ] Record final harness and coding ownership.
- [ ] Mark all implementation-plan steps complete.
- [ ] Run architecture tests, Ruff on changed Python files, and `git diff --check`.
- [ ] Run the complete non-live test suite before completion.
