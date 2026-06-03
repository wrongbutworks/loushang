# Method P1 Resource Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the P1 `loushang.method` package so existing skills and project method resources can be discovered, adapted, compiled, and projected without changing current CLI or `AgentSession` behavior.

**Architecture:** Add a small independent `loushang.method` package. Keep `SkillDescriptor` knowledge isolated in `skill_adapter.py`, keep loader precedence in `loader.py`, and expose data-only objects from `types.py`.

**Tech Stack:** Python dataclasses, existing `loushang.coding.loader.DefaultResourceLoader`, pytest, ruff.

---

### Task 1: Core Method Types

**Files:**
- Create: `src/loushang/method/__init__.py`
- Create: `src/loushang/method/types.py`
- Test: `tests/method/test_method_types.py`
- Test: `tests/method/test_public_api.py`

- [ ] Write failing tests for `MethodDescriptor`, `MethodContext`, `MethodPlan`, `MethodStep`, and `MethodProjection` defaults.
- [ ] Verify tests fail because `loushang.method` does not exist.
- [ ] Implement frozen dataclasses in `types.py` and public exports in `__init__.py`.
- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/method/test_method_types.py tests/method/test_public_api.py -q`.
- [ ] Commit with `feat: add method p1 core types`.

### Task 2: Skill Adapter

**Files:**
- Create: `src/loushang/method/skill_adapter.py`
- Test: `tests/method/test_skill_adapter.py`

- [ ] Write failing tests for `method_from_skill(...)`, including id normalization, metadata preservation, and taxonomy hint extraction from frontmatter.
- [ ] Verify tests fail because `skill_adapter.py` does not exist.
- [ ] Implement `method_from_skill(skill: SkillDescriptor) -> MethodDescriptor`.
- [ ] Keep direct `SkillDescriptor` field access confined to `skill_adapter.py`.
- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/method/test_skill_adapter.py tests/method/test_method_types.py -q`.
- [ ] Commit with `feat: adapt skills to methods`.

### Task 3: Method Loader

**Files:**
- Create: `src/loushang/method/loader.py`
- Test: `tests/method/test_method_loader.py`

- [ ] Write failing tests for `discover_methods(...)`, `reload_methods(...)`, `list_methods()`, and `get_method(...)`.
- [ ] Cover `skills/**/SKILL.md` discovery through `DefaultResourceLoader`.
- [ ] Cover `methods/**/SKILL.md` discovery, `element_type` hints from frontmatter or path, and discovery-time de-duplication.
- [ ] Verify tests fail because `MethodLoader` does not exist.
- [ ] Implement loader cache semantics: `discover_methods` is stateless, `reload_methods` replaces snapshot, `list_methods` and `get_method` read snapshot.
- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/method/test_method_loader.py tests/method/test_skill_adapter.py -q`.
- [ ] Commit with `feat: discover method resources`.

### Task 4: Registry And Selector

**Files:**
- Create: `src/loushang/method/registry.py`
- Create: `src/loushang/method/selector.py`
- Test: `tests/method/test_method_registry.py`
- Test: `tests/method/test_method_selector.py`

- [ ] Write failing tests for registry list/get selected-state behavior and duplicate id rejection.
- [ ] Write failing tests for exact id/name selector behavior.
- [ ] Implement `MethodRegistry` and `MethodSelector`.
- [ ] Run focused registry/selector tests.
- [ ] Commit with `feat: add method registry and selector`.

### Task 5: Compiler And Projection

**Files:**
- Create: `src/loushang/method/compiler.py`
- Create: `src/loushang/method/projection.py`
- Test: `tests/method/test_method_compiler.py`
- Test: `tests/method/test_method_projection.py`

- [ ] Write failing tests for single-turn compilation.
- [ ] Write failing tests for deterministic projection guidance and optional role/temperature hint carrying.
- [ ] Implement `MethodCompiler` and `MethodProjector`.
- [ ] Run focused compiler/projection tests.
- [ ] Commit with `feat: compile and project method guidance`.

### Task 6: Optional Work Metadata Integration

**Files:**
- Modify: `src/loushang/work/coding.py`
- Test: `tests/work/test_coding_work_shell.py`

- [ ] Check current `WorkRun.method_id` usage and write a failing test for `CodingWorkShell.submit_coding_turn(..., method_id=...)`.
- [ ] Implement metadata-only parameter plumbing.
- [ ] Verify no prompt, method selection, or `AgentSession` behavior changes.
- [ ] Run focused work tests.
- [ ] Commit with `feat: record method id on coding work runs`.

### Task 7: Regression

**Files:**
- Modify as needed: public exports and tests only.

- [ ] Run `uv --cache-dir .uv-cache run --extra dev pytest tests/method tests/coding/test_skill_loader.py tests/coding/test_cli.py tests/work -q`.
- [ ] Run `uv --cache-dir .uv-cache run ruff check src/loushang/method tests/method`.
- [ ] Fix issues without broadening P1 scope.
- [ ] Commit any final fixes.
