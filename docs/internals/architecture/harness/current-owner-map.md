# Harness Current Owner Map

Status: current architecture reference.

This document is the short, authoritative map of the implemented
`loushang.harness` boundaries. Detailed boundary records explain individual
decisions; migration ledgers record how the code arrived here and are not a
second description of current ownership.

## Scope

Harness is the cross-Product execution substrate. It owns reusable mechanisms,
contracts, lifecycle shapes, and explicitly overridable platform defaults. A
Product owns domain language, prompts, policy choices, presentation semantics,
and the conversion from user intent or Method output into Product operations.

Harness does not import Product packages. In particular, Harness must not
depend on `loushang.coding`, `loushang.work`, `loushang.method`,
`loushang.channel`, `loushang.harnesstui`, or Product UI packages.

## Implemented Owners

| Owner | Owns | Does not own |
| --- | --- | --- |
| `runtime` | cancellation, retry/scheduling primitives, runtime-profile declarations, admission, resolution, binding, refresh, disposal | Product capability selection policy or provider behavior |
| `config` | layered/scoped configuration mechanics and optional Agent settings types, patch commands, schema codec, and manager lifecycle | Product-only fields, paths, activation effects, credentials, or presentation |
| `session` | optional Agent-session profile, Product-neutral assembly, turn/lifecycle coordination, command and maintenance bindings, Session facade and inspection | Product prompt content, domain operations, UI state, Work persistence |
| `conversation` | Product-neutral conversation identity, records, repository/catalog and replay contracts | Agent/AI message schema or Product-specific payload meaning |
| `transcript` | optional Agent/AI transcript profile, codecs, file/session lifecycle, context rebuild, compaction/retry/navigation mechanisms | Product compaction prompts, semantic summary policy, Product store selection |
| `context` | context items, packing, deterministic budget/accounting records, summary evaluation foundations | Product salience policy or model-specific estimation decisions |
| `tools` / `approval` / `policy` / `sandbox` | tool authoring and hosted execution mechanics, action policy evaluation, approval lifecycle, effects and containment ports | Product risk defaults, Product approval wording, arbitrary Product commands |
| `resources` / `extensions` / `capabilities` | resource discovery and precedence, package materialization mechanics, extension runtime, capability composition | Product-owned built-in content, trust decisions, activation policy |
| `host` / `cli` / `events` / `presentation` | Product-neutral host lifecycle, RPC/JSON projection, runtime event contracts and reusable presentation | AppService tenancy, Channel protocol, Product grammar or final UI composition |
| `diagnostics` / `continuity` / `workspace` | shared diagnostic records/export, continuity provider composition, workspace and execution primitives | Product-specific recovery UX, business audit retention, Product artifact semantics |

## Dependency Direction

The intended direction is:

```text
Product composition root
        -> Harness public contracts and optional profiles
        -> Agent / AI public contracts where an optional profile requires them

AppService / Product host
        -> Product narrow ports
        -> Harness Session or Work adapter

Harness -/-> Product, Work, Method, Channel, Harnesstui, or Product UI
```

`session` is an assembly owner and therefore has high fan-out. High fan-out is
acceptable at that composition boundary; cycles, Product imports, and lower
layers importing the Session public barrel are not.

## Session Assembly Shape

The standard Agent-session composition has three explicit phases:

1. Foundation: diagnostics, tools, resources, navigation, and bash.
2. Maintenance: compaction and retry mechanisms with Product policy inputs.
3. Product bindings: model, identity, command, extension, maintenance, and
   inspection bindings.

`SessionCompositionPorts` stores those phase inputs as cohesive records.
`SessionComposition` stores the corresponding phase results and retains flat,
read-only compatibility properties for existing consumers. No generic bridge
or second coordinator is introduced merely to forward callbacks.

## Public API And Loading

`loushang.harness` is the narrow base entrypoint. Optional, larger profiles such
as `loushang.harness.session` and `loushang.harness.transcript` preserve their
published symbols through lazy facades: importing a profile does not construct
or import all implementation runtimes, while accessing a symbol loads its owner
module and caches the result.

Compatibility facades remain stable while large implementation pipelines are
split internally. The implemented dependency direction is:

```text
resource loader facade -> snapshot pipeline -> discovery + resolution
                                            -> precedence policy

runtime profile facade -> types + admission + resolution + binding + standard slots
admission / resolution / binding / standard slots -> profile types

Agent settings manager -> typed settings patch + settings schema codec
typed settings patch -> settings schema codec field rules
settings schema codec / typed settings patch -> Agent settings types
```

Resolution never imports discovery, live profile binding never imports profile
resolution, and internal leaf modules never import their public facade. The
Agent settings manager depends only on the explicit codec/patch ports enforced
by the architecture tests, not on field-level serializer helpers.

## Architecture Gates

`make check-harness` is the integration gate. The architecture tests enforce:

- an acyclic internal Harness dependency graph;
- no Session-module import from the Session public barrel;
- one-way Harness, Work, and Channel dependencies;
- explicit Agent/AI import allowlists for optional profiles;
- one-way resource loader, runtime profile, and Agent settings internals with
  an exact manager-to-codec/patch import allowlist;
- Product-neutral Harnesstui and shared runtime owners.

New boundaries must update this map when they change current ownership. A
migration ledger alone is not sufficient evidence of the resulting boundary.

## Product-Owned Exclusions

The following remain Product-owned unless a separate accepted boundary record
demonstrates multiple real Product implementations:

- prompts, model defaults, domain vocabulary, and policy defaults;
- user-intent parsing and Product operation resolution;
- Method-to-Work preparation and Product Work execution;
- Product event vocabulary and final UI projection;
- Product storage roots, retention policy, and artifact meaning;
- cloud tenancy, billing policy, credentials, and AppService authorization.

## Document Authority

When documents disagree, use this order:

1. current source and architecture gates;
2. this current owner map;
3. accepted boundary documents linked from the Harness README;
4. proposed architecture documents;
5. migration plans, ledgers, slice status, and historical inventories.

Completed migration records should be retained for traceability but must not be
read as current ownership specifications.
