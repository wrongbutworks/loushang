# Runtime Profile Resolution And Binding

## Status

Implemented and first adopted by Coding. `loushang.harness.runtime.profile`
provides the product-neutral profile contract, resolver, snapshot, registry,
and binding lifecycle. `loushang.coding.runtime_profile` now declares Coding's
current session selections and binds them through the same contract.

## Purpose And Requirement Traceability

This component turns an explicitly declared Product runtime plan into a
deterministic, inspectable, session-scoped set of live bindings. It satisfies
the common mechanics in PDRI-001 through PDRI-012, with capability-specific
policy remaining in each Product and its later component document.

Harness owns resolution, strict data validation, lifecycle sequencing, stale
lease invalidation, and diagnostics. A Product owns its slots, baseline
selections, configuration defaults, source authorization, and policy that
accepts or rejects OEM and extension declarations. Harness never discovers a
plugin, grants authority, or infers a Product default here.

This is not a dependency-injection container or a global service locator. An
implementation can only be retrieved through the exact slot/key/version
selection in a resolved profile and the explicit `RuntimeProfileBinding`
returned by its binder.

## Data Model

`ProductRuntimePlan` contains a Product identifier, declared
`RuntimeCapabilitySlot` values, and Product baseline
`RuntimeCapabilitySelection` values. Each slot declares:

- its stable string key;
- `single`, `exclusive`, `ordered`, or `append_only` shape;
- process, tenant, workspace, session, turn, or channel scope;
- a `sealed` or `turn` refresh boundary; and
- the allowed sources (`product`, `oem`, `extension`, `session`).

Every selection is pure data: slot, implementation key, positive
implementation version, integer priority, and strict JSON-object
configuration. It never contains a callable, a connection, a credential, a
provider instance, or a Product object.

The first shared vocabulary is deliberately limited to these neutral slot
identifiers:

| Slot | Shape | Refresh | Intended contract owner |
| --- | --- | --- | --- |
| `conversation.store` | single | sealed | `harness.storage` |
| `agent.transcript_profile` | single | sealed | `harness.agent_transcript` |
| `context.compaction` | single | turn | `harness.context` |

The vocabulary does not import or prescribe an implementation. A Product can
bind a memory, file, database, or OEM store factory only when its plan and
policy allow it. Database, Redis, and index providers remain non-authoritative
until their own storage contracts are accepted (PDRI-006, PDRI-007).

## Resolution And Authority

`RuntimeProfileResolver` receives a Product plan plus layers that the Product
has already authorized. It applies a fixed source order:

```text
product -> oem -> extension -> session
```

Within a source, layers sort by integer priority and then `layer_id`; selections
sort by priority, implementation key, version, and canonical JSON
configuration. The resolver never uses discovery order or factory side
effects.

- A `single` or `exclusive` slot chooses the final authorized selection.
- An `ordered` slot replaces an earlier selection with the same
  `(implementation, version)` identity while retaining a deterministic
  sequence for distinct identities.
- An `append_only` slot retains every authorized selection, including repeated
  identities, in deterministic order.
- An undeclared slot, forbidden source, duplicate source/layer identity, or
  ambiguous single selection fails with `RuntimeProfileDiagnostic` values.
- Missing required slots fail rather than falling back implicitly.

The resolver accepts `RuntimeProfileLayer` data; it does not decide whether a
particular extension is trusted. Extension manifests, permissions, dependency
checks, OEM trust, and Product policy must complete before a layer is passed
to the resolver (PDRI-003, PDRI-009).

## Snapshot And Resume

`ResolvedRuntimeProfile.snapshot()` produces `RuntimeProfileSnapshot` schema
version 1. The JSON form records the Product, slot shape/scope/refresh boundary,
selected implementation key/version/configuration, and source-layer
provenance. `RuntimeProfileSnapshot.from_json()` validates that the entire
payload is strict JSON and rejects boolean or malformed version values.

The snapshot is evidence of what a current Loushang session used; it is not a
factory registry and is not an implicit compatibility importer. Native load
continues to accept the current Loushang format only. Pi, Claude Code, Codex,
or historical Loushang formats require explicit external or native migration
paths rather than permissive profile fallback (PDRI-008).

## Binding Lifecycle

`RuntimeCapabilityRegistry` registers exact `(slot, implementation, version)`
factories. `RuntimeProfileBinder` creates an entire profile in declared slot
order, disposes already-created values in reverse order when a later factory
fails, and exposes values only through `RuntimeProfileBinding`.

For a turn-safe rebind, the binder creates every replacement before disposing
the previous values. A creation failure leaves the previous binding current.
After a successful swap, `RuntimeBindingState` invalidates prior leases, so a
stale callback cannot access a new session binding accidentally.

`sealed` slots, including the initial store and transcript slots, cannot be
rebound during a session. `exclusive` slots are always sealed. `turn` slots
may only rebind through the explicit turn-boundary operation. If a disposer
itself fails after replacement creation, the binder reports the error and
does not publish the new profile; a capability-specific factory must make its
own disposer idempotent because a partially disposed external resource cannot
be made transactionally atomic by this generic layer (PDRI-005, PDRI-006,
PDRI-010).

Declared scope describes ownership and future pooling boundaries. This first
implementation binds an explicit resolved profile and intentionally does not
add a process-global cache or automatic cross-tenant reuse.

## Coding Adoption

`loushang.coding.runtime_profile` is the first Product composition adapter. It
declares the existing Coding choices as one `ProductRuntimePlan` and registers
exact factories for:

1. `coding.file` or `coding.memory` conversation storage, selected by the
   existing `persist` decision;
2. the current `coding.agent_transcript` profile; and
3. `coding.default` compaction behavior, which still delegates to Coding's
   existing prompt, model invocation, and compaction functions.

`SessionManager` creates, loads, and forks these bindings. New session headers
persist the pure JSON `runtimeProfile` snapshot. Persistent resume validates
the snapshot and rejects an unsupported profile instead of silently choosing a
different durable-store or transcript schema. A non-persistent open may use a
memory runtime binding while preserving the source file's durable snapshot.
`AgentSession` supplies the selected compaction behavior to its Coding
controller and disposes the binding with the session.

This adoption does not move `coding.settings_manager`, `coding.bootstrap`,
extension discovery, model registry, auth resolution, Coding file naming, or
compaction prompts into Harness. Coding has not yet admitted OEM or extension
layers for these slots; each remains Product-only until that trust and policy
surface has its own accepted design.

No channel is involved in resolution. TUI, Web, RPC, and future channel
adapters consume the same resolved profile or its diagnostics and may bind
channel-local presentation slots only in their own component design
(PDRI-012).

## Contract Tests

`tests/harness/runtime/test_profile.py` covers deterministic precedence,
source rejection diagnostics, ordered versus append-only semantics, strict
snapshot round-trip, turn-boundary rebind lease invalidation, sealed store
rejection, and factory rollback. Existing runtime binding tests retain the
generation-lease contract. The module has no imports from Coding, Agent, AI,
extensions, or concrete store implementations.

`tests/coding/test_runtime_profile.py` verifies the first Product adoption:
new memory/file sessions select the correct factory, headers retain the
snapshot, persistent resume validates it, transient open does not rewrite the
durable file choice, and `AgentSession` consumes then disposes the selected
compaction behavior.

## Non-Goals

- No plugin discovery, trust evaluation, permission granting, or OEM loader.
- No dynamic migration or hot swap of durable stores/transcript schemas.
- No universal memory, compaction prompt, artifact, model, auth, or
  presentation policy.
- No persistence of callables, live clients, credentials, or provider state.
