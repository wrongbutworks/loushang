# Runtime Tool Contribution Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route coding runtime tool registration through neutral harness contribution projection and resolver verification without changing active-tool, prompt, execution, or duplicate-name behavior.

**Architecture:** `ToolController.register_runtime_tool` remains the coding-owned mutation point. Coding projects the runtime tool into a neutral `ToolContribution`, calls the harness resolver with current registry contributions plus the runtime contribution, then applies existing coding policy by registering the runtime definition and rebuilding/activating tools exactly as before.

**Tech Stack:** Python 3.11, pytest, Ruff, `loushang.harness.tools.contribution`, `loushang.coding.session.ToolController`.

---

### Task 1: Prove runtime registration calls the harness resolver

**Files:**
- Modify: `tests/coding/test_session_tool_controller.py`
- Modify: `src/loushang/coding/session/tool_controller.py`

- [x] **Step 1: Write the failing test**

Add a test that monkeypatches `loushang.coding.session.tool_controller.resolve_tool_contributions`, registers a runtime `ToolDefinition`, and asserts the resolver receives existing registry contributions plus a new runtime contribution with opaque metadata and source info.

- [x] **Step 2: Run test to verify it fails**

Run: `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_session_tool_controller.py::test_tool_controller_routes_runtime_registration_through_contribution_resolver -q`

Expected: FAIL because `tool_controller` does not expose/call `resolve_tool_contributions` for runtime registration yet.

- [x] **Step 3: Write minimal implementation**

In `ToolController.register_runtime_tool`, normalize the runtime tool into a `ToolDefinition`, build a `ToolContribution` with `metadata={"kind": "runtime_tool", "runtime_tool": definition.name}`, and call `resolve_tool_contributions((*registry.list_contributions(), contribution), fail_on_errors=False)`. Register the selected runtime contribution from resolver output when present; fall back to the original runtime contribution when the resolver selects an existing registry contribution so duplicate-name overwrite behavior remains unchanged.

- [x] **Step 4: Run test to verify it passes**

Run: `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_session_tool_controller.py::test_tool_controller_routes_runtime_registration_through_contribution_resolver -q`

Expected: PASS.

### Task 2: Preserve duplicate-name and active-tool behavior

**Files:**
- Modify: `tests/coding/test_session_tool_controller.py`
- Modify: `src/loushang/coding/session/tool_controller.py`

- [x] **Step 1: Write focused regression tests**

Add tests proving that runtime registration still overwrites an existing tool with the same name and that `default_activate_new_tools` still activates non-builtin runtime tools after the resolver call.

- [x] **Step 2: Run tests to verify current behavior remains explicit**

Run: `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_session_tool_controller.py -q`

Expected: PASS after Task 1 implementation; if any behavior changed, fix implementation rather than weakening tests.

### Task 3: Validate boundaries and focused coding behavior

**Files:**
- Modify: `docs/superpowers/plans/2026-07-08-runtime-tool-contribution-routing.md`
- Modify: `tests/coding/test_session_tool_controller.py`
- Modify: `src/loushang/coding/session/tool_controller.py`

- [x] **Step 1: Run architecture and harness checks**

Run:
- `uv --cache-dir .uv-cache run --extra dev pytest tests/architecture/test_import_boundaries.py -q`
- `uv --cache-dir .uv-cache run --extra dev pytest tests/harness -q`

- [x] **Step 2: Run focused coding checks**

Run:
- `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_session_tool_controller.py tests/coding/test_agent_session_tools.py -q`
- `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_extension_runner.py tests/coding/test_extension_api.py tests/coding/test_bootstrap.py -k 'extension_tool or extension' -q`
- `uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_tool_registry.py -q`

- [x] **Step 3: Run lint and diff checks**

Run:
- `uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/coding/session/tool_controller.py tests/coding/test_session_tool_controller.py`
- `git diff --check`

### Task 4: Close Slice 2A documentation and architecture status

**Files:**
- Modify: `tests/architecture/test_import_boundaries.py`
- Modify: `docs/internals/architecture/harness/slice-2-execution-context-design.md`
- Modify: `docs/internals/architecture/harness/coding-to-harness-migration-inventory.md`
- Modify: `docs/internals/architecture/harness/README.md`

- [x] **Step 1: Update the architecture contract test**

Replace the transient design-draft assertion with durable Slice 2A status and
boundary phrases: runtime contribution adapter verification is complete on the
task branch, resolver diagnostics remain advisory to coding policy, and neutral
execution context remains deferred. The later neutrality evidence policy
replaces the original production-consumer prerequisite.

- [x] **Step 2: Run the architecture test to verify it fails**

Run: `uv --cache-dir .uv-cache run --extra dev pytest tests/architecture/test_import_boundaries.py::test_harness_slice2_execution_context_design_is_documented -q`

Expected: FAIL because the Slice 2 design still reports draft status and does
not record the completed 2A boundary.

- [x] **Step 3: Update Slice 2 architecture documents**

Record Slice 2A as implemented on `harness/runtime-tool-contribution-routing`,
document that runtime duplicate overwrite and activation remain coding-owned,
and mark neutral execution context as a gated Slice 2B item. Update the
migration inventory and harness README to match.

- [x] **Step 4: Run the architecture test to verify it passes**

Run: `uv --cache-dir .uv-cache run --extra dev pytest tests/architecture/test_import_boundaries.py::test_harness_slice2_execution_context_design_is_documented -q`

Expected: PASS.

- [x] **Step 5: Re-run the complete focused validation surface**

Run the Task 3 commands plus Ruff on the modified architecture test and
`git diff --check`.
