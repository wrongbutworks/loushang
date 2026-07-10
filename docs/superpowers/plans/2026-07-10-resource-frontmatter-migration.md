# Resource Frontmatter Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the shared frontmatter parser into `loushang.harness.resources.frontmatter` while preserving legacy imports and all coding/method behavior.

**Architecture:** Harness becomes the single parser owner. The top-level resource and coding frontmatter modules become identity-preserving re-export shims, while in-repository coding and method consumers import the focused harness module directly.

**Tech Stack:** Python 3.11+, dataclasses, pytest, Ruff.

---

### Task 1: Establish the harness parser owner

**Files:**
- Create: `tests/harness/resources/test_frontmatter.py`
- Create: `src/loushang/harness/resources/__init__.py`
- Create: `src/loushang/harness/resources/frontmatter.py`

- [x] Add harness-path tests for plain content, newline normalization, block scalars, lists, nested maps, stripping, and parse locations.
- [x] Run the new tests and verify import failure.
- [x] Move the parser implementation without changing accepted syntax or errors.
- [x] Run harness frontmatter tests.

### Task 2: Preserve compatibility and redirect internal consumers

**Files:**
- Modify: `src/loushang/resource/frontmatter.py`
- Modify: `src/loushang/coding/frontmatter.py`
- Modify: `src/loushang/coding/loader/default_resource_loader.py`
- Modify: `src/loushang/method/loader.py`
- Modify: `src/loushang/method/resources.py`
- Modify: frontmatter compatibility and architecture tests

- [x] Add identity tests and an internal-owner import boundary test.
- [x] Run focused tests and verify the owner import assertion fails.
- [x] Replace legacy implementations/imports with harness owner imports and compatibility shims.
- [x] Run resource, coding frontmatter, coding loader, and method resource tests.

### Task 3: Record final ownership

**Files:**
- Modify: `docs/internals/architecture/harness/README.md`
- Modify: `docs/internals/architecture/harness/coding-to-harness-migration-inventory.md`
- Modify: `tests/architecture/test_import_boundaries.py`

- [ ] Add a documentation contract test and verify it fails before status updates.
- [ ] Record harness ownership, compatibility paths, and deferred resource concerns.
- [ ] Run architecture tests.

### Task 4: Complete verification

- [ ] Run Ruff on every changed Python file.
- [ ] Run `git diff --check`.
- [ ] Run the complete non-live test suite.
- [ ] Mark every plan step complete and commit the final status.
