# Harness Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract product-neutral approval, presentation, and tools-core contracts into focused `loushang.harness` modules while preserving all existing `loushang.coding` behavior and imports.

**Architecture:** Add harness owner modules first, then turn coding modules into behavior-preserving adapters or re-export shims. Harness modules may import stable `loushang.agent.types` primitives, but must not import `loushang.coding`, `loushang.tui`, `loushang.work`, `loushang.method`, or `loushang.ai`. Coding remains responsible for policy, concrete tools, prompt semantics, UI behavior, context binding, concrete renderers, and public Pi-style aliases.

**Tech Stack:** Python 3.11+, pytest, ruff, dataclasses, Protocols, existing `src/` layout.

---

## References

- Design: `docs/internals/architecture/harness/slice-1-approval-tools-presentation-design.md`
- Boundary docs: `docs/internals/architecture/harness/README.md`
- Boundary tests: `tests/architecture/test_import_boundaries.py`

## File Structure

- Create `src/loushang/harness/approval.py`: neutral approval dataclasses, resolver protocol, headless/fail-closed helpers.
- Create `src/loushang/harness/presentation.py`: neutral presentation records, render context/options, render runtime, ANSI/text normalization helpers.
- Create `src/loushang/harness/tools/__init__.py`: package marker only; do not expose Slice 1 symbols from top-level `loushang.harness`.
- Create `src/loushang/harness/tools/core.py`: neutral `ToolDefinition`, render callback aliases, schema inference, authoring decorator metadata, registry records, agent-tool adaptation with no coding context binding.
- Create `tests/harness/test_approval.py`.
- Create `tests/harness/test_presentation.py`.
- Create `tests/harness/tools/test_core.py`.
- Modify `src/loushang/coding/policy/approval.py`: keep coding-owned `PolicyEnforcementError` and `InteractiveApprovalResolver`; import/re-export neutral approval contracts from harness.
- Modify `src/loushang/coding/tools/types.py`: keep `PiTruncationDetails`; import/re-export neutral render and tool types from harness.
- Modify `src/loushang/coding/tools/schema.py`: compatibility shim over harness schema helpers.
- Modify `src/loushang/coding/tools/authoring.py`: compatibility shim over harness authoring metadata.
- Modify `src/loushang/coding/tools/presentation.py`: delegate neutral helpers to harness; keep protocol projection, artifact labels, truncation wording.
- Modify `src/loushang/coding/tools/rendering.py`: compatibility shim over harness render runtime if the runtime can be moved without changing behavior.
- Modify `src/loushang/coding/tools/registry.py`: use harness registry mechanics where possible; keep decorated-tool normalization and coding context materialization in coding.
- Modify `src/loushang/coding/tools/wrapper.py`: keep `ToolContextProvider` binding and abort behavior in coding; optionally use harness agent-tool adaptation after those product hooks are applied.

Do not modify `src/loushang/harness/__init__.py` to export Slice 1 symbols.

## Task 0: Baseline and Guardrails

**Files:**
- Read: `src/loushang/harness/__init__.py`
- Read: `tests/architecture/test_import_boundaries.py`
- Read: `docs/internals/architecture/harness/slice-1-approval-tools-presentation-design.md`

- [ ] **Step 1: Confirm lane and dirty state**

Run:

```bash
git status --short
git branch --show-current
```

Expected: branch is `lane/harness` or a `harness/<slice>` task branch based on `lane/harness`. Preserve unrelated user changes.

- [ ] **Step 2: Run import-boundary baseline**

Run:

```bash
uv run pytest tests/architecture/test_import_boundaries.py -q
```

Expected: PASS before source changes.

- [ ] **Step 3: Run current focused coding baseline**

Run:

```bash
uv run pytest \
  tests/coding/test_policy_engine.py \
  tests/coding/test_tool_policy_integration.py \
  tests/coding/test_tool_presentation.py \
  tests/coding/test_tool_render_runtime.py \
  tests/coding/test_tool_schema.py \
  tests/coding/test_tool_authoring.py \
  tests/coding/test_tool_wrapper.py \
  tests/coding/test_tool_registry.py \
  tests/coding/test_tool_public_types.py \
  tests/coding/test_tool_runtime.py \
  tests/coding/test_tool_pi_golden_behavior.py \
  -q
```

Expected: PASS. If any test already fails, record it before changing code.

## Task 1: Approval Neutral Module

**Files:**
- Create: `src/loushang/harness/approval.py`
- Create: `tests/harness/test_approval.py`
- Modify: `src/loushang/coding/policy/approval.py`
- Test: `tests/coding/test_policy_engine.py`
- Test: `tests/coding/test_tool_policy_integration.py`
- Test: `tests/architecture/test_import_boundaries.py`

- [ ] **Step 1: Write failing harness approval tests**

Add tests for neutral contracts:

```python
async def test_resolve_approval_defaults_to_deny() -> None:
    from loushang.harness.approval import ApprovalRequest, resolve_approval

    decision = await resolve_approval(
        None,
        ApprovalRequest(tool_name="write", arguments={"path": "x"}, reason="needs approval"),
    )

    assert decision.disposition == "deny"
    assert decision.reason == "needs approval"
```

Also test:

- `ApprovalDecision.allow()` and `.deny("reason")`.
- `HeadlessApprovalResolver(mode="allow")`.
- invalid headless mode raises `ValueError`.
- `ApprovalRequest(policy_decision=object())` accepts opaque policy context without importing coding.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
uv run pytest tests/harness/test_approval.py -q
```

Expected: FAIL because `loushang.harness.approval` does not exist.

- [ ] **Step 3: Implement minimal harness approval module**

Move or copy neutral definitions from `src/loushang/coding/policy/approval.py` into `src/loushang/harness/approval.py`:

- `MaybeAwaitable`
- `ApprovalRequest`
- `ApprovalDecision`
- `ApprovalResolver`
- `DenyApprovalResolver`
- `HeadlessApprovalResolver`
- `resolve_approval`

Set `ApprovalRequest.policy_decision` to `object | None`, not `PolicyDecision | None`.

- [ ] **Step 4: Update coding approval adapter**

In `src/loushang/coding/policy/approval.py`:

- import neutral approval contracts from `loushang.harness.approval`;
- keep `PolicyEnforcementError` in coding;
- keep `InteractiveApprovalResolver` in coding;
- keep its payload shape and pending future behavior unchanged;
- remove the direct `PolicyDecision` import unless still needed for local coding-only code.

- [ ] **Step 5: Run approval tests**

Run:

```bash
uv run pytest \
  tests/harness/test_approval.py \
  tests/coding/test_policy_engine.py \
  tests/coding/test_tool_policy_integration.py \
  tests/architecture/test_import_boundaries.py \
  -q
```

Expected: PASS. Coding audit payloads and approval denial details must be byte-for-byte unchanged except generated action IDs.

- [ ] **Step 6: Ruff changed files**

Run:

```bash
uv run ruff check src/loushang/harness/approval.py src/loushang/coding/policy/approval.py tests/harness/test_approval.py
```

Expected: PASS.

## Task 2: Presentation Neutral Module

**Files:**
- Create: `src/loushang/harness/presentation.py`
- Create: `tests/harness/test_presentation.py`
- Modify: `src/loushang/coding/tools/types.py`
- Modify: `src/loushang/coding/tools/presentation.py`
- Modify: `src/loushang/coding/tools/rendering.py`
- Test: `tests/coding/test_tool_presentation.py`
- Test: `tests/coding/test_tool_render_runtime.py`
- Test: `tests/coding/test_tool_builtin_renderers.py`
- Test: `tests/coding/test_tool_transcript_blocks.py`
- Test: `tests/architecture/test_import_boundaries.py`

- [ ] **Step 1: Write failing harness presentation tests**

Add tests for neutral helpers and runtime:

```python
def test_normalize_display_text_strips_full_ansi_and_line_endings() -> None:
    from loushang.harness.presentation import normalize_display_text

    assert normalize_display_text("a\r\n\x1b[31mred\x1b[0m") == "a\nred"
```

Also test:

- `collapse_text("a\nb\nc", max_lines=2)` returns `("a\nb\n... (1 more lines)", 1)`.
- `collapse_text(..., max_lines=0)` raises `ValueError`.
- `ToolRenderRuntime.render_event()` returns `None` for unknown event types and missing renderers.
- render context preserves `tool_call_id`, `state`, `last_rendered`, `expanded`, `is_partial`, and `show_images`.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
uv run pytest tests/harness/test_presentation.py -q
```

Expected: FAIL because `loushang.harness.presentation` does not exist.

- [ ] **Step 3: Implement neutral presentation module**

Move neutral pieces into `src/loushang/harness/presentation.py`:

- `ToolResultPresentation`
- `ToolRenderResultOptions`
- `ToolRenderContext`
- `ToolDefinitionResolver` or a local `RenderableToolDefinition` protocol
- `ToolRenderRuntime`
- `normalize_display_text`
- `normalize_line_endings`
- `strip_ansi`
- `collapse_text`

Use a robust ANSI regex that covers CSI, OSC, DCS/SOS/PM/APC, and C1 controls. Keep the implementation local and dependency-free.

- [ ] **Step 4: Update coding presentation adapter**

In `src/loushang/coding/tools/presentation.py`:

- import neutral `ToolResultPresentation`, `normalize_display_text`, and `collapse_text`;
- keep `_tool_result_notices`, `_artifact_paths`, `render_tool_result_presentation`, and `render_tool_result_text` in coding;
- preserve `[Full output: ...]`, truncation wording, and image fallback output exactly.

- [ ] **Step 5: Update render-runtime compatibility**

In `src/loushang/coding/tools/rendering.py`, re-export or subclass the harness `ToolRenderRuntime`.

Stop condition: if a neutral `ToolRenderRuntime` cannot move into harness while preserving existing tests, stop the implementation and revise the accepted design/plan before Task 3. Do not proceed with `ToolRenderRuntime` still owned only by coding.

- [ ] **Step 6: Update type compatibility**

In `src/loushang/coding/tools/types.py`:

- import/re-export presentation context/options/runtime-facing types from `loushang.harness.presentation`;
- keep `PiTruncationDetails` in coding;
- do not import `loushang.harness` top-level.

- [ ] **Step 7: Run presentation tests**

Run:

```bash
uv run pytest \
  tests/harness/test_presentation.py \
  tests/coding/test_tool_presentation.py \
  tests/coding/test_tool_render_runtime.py \
  tests/coding/test_tool_builtin_renderers.py \
  tests/coding/test_tool_transcript_blocks.py \
  tests/architecture/test_import_boundaries.py \
  -q
```

Expected: PASS. Existing coding text output, truncation notices, artifact labels, and render runtime state behavior remain unchanged.

- [ ] **Step 8: Ruff changed files**

Run:

```bash
uv run ruff check \
  src/loushang/harness/presentation.py \
  src/loushang/coding/tools/types.py \
  src/loushang/coding/tools/presentation.py \
  src/loushang/coding/tools/rendering.py \
  tests/harness/test_presentation.py
```

Expected: PASS.

## Task 3: Tools Core Foundation

**Files:**
- Create: `src/loushang/harness/tools/__init__.py`
- Create: `src/loushang/harness/tools/core.py`
- Create: `tests/harness/tools/test_core.py`
- Modify: `src/loushang/coding/tools/types.py`
- Modify: `src/loushang/coding/tools/schema.py`
- Modify: `src/loushang/coding/tools/authoring.py`
- Modify: `src/loushang/coding/tools/wrapper.py`
- Modify: `src/loushang/coding/tools/registry.py`
- Test: `tests/coding/test_tool_schema.py`
- Test: `tests/coding/test_tool_authoring.py`
- Test: `tests/coding/test_tool_wrapper.py`
- Test: `tests/coding/test_tool_registry.py`
- Test: `tests/coding/test_tool_public_types.py`
- Test: `tests/coding/test_tool_runtime.py`
- Test: `tests/coding/test_tool_pi_golden_behavior.py`
- Test: `tests/coding/test_prompt_assembly.py`
- Test: `tests/architecture/test_import_boundaries.py`

- [ ] **Step 1: Write failing harness tools-core tests**

Add tests for neutral tool definitions, schema inference, decorators, registry order, enable/disable, and agent-tool adaptation:

```python
def test_tool_definition_validates_prompt_guidelines_sequence() -> None:
    from loushang.harness.tools.core import ToolDefinition

    async def execute(tool_call_id, params, signal=None, on_update=None):
        from loushang.agent.types import AgentToolResult

        return AgentToolResult(content=[], details={})

    definition = ToolDefinition(
        name="demo",
        label="Demo",
        description="demo",
        parameters={"type": "object", "properties": {}, "required": []},
        execute=execute,
        prompt_guidelines=["one", "two"],
    )

    assert definition.prompt_guidelines == ("one", "two")
```

Also test:

- `tool()` decorator attaches `DecoratedToolSpec`.
- `infer_schema_from_signature()` handles `TypedDict`, dataclass, optional fields.
- `ToolRegistry.register_tool()` preserves order and source info.
- harness `ToolRegistry.register_tool()` accepts pre-normalized `ToolDefinition` and `AgentTool`-like objects only.
- harness `ToolRegistry.register_tool()` rejects decorated plain-return functions rather than importing coding normalization.
- `ToolRegistry.enable_tool()` and `.disable_tool()` affect only enabled listing.
- `wrap_tool_definition()` returns an `AgentTool`-like object without coding context binding, abort checks, or provider schema projection.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
uv run pytest tests/harness/tools/test_core.py -q
```

Expected: FAIL because `loushang.harness.tools.core` does not exist.

- [ ] **Step 3: Implement harness tools package and core module**

Create `src/loushang/harness/tools/__init__.py` with no broad exports.

In `src/loushang/harness/tools/core.py`, move neutral pieces:

- `ToolDefinition`
- `ToolRenderOutput`
- `ToolRenderCall`
- `ToolRenderResult`
- schema helpers from `coding.tools.schema`
- `DecoratedToolSpec`, `DecoratedTool`, and `tool`
- neutral `WrappedToolDefinition`
- `wrap_tool_definition()` with no coding context provider and no coding abort hook
- `create_tool_definition_from_tool()`
- `ToolRegistry` and registered record mechanics

`ToolRegistry.register_tool()` in harness should accept only already-neutral
definitions and agent-tool-like objects. It must not import
`loushang.coding.tools.normalize` and must not convert plain Python return
values into model content.

Imports allowed from `loushang.agent.types`:

- `AgentTool`
- `AgentToolResult`
- `ToolExecutionMode`
- `ensure_agent_tool`
- `is_agent_tool_like`

Do not import `loushang.coding.tools.normalize` in harness. Decorated
plain-return normalization remains coding-owned because it currently converts
return values through AI content part types.

- [ ] **Step 4: Update coding schema and authoring shims**

Replace implementations in:

- `src/loushang/coding/tools/schema.py`
- `src/loushang/coding/tools/authoring.py`

with imports/re-exports from `loushang.harness.tools.core`, preserving current names and exceptions.

- [ ] **Step 5: Update coding types shim**

In `src/loushang/coding/tools/types.py`:

- import `ToolDefinition` from `loushang.harness.tools.core`;
- import `ToolRenderOutput`, `ToolRenderCall`, and `ToolRenderResult` from `loushang.harness.tools.core`;
- import `ToolRenderContext` and `ToolRenderResultOptions` from `loushang.harness.presentation`;
- keep `PiTruncationDetails` and any coding-only aliases locally.

- [ ] **Step 6: Update coding wrapper without losing context behavior**

In `src/loushang/coding/tools/wrapper.py`:

- keep `ToolContextProvider` import from `.context`;
- keep `raise_if_tool_aborted(signal)`;
- continue to call `bind_context_provider(context_provider)` when present;
- preserve current provider schema projection where `parameters` returns `provider_parameters or parameters`;
- adapt the final `ToolDefinition` to `AgentTool` using harness core or the existing local wrapper shape.

Behavior required: `tests/coding/test_tool_registry.py::test_tool_factory_create_tool_binds_cwd_context` still passes.

- [ ] **Step 7: Update coding registry without moving normalization**

In `src/loushang/coding/tools/registry.py`:

- reuse harness registry record mechanics if straightforward;
- keep `tool_to_definition()` from `coding.tools.normalize` for decorated tools;
- keep `ToolContextProvider` materialization in coding;
- keep decorated plain-return normalization in coding before registration or materialization;
- keep source info behavior and ordering unchanged.

- [ ] **Step 8: Run tools-core tests**

Run:

```bash
uv run pytest \
  tests/harness/tools/test_core.py \
  tests/coding/test_tool_schema.py \
  tests/coding/test_tool_authoring.py \
  tests/coding/test_tool_wrapper.py \
  tests/coding/test_tool_registry.py \
  tests/coding/test_tool_public_types.py \
  tests/coding/test_tool_runtime.py \
  tests/coding/test_tool_pi_golden_behavior.py \
  tests/coding/test_prompt_assembly.py \
  tests/architecture/test_import_boundaries.py \
  -q
```

Expected: PASS. Tool schemas, public aliases, registry ordering, context binding, and prompt assembly remain unchanged.

- [ ] **Step 9: Ruff changed files**

Run:

```bash
uv run ruff check \
  src/loushang/harness/tools/__init__.py \
  src/loushang/harness/tools/core.py \
  src/loushang/coding/tools/types.py \
  src/loushang/coding/tools/schema.py \
  src/loushang/coding/tools/authoring.py \
  src/loushang/coding/tools/wrapper.py \
  src/loushang/coding/tools/registry.py \
  tests/harness/tools/test_core.py
```

Expected: PASS.

## Task 4: Compatibility and Public Surface Audit

**Files:**
- Modify only if needed: `src/loushang/coding/tools/__init__.py`
- Modify only if needed: `src/loushang/coding/policy/__init__.py`
- Do not modify exports: `src/loushang/harness/__init__.py`
- Test: `tests/coding/test_tool_public_types.py`
- Test: `tests/coding/test_commands.py`
- Test: `tests/coding/test_session_command_controller.py`
- Test: screen/surface focused tests listed below

- [ ] **Step 1: Add or update compatibility tests only when a public path is not already covered**

Check that these imports still work:

```python
from loushang.coding.policy import ApprovalDecision, ApprovalRequest
from loushang.coding.tools import ToolDefinition, ToolRegistry, tool
from loushang.coding.tools.schema import infer_schema_from_signature
from loushang.coding.tools.rendering import ToolRenderRuntime
```

Prefer updating `tests/coding/test_tool_public_types.py` over adding broad snapshot tests.

- [ ] **Step 2: Run command and surface focused tests**

Run:

```bash
uv run pytest \
  tests/coding/test_commands.py \
  tests/coding/test_session_command_controller.py \
  tests/coding/test_screen_coding_tui_surfaces.py \
  tests/coding/test_screen_coding_tui_events.py \
  tests/coding/test_session_exports.py \
  -q
```

Expected: PASS. Command catalog, slash command behavior, exported transcript text, and screen/surface behavior remain unchanged.

- [ ] **Step 3: Confirm top-level harness exports are unchanged**

Run:

```bash
git diff -- src/loushang/harness/__init__.py
```

Expected: no diff.

## Task 5: Final Validation

**Files:**
- All changed source and test files.

- [ ] **Step 1: Run architecture boundary test**

Run:

```bash
uv run pytest tests/architecture/test_import_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 2: Run focused Slice 1 suite**

Run:

```bash
uv run pytest \
  tests/harness/test_approval.py \
  tests/harness/test_presentation.py \
  tests/harness/tools/test_core.py \
  tests/coding/test_policy_engine.py \
  tests/coding/test_tool_policy_integration.py \
  tests/coding/test_tool_schema.py \
  tests/coding/test_tool_authoring.py \
  tests/coding/test_tool_wrapper.py \
  tests/coding/test_tool_registry.py \
  tests/coding/test_tool_public_types.py \
  tests/coding/test_tool_runtime.py \
  tests/coding/test_tool_pi_golden_behavior.py \
  tests/coding/test_tool_presentation.py \
  tests/coding/test_tool_render_runtime.py \
  tests/coding/test_tool_builtin_renderers.py \
  tests/coding/test_tool_transcript_blocks.py \
  tests/coding/test_prompt_assembly.py \
  tests/coding/test_commands.py \
  tests/coding/test_session_command_controller.py \
  tests/coding/test_screen_coding_tui_surfaces.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Ruff changed files**

Run:

```bash
uv run ruff check $(git diff --name-only -- '*.py')
```

Expected: PASS. If the command expands to no Python files because only docs changed, skip this step and record that no Python files changed.

- [ ] **Step 4: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Review import graph manually**

Run:

```bash
rg -n "loushang\\.(coding|tui|work|method|ai)" src/loushang/harness
```

Expected: no matches.

## Rollback Boundaries

- Approval rollback: restore `src/loushang/coding/policy/approval.py` to own all approval classes; remove `src/loushang/harness/approval.py` and `tests/harness/test_approval.py`.
- Presentation rollback: restore coding `types.py`, `presentation.py`, and `rendering.py` ownership; remove harness presentation tests/module.
- Tools-core rollback: restore coding `types.py`, `schema.py`, `authoring.py`, `wrapper.py`, and `registry.py` ownership; remove `src/loushang/harness/tools`.

Each task should pass its focused tests before proceeding to the next task. Do not continue after a behavior change unless the design is updated and accepted.
