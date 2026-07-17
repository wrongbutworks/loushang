# Product Runtime Injection Requirements

## Status

Proposed. These requirements constrain later component designs and
implementation waves. They intentionally do not prescribe Python class names,
module paths, or a dependency-injection container.

## Problem Statement

One Product must be able to choose runtime behavior that differs materially
from another Product without copying Harness mechanisms. For example, Coding,
PPT, and Research may use different context compaction, memory, artifact, and
durable-store strategies while sharing session, event, transcript, and
diagnostic contracts.

Product selection must also support trusted OEM overrides and explicitly
allowed plugin contributions. Runtime dynamism must not compromise durable
facts, deterministic replay, permissions, or compatibility.

## Terms

| Term | Meaning |
| --- | --- |
| Capability | A named runtime concern, such as a conversation store, memory provider, compaction planner, or tool pack. |
| Capability slot | The declared location at which one or more implementations of a capability may bind. |
| Product runtime plan | Product-owned declaration of defaults, selections, configuration, and allowed override depth. |
| Contribution | Versioned declaration from an OEM or extension that can participate in an allowed capability slot. |
| Resolved runtime profile | Deterministic result of applying precedence, validation, and configuration to a Product runtime plan. |
| Runtime binding | A live implementation instance created from a resolved profile. |
| Runtime snapshot | Durable description of the resolved selections and configuration used by one session. |
| Sealed capability | A capability whose binding cannot change during an active session. |

## Functional Requirements

### PDRI-001: Product-Owned Composition

A Product must declare its runtime defaults and choose the capability slots it
uses. Harness must not infer a Product's prompt, tool pack, memory, compaction,
store, artifact, approval, model, or presentation defaults.

### PDRI-002: Explicit Slot Semantics

Every injectable capability must declare whether it is a single selection, an
ordered composition, an exclusive replacement, or an append-only contribution.
It must also declare its binding scope and mutability.

### PDRI-003: Controlled Sources

A resolved profile may draw selections from Product defaults, typed
configuration, trusted OEM overrides, Product-allowed extension contributions,
and explicitly authorized session overrides. A source may not alter a slot that
the Product has sealed.

### PDRI-004: Deterministic Resolution

Resolution order, conflicts, missing dependencies, disabled contributions, and
fallback behavior must be deterministic and explainable. The result must not
depend on plugin discovery order or object construction side effects.

### PDRI-005: Scope And Lifecycle Safety

Bindings must declare one of process, tenant, workspace, session, turn, or
channel-local scope. Creation, refresh, disposal, cancellation, and failure
behavior must be explicit. Runtime refresh may occur only at a capability's
declared safe boundary.

### PDRI-006: Durable Fact Protection

Conversation stores, transcript profiles, and persisted artifact schemas are
session-sealed unless an explicit migration transaction is designed for them.
Compaction, memory, and cache changes must never silently replace or erase
durable transcript or artifact facts.

### PDRI-007: Data-Layer Separation

The design must distinguish durable stores from context memory and rebuildable
indexes or caches. Redis, vector search, and full-text indexes may accelerate
memory retrieval but are not authoritative conversation or artifact stores.

### PDRI-008: Reproducibility And Resume

The session runtime snapshot must identify the selected capability
implementations, compatible versions, and JSON configuration needed to explain
resume, fork, replay, diagnostics, and later migration decisions. It must not
serialize arbitrary live objects, callables, or credentials.

### PDRI-009: OEM And Extension Safety

Contribution acceptance must be governed by Product policy, trust, declared
permissions, compatibility, and dependency validation. A plugin cannot gain
store, credential, process, approval, or data-exfiltration authority merely by
registering a contribution.

### PDRI-010: Failure And Diagnostics

Resolution and binding failures must produce structured diagnostics containing
the capability slot, requested contribution, source layer, and failure reason.
A failed replacement must preserve the last valid binding where the component
contract permits fallback.

### PDRI-011: Product Facade Reduction

Shared runtime mechanisms must move behind Harness contracts. Product packages
retain domain content, policy, selection, configuration, artifact semantics,
compatibility projection, and assembly, rather than copied session/store/event
implementations.

### PDRI-012: Channel Independence

Runtime composition must not depend on a terminal, web, RPC, or other channel.
Presentation and theme selections may be channel-local, but they must not
change durable session facts.

## Quality Requirements

- Harness must not import a Product package to resolve a profile or binding.
- The design must not introduce a global service locator or arbitrary object
  registry.
- Capability configuration must be strict JSON-compatible data with an
  explicit schema/version owner.
- Product-neutral contract tests must cover resolution, lifecycle, diagnostics,
  and sealing; Coding tests must preserve existing behavior during cutover.
- Unknown future contributions must fail explicitly or remain inactive; they
  must not be treated as a valid fallback implementation.

## Non-Goals

This wave does not:

- implement a multi-client channel protocol or persistent event log;
- define one universal Product schema, memory algorithm, compaction prompt, or
  artifact model;
- move credentials, provider execution, or model registry implementation into
  a generic injection container;
- allow runtime Store hot swapping or implicit backend-to-backend migration;
- replace existing focused Harness contracts before their capability binding
  design is accepted.

## Acceptance Criteria For Detailed Designs

Each component design must trace its requirements by identifier, specify its
slot semantics and lifecycle, and define Product, OEM, extension, and session
override authority. A detailed design is not implementation-ready until it
also defines its runtime snapshot, failure behavior, diagnostics, and contract
tests.
