# Loushang Harness Architecture

`loushang.harness` is the cross-product substrate that lets product adapters
prepare and run agent work without depending on another product package.

It is intentionally narrower than a product framework and broader than the
initial prepared-run facade. Harness owns product-neutral contracts, helper
engines, registries, and lifecycle shapes that `coding`, `design`, `research`,
`ppt`, `cowork`, and OEM products can share.

Harness may provide explicitly overridable cross-product platform defaults. It
does not own domain content/defaults, product stores, product UI state, method
planning, work event persistence, or AI provider behavior.

## Documents

- [Refactoring Principles](refactoring-principles.md) defines what may move
  into harness and how migration slices should be shaped.
- [Shared Capability Boundaries](shared-capability-boundaries.md) maps tools,
  approval, renderers, workspace, resources, context, memory, session, and
  diagnostics across harness and product adapters, and records the product
  kernel that must remain product-owned.
- [Coding To Harness Migration Inventory](coding-to-harness-migration-inventory.md)
  records how the current `loushang.coding` modules should be classified before
  implementation moves code.
- [Slice 1 Closure Status](slice-1-status.md) records the approval, tools-core,
  contribution, and presentation substrate that has landed on `lane/harness`,
  plus deferred runtime and product-adapter work.
- [Slice 2 Execution Context Design](slice-2-execution-context-design.md)
  records Slice 2A implementation complete for runtime tool contribution
  adapter verification and Slice 2B eligible under the neutrality evidence
  gate but not yet implemented.
- [Resource Frontmatter Boundary](resource-frontmatter-boundary.md) defines the
  shared parser owner, legacy compatibility paths, and product-owned resource
  semantics that remain outside harness.
- [Resource Provenance Boundary](resource-provenance-boundary.md) defines
  shared source metadata and resource diagnostic ownership while preserving
  coding path representations and public compatibility imports.
- [Platform Resource Layout Boundary](platform-resource-layout-boundary.md)
  records the implemented Harness-owned platform roots, resource/package
  runtime, standard resource scopes, `AGENTS.md` conventions, and built-in
  package mechanisms while preserving product content, activation, trust, and
  runtime projection.
- [Contribution Inventory Boundary](contribution-inventory-boundary.md) defines
  shared descriptor and registry ownership.
- [Extension Runtime Core Boundary](extension-runtime-core-boundary.md) defines
  shared manifest, loading, registration, conflict resolution, observer/input
  dispatch, resource contribution, and tool-wrapper ownership while preserving
  product policy, session/model behavior, and UI integration.
- [Context Budget And Accounting Boundary](context-budget-accounting-boundary.md)
  defines deterministic compaction-budget and usage-estimate record ownership
  while keeping message estimation and compaction policy in product adapters.
- [Context, Compaction, And Journal Foundations](context-compaction-journal-foundations.md)
  records the implemented ownership of context items and packing, selectable
  compaction strategies, profiled append-only JSONL mechanics, branch graphs,
  and focused Coding/Work compatibility adapters.
- [Runtime Data Foundations](runtime-data-foundations.md) records the follow-on
  ownership of transcript repositories, rebuildable projection indexes,
  layered configuration, explainable salience, and summary-profile mechanics
  while preserving Product schemas, prompts, defaults, and artifact semantics.
- [Product Runtime Core Boundary](product-runtime-core-boundary.md) defines
  shared runtime bindings and contexts, session-transition ownership,
  coalesced scheduling, AI/Agent data-contract placement, and the irreducible
  Product kernel that remains outside Harness.
- [Tool Output Projection Core Boundary](tool-output-projection-core.md) defines
  strict JSON ownership, Agent raw-result projection targets, failure timing,
  Harness journal/presentation adoption, and Product wire-schema ownership.
- [Diagnostics Core Boundary](diagnostics-core-boundary.md) defines shared
  diagnostic records, queries, summaries, startup checks, and in-memory engine
  ownership while keeping checks and presentation in product adapters.
- [Host Runtime Boundary](host-runtime-boundary.md) defines product-neutral host
  lifecycle, input-queue ledger, and ordered event ownership while preserving
  Agent loop and product session responsibilities.
- [OEM And Extension Architecture](oem-extension-architecture.md) describes how
  OEM customisation, extension contributions, and harness upgrades interact,
  including override mechanisms, extension categories, surface-type gaps, and
  upgrade-compatibility guarantees.
- [Workspace Execution Boundary](workspace-execution-boundary.md) defines
  harness-owned truncation, exec records, backend protocols, process execution,
  and coding compatibility ownership.
- [Workspace Operation Boundary](workspace-operation-boundary.md) defines
  filesystem operation protocols, local backend ownership, coding compatibility
  paths, and product adapters that remain outside harness.
- [Workspace Path And Mutation Boundary](workspace-path-mutation-boundary.md)
  defines configurable path resolution, canonical identity, optional input
  variants, mutation coordination, and coding path policy ownership.
- [Workspace Tool Pack Boundary](workspace-tool-pack-boundary.md) defines
  reusable concrete read/search/edit/exec ownership, Coding compatibility
  adapters, and the product-owned activation and policy boundary.
- [Harness Lane Development Workflow](development-workflow.md) defines how the
  long-lived `lane/harness` branch stays isolated from `main` until the
  migration is bootable and validated.

Accepted decisions that govern this directory:

- [ARD-001: Agent Harness and Product Adapter Boundaries](../agent/ARD-001-agent-harness-and-product-adapters.md)
- [ARD-002: Harness Product Adapter Substrate](../agent/ARD-002-harness-product-adapter-substrate.md)

## Boundary Summary

Harness may depend on stable `loushang.agent` primitives and the existing agent
loop. `loushang.agent` must not depend on harness.

Harness must not import:

- `loushang.coding`
- `loushang.design`
- `loushang.research`
- `loushang.ppt`
- `loushang.cowork`
- `loushang.method`
- `loushang.work`
- `loushang.tui`
- `loushang.ai`

If a harness contract needs to refer to method, work, channel, UI, or product
state, it should carry opaque ids, neutral metadata, or protocol-shaped values.
The product adapter interprets those values.

## Parallel Development Rule

Harness refactoring should not block TUI, agent, or AI provider work:

- TUI work stays under `loushang.tui` or product-owned UI adapters.
- Agent loop work stays under `loushang.agent`.
- Provider/model/auth work stays under `loushang.ai`.
- Harness work stays in product-neutral contracts and shared engines used by
  product adapters.

When a migration slice touches a product adapter, it must prove product behavior
is unchanged with focused tests and must keep the architecture import-boundary
tests passing.
