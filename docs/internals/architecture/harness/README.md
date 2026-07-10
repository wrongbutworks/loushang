# Loushang Harness Architecture

`loushang.harness` is the cross-product substrate that lets product adapters
prepare and run agent work without depending on another product package.

It is intentionally narrower than a product framework and broader than the
initial prepared-run facade. Harness owns product-neutral contracts, helper
engines, registries, and lifecycle shapes that `coding`, `design`, `research`,
`ppt`, `cowork`, and OEM products can share.

Harness does not own product defaults, product stores, product UI state, method
planning, work event persistence, or AI provider behavior.

## Documents

- [Refactoring Principles](refactoring-principles.md) defines what may move
  into harness and how migration slices should be shaped.
- [Shared Capability Boundaries](shared-capability-boundaries.md) maps tools,
  approval, renderers, workspace, resources, context, memory, session, and
  diagnostics across harness and product adapters.
- [Coding To Harness Migration Inventory](coding-to-harness-migration-inventory.md)
  records how the current `loushang.coding` modules should be classified before
  implementation moves code.
- [Slice 1 Closure Status](slice-1-status.md) records the approval, tools-core,
  contribution, and presentation substrate that has landed on `lane/harness`,
  plus deferred runtime and product-adapter work.
- [Slice 2 Execution Context Design](slice-2-execution-context-design.md)
  records Slice 2A implementation complete for runtime tool contribution
  adapter verification and Slice 2B gated pending a second product consumer.
- [Resource Frontmatter Boundary](resource-frontmatter-boundary.md) defines the
  shared parser owner, legacy compatibility paths, and product-owned resource
  semantics that remain outside harness.
- [Resource Provenance Boundary](resource-provenance-boundary.md) defines
  shared source metadata and resource diagnostic ownership while preserving
  coding path representations and public compatibility imports.
- [Workspace Execution Boundary](workspace-execution-boundary.md) defines
  harness-owned truncation, exec records, backend protocols, process execution,
  and coding compatibility ownership.
- [Workspace Operation Boundary](workspace-operation-boundary.md) defines
  filesystem operation protocols, local backend ownership, coding compatibility
  paths, and product adapters that remain outside harness.
- [Workspace Path And Mutation Boundary](workspace-path-mutation-boundary.md)
  defines configurable path resolution, canonical identity, optional input
  variants, mutation coordination, and coding path policy ownership.
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
