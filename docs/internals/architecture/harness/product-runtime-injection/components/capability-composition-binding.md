# Capability Composition Binding

## Purpose

This component binds Product-selected resource, prompt, skill, tool, and
command capabilities into one Agent Session without making Harness a Product
or extension container. Harness owns selection shape, source admission,
ordering, lifecycle, and diagnostics. Products retain their domain content,
default selections, executable handlers, and policy.

It satisfies PDRI-001, PDRI-004, PDRI-008, PDRI-009, PDRI-010, and PDRI-011.

## Standard Slots

| Slot | Shape / lifecycle | Sources | Meaning |
| --- | --- | --- | --- |
| `resource.runtime` | single, workspace, sealed | Product, OEM | Resource discovery/materialization implementation. Content may refresh; the backend cannot hot-swap inside a Session. |
| `prompt.sections` | ordered, session, turn-refreshable | Product, OEM, approved extension, session | Prepared prompt section providers. |
| `skill.activation` | single, session, turn-refreshable | Product, OEM, approved extension, session | The policy that decides which discovered skills are active and model-visible. |
| `tool.packs` | ordered, session, turn-refreshable | Product, OEM, approved extension | Definitions/materializers to contribute; a session cannot inject an executable handler. |
| `command.packs` | ordered, session, turn-refreshable | Product, OEM, approved extension | Command descriptors and handlers; a session cannot inject an executable handler. |

An ordered slot retains contributor order after source/layer/selection ordering;
the concrete pack runtime owns duplicate-name conflict rules. `tool.packs` and
`command.packs` deliberately exclude session selection because a session
setting must not acquire executable authority.

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

Coding's first adoption uses this mechanism for two compatibility-preserving
orders:

- registered Coding tools before extension tool contributions, so the existing
  registry remains authoritative on duplicate tool names;
- extension command handler, built-in command handler, then resource command
  handler; the command list continues to display built-ins, extensions, then
  resource commands.

The first adoption moves resource activation and pack ordering only. It does
not yet expose OEM or extension profile selections through Coding settings or
persist a capability-composition snapshot. Those are the next binding step,
after each selectable implementation has a real factory and resume contract.

## Durable And Refresh Rules

The resolved profile snapshot records implementation ID, version, JSON
configuration, and layer provenance. It never records live factories, handler
callables, credentials, or arbitrary extension objects.

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

Coding's first adoption routes its resource activation and tool/command pack
ordering through this contract. The next binding step must not move model/auth
execution, terminal/UI behavior, or arbitrary extension code into Harness.

## Verification

- Harness tests cover source boundaries, untrusted layers, slot grants, and
  permission denial.
- Product tests cover the same resource bundle, prompt output, active skills,
  tool conflict result, and command conflict result before and after adoption.
- Resume tests assert the persisted runtime profile can be validated without
  rehydrating executable objects.
