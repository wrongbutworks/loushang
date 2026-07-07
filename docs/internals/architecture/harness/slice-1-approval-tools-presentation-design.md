# Harness Slice 1 Design: Approval, Tools Core, Presentation

## Status

Draft for `lane/harness`.

This design starts Slice 1 of the harness migration. It is a boundary design,
not an implementation plan. Source changes should wait until this design is
accepted and an implementation plan is written.

## Goal

Extract product-neutral approval, tool-core, and presentation mechanisms from
`loushang.coding` into `loushang.harness` without changing coding behavior.

Slice 1 validates the OEM and extension contribution model while avoiding the
agent loop, AI provider/model/auth layer, TUI render loop, command/slash
semantics, prompt templates, coding session store, and work/method/channel
implementations.

## Design Rule

Slice 1 is a split, not a file move.

Current `loushang.coding` modules often mix reusable mechanism with coding
policy, Pi-compatible protocol projection, AI content conversion, concrete tool
behavior, or UI/session integration. Only the product-neutral contract or
mechanism may move into harness. Coding-owned behavior remains in coding
adapters and compatibility modules.

Harness may depend on stable `loushang.agent` primitives. Harness must not
import `loushang.coding`, `loushang.tui`, `loushang.work`, `loushang.method`,
or `loushang.ai`.

Do not add Slice 1 types to top-level `loushang.harness.__all__`. Consumers
should import from focused modules.

## Target Modules

Slice 1 introduces or fills these focused modules:

- `loushang.harness.approval`
- `loushang.harness.tools.core`
- `loushang.harness.presentation`

No new top-level packages such as `loushang.workspace`, `loushang.context`,
`loushang.memory`, `loushang.session`, `loushang.product`, or
`loushang.runtime` are introduced.

## Approval Boundary

### Harness Owns

`loushang.harness.approval` owns neutral approval contracts and headless
resolver mechanics:

- `ApprovalRequest`
- `ApprovalDecision`
- `ApprovalResolver`
- `DenyApprovalResolver`
- `HeadlessApprovalResolver`
- `resolve_approval`
- a local `MaybeAwaitable` helper if needed

`ApprovalRequest` may carry product policy context only as opaque metadata.
For example, a current `policy_decision` field must become `object | None` or
a neutral metadata mapping. Harness must not import
`loushang.coding.policy.types.PolicyDecision`.

### Coding Keeps

`loushang.coding.policy` keeps coding policy and UI integration:

- `PolicyDecision`
- `PolicyEngine`
- destructive command/path heuristics
- `enforce_tool_policy`
- approval audit payload shape
- `PolicyEnforcementError`
- `InteractiveApprovalResolver`
- persisted or UI-specific approval behavior

`InteractiveApprovalResolver` stays coding-owned in Slice 1 because the current
implementation owns pending futures, presenter payload shape, and product UI
behavior. A later slice may define a neutral approval broker if it can be
expressed without importing UI callbacks or product payload semantics.

## Tools Core Boundary

### Harness Owns

`loushang.harness.tools.core` owns neutral tool definition, contribution, schema,
registry, and agent-adaptation mechanics:

- `ToolDefinition`
- `ToolRenderCall`
- `ToolRenderResult`
- `ToolRenderOutput`
- schema helpers such as `apply_schema_overrides`,
  `infer_schema_from_signature`, and `infer_schema_from_type`
- `DecoratedToolSpec`
- `DecoratedTool`
- `tool` decorator metadata
- neutral registry records and enable/disable/list mechanics
- adaptation from `ToolDefinition` to stable `loushang.agent` `AgentTool`
  primitives

`ToolDefinition.prompt_snippet` and `ToolDefinition.prompt_guidelines` are
opaque product-consumed metadata. Harness may store and preserve them, but must
not assemble prompts, validate prompt semantics, order prompt sections, or
render prompt guidance.

Render callback types may use stable `loushang.agent` result primitives, but
harness must not import AI content-part types directly.

### Coding Keeps

`loushang.coding.tools` keeps concrete tools and coding adapters:

- `read`, `ls`, `find`, `grep`, `write`, `edit`, and `bash`
- `factory.py`
- `builtins.py`
- default tool packs and activation order
- product-specific tool names and descriptions
- `ToolsOptions`
- concrete operation protocols for coding tools
- external tool download/installation policy
- Pi-style aliases and public coding SDK surface

`normalize.py` is split rather than moved. The current decorated-tool
normalization converts plain return values into AI text parts, so that portion
stays in coding. Harness may own decorator metadata and schema inference, but
plain return value to model content conversion remains a product adapter
concern unless a later neutral result adapter is designed.

Context binding is also split. Current `ToolContext` carries coding diagnostics
and product runtime fields. Harness may own registry and agent-tool adaptation,
but coding keeps `ToolContext`, `ToolContextProvider`, and context injection
unless the implementation introduces an opaque binder protocol with no coding
dependencies.

Provider schema projection is coding-owned in Slice 1. Harness may store a
secondary parameter schema as opaque metadata if needed for compatibility, but
the current behavior where runtime agent tools expose
`provider_parameters or parameters` stays in the coding wrapper until a neutral
provider-adaptation contract exists.

## Presentation Boundary

### Harness Owns

`loushang.harness.presentation` owns neutral presentation records and renderer
mechanics:

- `ToolResultPresentation`
- ANSI stripping
- line-ending normalization
- generic text/image-like output extraction by duck typing
- generic line collapse helpers
- `ToolRenderContext`
- `ToolRenderResultOptions`
- `ToolDefinitionResolver`
- `ToolRenderRuntime` state, last-rendered, and invalidation mechanics

Harness presentation records should be neutral. They may describe text,
structured values, file references, or opaque artifact references, but they do
not decide terminal/web widgets or product transcript layout.

### Coding Keeps

`loushang.coding.tools.presentation` and related modules keep coding-specific
projection and wording:

- `coding.tools.protocol` Pi-compatible detail projection
- artifact-path key conventions such as `fullOutputPath`
- `[Full output: ...]` labels
- truncation notice wording and size formatting policy
- `output_preview`
- `builtin_renderers`
- coding-specific collapsed preview limits
- command/path-oriented renderer text

The current builtin renderers know concrete coding tool names and argument
semantics, so they remain coding-owned.

Render callback aliases (`ToolRenderCall`, `ToolRenderResult`, and
`ToolRenderOutput`) are tools-core contracts because they are fields on
`ToolDefinition`. They may reference presentation-owned context and options
types, but presentation runtime should avoid importing tools core at runtime by
using a small local protocol or type-checking-only imports.

## Compatibility Strategy

Slice 1 requires compatibility shims.

Existing public and internal imports from `loushang.coding` and
`loushang.coding.tools` must continue to work. Compatibility modules may
re-export or adapt harness-owned contracts while preserving current coding
behavior.

Required compatibility paths include:

- `loushang.coding.policy.approval`
- `loushang.coding.tools.types`
- `loushang.coding.tools.schema`
- `loushang.coding.tools.authoring`
- `loushang.coding.tools.wrapper`
- `loushang.coding.tools.registry`
- `loushang.coding.tools.rendering`
- `loushang.coding.tools.presentation`

Compatibility shims are temporary for internal imports but remain until the
public SDK surface decision is explicit. They can be deleted only when:

- in-repo imports have migrated to focused harness modules where appropriate;
- docs state that the old submodule path is not a supported SDK contract, or a
  replacement deprecation policy is accepted;
- focused compatibility tests are updated;
- downstream product, OEM, or extension users are not expected to import the old
  path.

Top-level `loushang.coding` and `loushang.coding.tools` exports remain stable
through Slice 1.

## External Reference: Hermes Agent

`~/workspace/hermes-agent` is useful as a boundary validation sample, not as a
template to copy.

Its tool registry demonstrates a contribution-record shape that is relevant to
`harness.tools.core`: tool name, schema, handler, toolset membership,
availability metadata, dynamic schema override hooks, registry snapshots, and a
generation counter. Slice 1 may borrow those mechanism concepts, but not the
Hermes implementation style. Hermes uses import-time singleton registration,
OpenAI-format tool definitions, plugin override policy, availability probing,
and JSON-string dispatch; those are product/runtime choices and remain outside
harness.

Hermes toolsets also validate that pack/include resolution is a shared
mechanism, while defaults remain product-owned. Harness may define neutral
tool-pack contribution and include resolution in or near `harness.tools.core`.
Coding still decides the default tool set, activation order, disabled platform
bundles, aliases, and user-facing names.

Hermes approval code reinforces that approval must be split instead of moved.
Its approval layer includes dangerous-command detection, YOLO/config handling,
context variables, gateway and CLI session behavior, plugin hooks, pending
queues, and smart approval through an auxiliary model. Those are adapter and
product policy concerns. Harness should keep only neutral request, decision,
resolver, and fail-closed mechanics. Product adapters map local approval
choices onto transport-specific wire decisions.

Hermes' rendering bridge is a useful presentation precedent: renderers are
optional and fail soft, allowing the UI surface to fall back when a Python-side
renderer is absent or fails. `harness.presentation` should follow that shape by
owning neutral records and renderer contracts while leaving terminal, TUI, web,
and transcript fallback behavior to product adapters.

Hermes' ANSI stripping helper is a good candidate reference for robust generic
text normalization. By contrast, Hermes schema sanitization for LLM backends,
tool output limits, write-approval pending stores, and terminal callback
plumbing are provider, store, runtime, or UI policies and should not enter
Slice 1 harness modules.

## Migration Sequence

### Step 1: Approval Split

Create `loushang.harness.approval` with neutral approval request/decision and
headless resolver contracts.

Update `loushang.coding.policy.approval` to use or re-export harness contracts
while retaining `PolicyEnforcementError` and `InteractiveApprovalResolver` in
coding.

Focused tests:

- `tests/coding/test_tool_policy_integration.py`
- `tests/coding/test_policy_engine.py`
- new harness approval tests
- `tests/architecture/test_import_boundaries.py`

### Step 2: Presentation Split

Create `loushang.harness.presentation` for neutral presentation records,
normalization helpers, and render runtime mechanics.

Keep coding protocol projection, artifact labels, truncation wording, and
builtin renderers in coding.

Focused tests:

- `tests/coding/test_tool_presentation.py`
- `tests/coding/test_tool_render_runtime.py`
- `tests/coding/test_tool_builtin_renderers.py`
- `tests/coding/test_tool_transcript_blocks.py`
- relevant session event and export rendering tests
- new harness presentation tests
- `tests/architecture/test_import_boundaries.py`

### Step 3: Tools Core Split

Create `loushang.harness.tools.core` for neutral tool definition, schema,
decorator metadata, registry mechanics, and agent-tool adaptation.

Keep decorated plain-return normalization, coding `ToolContext`, concrete tools,
tool factories, default tool packs, and public Pi-style aliases in coding.

Focused tests:

- `tests/coding/test_tool_schema.py`
- `tests/coding/test_tool_wrapper.py`
- `tests/coding/test_tool_authoring.py`
- `tests/coding/test_tool_registry.py`
- `tests/coding/test_tool_public_types.py`
- `tests/coding/test_prompt_assembly.py`
- extension tests that import `ToolDefinition`
- new harness tools-core tests
- `tests/architecture/test_import_boundaries.py`

### Step 4: Coding Compatibility Adapters

Preserve existing coding imports and behavior through thin shims or adapters.
Avoid a broad internal import rewrite until the harness owner modules are
tested and stable.

Focused tests:

- command catalog and command controller tests
- tool policy integration tests
- screen/surface focused tests for changed render paths
- SDK/public type tests

## Behavior Preservation

Coding behavior must remain unchanged:

- same default tool set and activation order;
- same concrete tool descriptions and argument schemas;
- same policy allow/deny/ask decisions;
- same approval audit details;
- same terminal/plain transcript rendering text;
- same command catalog and slash command behavior;
- same public imports from `loushang.coding` and `loushang.coding.tools`.

If a harness extraction requires changing any of those behaviors, it is out of
scope for Slice 1 unless separately accepted.

## Validation Matrix

Required validation before a Slice 1 implementation is considered ready:

- `uv run pytest tests/architecture/test_import_boundaries.py -q`
- focused coding tool tests for schema, wrapper, authoring, registry,
  presentation, render runtime, builtin renderers, and policy integration
- focused command catalog and session command controller tests
- focused screen/surface tests when render paths are touched
- harness-focused tests for each new owner module
- `uv run ruff check <changed files>`
- `git diff --check`

The architecture import-boundary test must show no harness import of
`loushang.coding`, `loushang.tui`, `loushang.work`, `loushang.method`, or
`loushang.ai`.

## Open Decisions

- Whether a later slice should introduce a neutral approval broker to replace
  the coding-owned interactive resolver.
- Whether prompt-related fields on `ToolDefinition` should remain named fields
  or move into a generic metadata mapping before non-coding products adopt the
  contract.
