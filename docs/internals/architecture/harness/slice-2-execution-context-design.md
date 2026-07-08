# Harness Slice 2 Execution Context Design

## Status

Status: design draft for `lane/harness`.

This document defines the Slice 2 boundary design for neutral execution context
and runtime contribution registration. No runtime behavior changes are part of
this design slice. Implementation must wait for design approval and a separate
implementation plan.

## Goal

Slice 2 should define a neutral execution context shape that lets product
adapters expose live runtime capabilities to tools and extensions without
moving product runtime state into `loushang.harness`.

The immediate pressure comes from runtime dynamic extension registration:

```text
ExtensionAPI._register_runtime_tool
-> ExtensionRuntimeBindings.register_tool
-> AgentSession._register_extension_runtime_tool
-> ToolController.register_runtime_tool
```

That path currently touches coding session state, active tool activation,
source information, prompt rebuild, runtime bindings, and extension execution.
Harness can define the neutral mechanism for describing runtime contributions,
but product execution adapter code must still own product behavior.

## Non-Goals

Slice 2 does not migrate:

- concrete coding tools
- command handlers or slash semantics
- prompt templates or prompt/resource semantics
- TUI controller/render loop or screen surface state
- coding session store
- AI provider/model/auth
- agent loop or tool-call orchestration
- work/method/channel implementations
- extension provider/model/session APIs
- connector authorization or product skill semantics

## Proposed Boundary

Harness should introduce a neutral execution context boundary only if it remains
product-agnostic.

Candidate harness-owned concepts:

- neutral execution context records carrying opaque ids, cwd, cancellation
  signal, metadata, and optional event sink
- neutral contribution registration requests for tools, renderers, or later
  capability kinds
- resolver integration through `harness.tools.contribution`
- source and diagnostic passthrough as opaque values
- product callback protocols that are typed by capability, not by coding
  session concepts

Product-owned concepts:

- product execution adapter
- active tool activation policy
- prompt rebuild behavior
- session state mutation
- extension runner lifecycle
- concrete execution, file, process, and model APIs
- UI diagnostics, status, footer data, and message append behavior
- coding-specific `ToolContext` and runtime binding fields

Product-owned behavior remains product-owned. Harness must not interpret
whether a runtime contribution should become active, how prompts are rebuilt,
or how a session records diagnostics.

## Current Coding Mapping

`loushang.coding.tools.context.ToolContext` is a product context. It currently
contains:

- `tool_call_id`
- `cwd`
- diagnostics service
- signal
- model
- event sink

Only a subset is neutral. A future harness context may carry `tool_call_id`,
`cwd`, `signal`, and opaque metadata. The diagnostics service, model object,
and event payload semantics stay adapter-owned unless a separate neutral
diagnostics or model-reference contract is accepted.

`ExtensionRuntimeBindings.register_tool` is a product runtime callback. It
currently accepts a tool object and source info, then delegates into the live
session. Harness should not own this callback directly. Instead, coding can
adapt the callback into a neutral contribution registration request and then
apply product policy to resolver output.

`ToolController.register_runtime_tool` is coding-owned because it mutates live
registry state, checks allowed tool names, activates tools, and rebuilds prompt
and tool views. Harness may provide resolver mechanics, but this method remains
the product execution adapter for coding.

## Runtime Dynamic Extension Registration

Runtime dynamic extension registration should become a two-step product adapter
flow:

1. Project the extension tool into a neutral contribution.
2. Resolve contributions with existing registry state through
   `harness.tools.contribution`.
3. Let coding decide whether to register, reject, diagnose, activate, or defer
   the contribution.
4. Let coding update active tools and prompt views.

This keeps startup-time and runtime extension registration aligned without
moving concrete execution into harness.

The first implementation slice should be adapter verification only:

- project runtime extension tools to `ToolContribution`
- include source info and metadata as opaque values
- call the resolver with existing registry contributions
- preserve existing conflict behavior and active-tool behavior
- keep `ToolController.register_runtime_tool` as the mutation point

No concrete tool execution should move in this slice.

## Proposed Modules

If implementation proceeds, use focused modules under existing harness package
boundaries:

- `loushang.harness.execution.context`
- `loushang.harness.execution.contribution`

Do not add new top-level packages such as `loushang.workspace`,
`loushang.context`, `loushang.memory`, `loushang.session`, `loushang.product`,
or `loushang.runtime`.

Do not export Slice 2 types from top-level `loushang.harness.__all__` unless a
separate public API decision accepts that surface.

## Error And Diagnostic Boundary

Harness diagnostics should stay neutral:

- duplicate contribution
- missing reference
- unsupported contribution kind
- invalid neutral request shape

Coding diagnostics stay product-owned:

- extension tool conflict messages
- startup/resource loading phases
- session ids
- UI status
- prompt rebuild or active-tool policy explanations

Harness may carry `source_info` and metadata but must not interpret extension
manifest semantics or product resource policy.

## Validation Strategy

Implementation slices that follow this design should validate:

- `tests/architecture/test_import_boundaries.py`
- new harness execution/context tests
- coding runtime extension registration focused tests
- `tests/coding/test_extension_runner.py`
- `tests/coding/test_extension_api.py`
- `tests/coding/test_bootstrap.py -k 'extension_tool or extension'`
- `tests/coding/test_tool_registry.py`
- command catalog and session command controller tests if active tool behavior
  is touched
- screen/surface tests if prompt/tool view state is touched
- `uv --cache-dir .uv-cache run --extra dev ruff check <changed files>`
- `git diff --check`

The architecture import-boundary test must continue proving that harness does
not import `loushang.coding`, `loushang.tui`, `loushang.work`,
`loushang.method`, or `loushang.ai`.

## Deferred Implementation Items

Deferred implementation items include:

- defining final names and exact dataclass/protocol shapes
- deciding whether neutral context is needed before runtime contribution
  adapter verification
- deciding whether runtime registration supports only tools first or a generic
  contribution-kind envelope
- deciding compatibility shim lifetime for any execution context aliases
- deciding how source diagnostics map from neutral resolver diagnostics to
  coding resource diagnostics

## Recommended First Implementation Slice

Start with runtime extension tool registration adapter verification.

The first code slice should not introduce broad context APIs. It should only
extract the common contribution projection/resolution path for runtime extension
tools, prove behavior is unchanged, and document what remains product-owned.

That keeps Slice 2 incremental and avoids prematurely designing a generic
runtime substrate before a second product adapter needs it.
