# Capability Composition Binding

## Status

Implemented by the `harness/resource-packs` wave. The standard binding runtime
now lives in `loushang.harness.capabilities.composition_runtime`; Coding's
former private binding facade has been removed.

## Purpose

This component binds Product-selected resource, prompt, skill, tool, and
command capabilities into one Agent Session without making Harness a Product
or extension container. Harness owns selection shape, source admission,
ordering, lifecycle, and diagnostics. Products retain their domain content,
default selections, executable handlers, and policy.

It satisfies PDRI-001, PDRI-004, PDRI-008, PDRI-009, PDRI-010, and PDRI-011.

## Standard Slots

| Slot | Shape / semantic / lifecycle | Sources | Meaning |
| --- | --- | --- | --- |
| `resource.runtime` | single, Exclusive Replacement, workspace, sealed | Product, OEM | Resource discovery/materialization implementation. Content may refresh; the backend cannot hot-swap inside a Session. |
| `prompt.sections` | single, Exclusive Replacement, session, turn-refreshable | Product, OEM, approved extension, session | One prepared-prompt composer; its admitted section inputs are Aggregate Contributions. |
| `skill.activation` | single, Exclusive Replacement, session, turn-refreshable | Product, OEM, approved extension, session | The policy that decides which discovered skills are active and model-visible. |
| `tool.packs` | single, Exclusive Replacement, session, turn-refreshable | Product, OEM, approved extension | One pack composer; its admitted tool-pack inputs are Aggregate Contributions. |
| `command.packs` | single, Exclusive Replacement, session, turn-refreshable | Product, OEM, approved extension | One pack composer; its admitted command-pack inputs are Aggregate Contributions. |

The selected prompt or pack composer retains its input contribution order and
owns its duplicate-name conflict rules. `tool.packs` and `command.packs`
deliberately exclude session selection because a session setting must not
acquire executable authority.

## Admission

`RuntimeProfileResolver` combines already admitted profile layers. It does not
authenticate an OEM or inspect extension permissions. Product bootstrap must
first call `RuntimeProfileAdmissionPolicy` with explicit
`RuntimeProfileLayerGrant` values. A grant is keyed by `(source, layer_id)` and
can restrict both allowed slots and granted permissions. Slot-specific
permissions are declared by the Product policy.

```text
extension manifest / OEM configuration
  -> Product trust and permission decision
  -> RuntimeProfileLayerGrant
  -> RuntimeProfileAdmissionPolicy
  -> RuntimeProfileResolver
  -> RuntimeProfileBinder
```

An unknown, untrusted, out-of-scope, or under-permissioned layer produces a
structured diagnostic and never reaches the binder. Admission is an
allow-list: it is not extension discovery, dynamic import, or a global service
locator.

## Pack Composition

After admission, `CapabilityPack` flattens live Product values in descending
priority and stable input order, retaining a provenance trace for each active
pack. It does not resolve duplicate tool or command names; the existing tool
contribution resolver and command catalog retain those capability-specific
conflict rules.

Coding binds its current Product-owned default profile through this mechanism
for the following compatibility-preserving paths:

- disabled-skill activation during bootstrap and resource refresh;
- prompt-section composition during initial assembly and tool-driven rebuilds;
- registered Coding tools before extension tool contributions, so the existing
  registry remains authoritative on duplicate tool names;
- extension command handler, built-in command handler, then resource command
  handler; the command list continues to display built-ins, extensions, then
  resource commands.

`coding.product_plan` selects
`standard_capability_composition_plan(product_id="coding")`; session headers
record its resolved snapshot under the separate `capabilityProfile` key. New
sessions and forks write that snapshot; persistent resume rejects a different
supported-profile snapshot. This is independent from `runtimeProfile`, which
continues to select the store, transcript, and context-compaction runtime.

The current Coding plan admits only Product selections because it registers
only Product-owned, pure factories. OEM and extension selections are not
silently accepted through settings or manifests. They become available only
when Coding owns a concrete factory, grants the source through admission, and
defines its resume contract.

## Durable And Refresh Rules

The resolved profile snapshot records variation semantic, implementation ID,
version, JSON configuration, and layer provenance. It never records live
factories, handler callables, credentials, or arbitrary extension objects.

`resource.runtime` is sealed for the Session. Refreshing resources must keep
the selected backend and atomically retain the last valid materialized bundle
when a later reload fails. Turn-refreshable slots can rebind only through the
runtime binder; a prior lease becomes stale after a successful rebind.

## Product Boundary

Harness provides neutral resource descriptors, prompt section composition,
tool activation, command catalog/dispatch, and this binding contract.

Coding retains:

- Coding prompt text, skill wording, and prompt preflight syntax;
- built-in coding tools and command handlers;
- Coding defaults and settings-to-selection translation;
- extension API compatibility mapping and user-facing diagnostics;
- model/auth policy, TUI/RPC presentation, and code artifact semantics.

Coding's current adoption routes resource and skill activation, prompt section
composition, and tool/command pack ordering through this contract. It must not
move model/auth execution, terminal/UI behavior, or arbitrary extension code
into Harness.

## Verification

- Harness tests cover source boundaries, untrusted layers, slot grants, and
  permission denial.
- Product tests cover the same resource bundle, prompt output, active skills,
  tool conflict result, and command conflict result before and after adoption.
- Resume tests assert the persisted runtime and capability profiles can be
  validated without rehydrating executable objects.
