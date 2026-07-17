# Product Runtime Injection Architecture

## Status

Proposed design. This directory freezes requirements and the component map for
dynamic Product runtime composition before introducing a new runtime API.
It does not claim that profile resolution, plugin-provided stores, or runtime
replacement are implemented today.

## Purpose

Products such as Coding, Design, Research, PPT, Cowork, and OEM variants need
to assemble different runtime behavior from common Harness mechanisms. A
Product supplies domain content, policy, defaults, and selection. Harness
supplies contracts, resolution mechanics, lifecycle mechanics, and diagnostics.

The target is not a service locator or a universal Product framework. It is a
bounded way to resolve declared capability selections into one observable,
session-scoped runtime configuration.

```text
Harness defaults
  -> Product runtime plan
  -> trusted OEM overrides
  -> Product-allowed extension contributions
  -> session-scoped resolved runtime snapshot
```

## Document Index

| Document | Role | Status |
| --- | --- | --- |
| [00 Requirements](00-requirements.md) | Product-facing requirements, constraints, non-goals, and acceptance criteria. | Proposed |
| [01 Component Inventory](01-component-inventory.md) | Index of runtime-injection components, their owners, dependencies, and migration relationship. | Proposed |
| [Component Design Directory](components/README.md) | One detailed binding contract for each capability component. | Planned |

Detailed component documents are added immediately before their corresponding
implementation wave. They use the common template named in the component
inventory so that Store, Memory, Compaction, Tool Pack, and other components
do not repeat generic resolution rules.

## Scope

This design covers dynamic binding of Product runtime capabilities, including
durable conversation storage, transcript profiles, memory, compaction,
artifact handling, resources, prompts, skills, methods, tools, commands,
policy, approval, model selection, and presentation choices.

Multi-client channel transport, attach/replay protocol, and channel control
arbitration are intentionally outside this directory. They will be specified
under `docs/internals/architecture/channel/` after this runtime composition
contract is stable.

## Relationship To Current Migration

The current Coding-to-Harness work has already moved many mechanisms without a
single dynamic composition contract: storage protocols, transcript profiles,
context packing and compaction coordination, capabilities, resources,
extensions, policy/approval, runtime bindings, and ordered runtime events.

This directory is the design gate for the next ownership waves. It does not
reopen completed boundaries. Instead, it specifies how Products, OEMs, and
extensions select and bind the existing mechanisms consistently as Coding's
remaining session facade is reduced.

Every implementation wave that introduces a new injectable capability must:

1. add or accept that capability's detailed component binding document;
2. add a Product-neutral contract probe and a Coding compatibility probe;
3. update the Coding-to-Harness migration inventory with the resulting owner;
4. record whether the capability is sealed, refreshable at a turn boundary, or
   channel-local.

## Related Boundaries

- [Shared Capability Boundaries](../shared-capability-boundaries.md)
- [Product Runtime Core Boundary](../product-runtime-core-boundary.md)
- [Product Configuration Runtime Boundary](../product-configuration-runtime-boundary.md)
- [Context, Compaction, And Journal Foundations](../context-compaction-journal-foundations.md)
- [Store And Runtime Event Protocol Migration](../store-event-protocol-migration.md)
- [OEM And Extension Architecture](../oem-extension-architecture.md)
