# Loushang Product And OEM Glossary

This glossary defines the canonical Product, OEM, package, plugin, and
capability-composition terms used by Loushang architecture documents and
implementations. Use these terms consistently in new Product, Harness, OEM,
resource, and launch-surface documents.

The glossary defines vocabulary and boundaries. It does not claim that every
described discovery, registration, or routing mechanism is already implemented.
Current implementation status belongs in the relevant architecture boundary
document and code.

For Chinese discussion terms, see the
[Chinese terminology table](./loushang-product-zh.md).

## Core Mental Model

```text
Platform CLI or OEM CLI
  -> Platform Host
  -> OEM Profile
  -> Product Registry
  -> Product Router
  -> Product Factory
  -> one active Product Runtime per Product Session
       -> Product Kernel
       -> admitted Capability Packs
       -> activated Product Capability Bundles
       -> Product-approved Plugin contributions
```

Harness supplies product-neutral mechanisms. A Product supplies domain
semantics, defaults, and policy. An OEM selects and overlays Products. Plugins
contribute optional resources or behavior only after Product and OEM admission.

## Platform And Launch Model

### Platform

The installable and runnable Loushang system that can discover, register, and
host one or more Products. The Platform is not itself a domain Product.

### Platform Host

The process-level composition root that owns Product discovery, OEM selection,
Product routing, shared process or tenant services, and runtime disposal.

A Platform Host may expose a CLI, TUI, RPC, web, embedded, or other channel. It
does not supply Coding, PPT, Research, or other domain semantics.

### Platform CLI

The neutral `loushang` command entry point. It resolves an explicitly selected
or configured default OEM and Product, then delegates startup through registered
descriptors and factories.

A Platform CLI should not derive an import path such as
`loushang.<oem>.cli` from an unvalidated string. Registration and trust precede
loading.

### OEM CLI

An OEM-branded command entry point, such as `acme`, that starts the same Platform
Host with a predetermined or selectable OEM Profile.

An OEM CLI is a launch surface, not a separate runtime architecture. It should
call the shared Platform bootstrap rather than copy Product startup,
registration, session, or disposal mechanisms.

### Default OEM

The OEM Profile selected when a launch request does not specify an OEM.

A default is configuration, not code ownership. Selecting a Default OEM must
not make the neutral Platform import one hard-coded OEM module.

### Default Product

The Product selected by an OEM or Platform launch when the user does not
explicitly choose one.

For example, an OEM may define `coding` as its Default Product while also
making the `ppt` Product and a `ppt-authoring` Product Capability Bundle
available.

## Product Model

### Product

A domain-specific Loushang experience with its own goals, language, completion
criteria, prompts, capability defaults, policy, context behavior, artifact
semantics, session compatibility, commands, configuration, and presentation.

Examples include Coding, PPT, Research, Design, Cowork, and Environmental.

A Product is not merely a collection of Skills or Tools. It owns the domain
decisions required to compose those capabilities into a coherent runtime.

### Product Kernel

The irreducible Product-owned semantics and policy that must not migrate into
Harness merely because another Product could reuse the surrounding mechanism.

The Product Kernel includes domain goals, system-prompt content, capability
selection, context salience, compaction and summary policy, risk and approval
defaults, artifact semantics, session compatibility, and Product presentation.

### Product Adapter

The code that binds one Product Kernel to Harness, Agent, Work, Channel, TUI,
and other shared mechanisms.

A Product Adapter should remain small as shared mechanisms improve, but it must
retain Product-exclusive semantics and policy.

### Product Package

An installable software distribution that provides a Product Descriptor,
Product Factory, Product Adapter, and any built-in Product resources.

A Product Package may be first-party or independently distributed. Installation
does not automatically grant activation or trust. A Product Package is distinct
from the current resource-oriented Package and Plugin abstractions.

### Product Descriptor

The data-only registration record for one Product. It identifies the Product
and its compatibility boundary without constructing a live runtime.

A Product Descriptor should include at least a stable `product_id`, display
name, Product version, supported Product API version, factory reference, and
declared compatibility or host requirements.

### Product Factory

The Product-supplied factory that creates a Product Runtime from an admitted
Platform, OEM, workspace, channel, and session context.

The factory owns Product assembly. Product discovery and Product selection do
not construct live Product services as side effects.

### Product Registry

The deterministic catalog of admitted Product Descriptors available to one
Platform Host.

The Product Registry rejects ambiguous Product identities and does not choose a
default Product. Discovery populates the registry; OEM policy filters it; the
Product Router selects from it.

### Product Router

The Platform or OEM mechanism that selects a registered Product for a launch,
request, workspace, or persisted session.

When restoring a session, the persisted `product_id` is authoritative unless an
explicit migration is performed. Routing must not silently reinterpret one
Product's session as another Product.

### Product Runtime Plan

The Product-owned, data-only declaration of runtime capability slots, baseline
selections, allowed override sources, and configuration.

A Product Runtime Plan does not contain factories, credentials, plugin
discovery, or live objects.

### Resolved Runtime Profile

The deterministic result of applying admitted Product, OEM, extension, and
session layers to a Product Runtime Plan.

Its durable snapshot explains which capability implementations and
configuration were used by a Product Session.

### Product Runtime

One live, bound execution of a Product for a specific lifecycle scope. It is
created by a Product Factory from a Resolved Runtime Profile and admitted
resources and services.

A Product Runtime is not a global singleton. Process- or tenant-scoped services
may be shared, but Product, workspace, session, and channel state follow their
declared scopes.

### Active Product

The Product whose runtime owns the current Product Session and interprets the
current input, context, policy, artifacts, and presentation.

One Product Session has exactly one Active Product. A Platform or OEM may host
many Product Runtimes and Product Sessions concurrently.

### Product Session

A durable or ephemeral interaction scope owned by one Product and identified by
that Product's session schema and compatibility policy.

A Product Session records its `product_id` and the runtime selections required
for resume, fork, replay, diagnostics, and migration. Adding a capability does
not change the owning Product identity.

### Product Handoff

An explicit transfer of a Work item, artifact reference, or user intent from
one Product Session to another Product.

For example, Coding may create a deck artifact and hand it to a PPT Product
Session for canvas-level editing. A Product Handoff is not an in-place mutation
of the source session's `product_id`.

## OEM Model

### OEM

A branded or policy-specific Platform configuration that selects Products and
overlays their allowed configuration, resources, capabilities, models,
permissions, channels, and presentation.

An OEM is not automatically a Product. It becomes a Product only when it defines
a distinct Product Kernel and registers its own Product identity.

### OEM Package

An installable distribution that provides an OEM Descriptor or OEM Profile,
optional OEM CLI, resource overlays, extension contributions, branding, and
Product availability policy.

One OEM Package may enable and configure multiple Product Packages.

### OEM Profile

The data-only configuration that identifies an OEM's enabled Products, Default
Product, Product-specific overlays, shared extensions, branding, model policy,
and permission policy.

An OEM Profile must not contain live runtime objects or credentials.

### OEM Layer

An admitted set of OEM-owned selections or resources applied to a Product's
declared override points.

An OEM Layer cannot alter a capability slot sealed by the Product and does not
gain authority merely by being discovered.

### Multi-Product OEM

An OEM Profile that admits more than one Product, such as Coding and PPT, into
the same Platform Host.

Multi-Product means co-installed and routable Products. It does not mean that
one Product Session simultaneously has multiple owning Product identities.

### OEM Product

Use this term only when an OEM Package defines and registers a distinct Product
Kernel and Product identity.

Do not use OEM Product as a synonym for OEM Package, OEM Profile, a branded
Coding launch, or a Product with OEM overlays.

## Capability Composition

### Capability

A named runtime or domain concern, such as a conversation store, memory
provider, compaction planner, tool definition, command descriptor, deck
renderer, or artifact handler.

### Product Capability Requirement

An opaque Product-level request for a named capability, declared by an admitted
Skill, Method, Work plan, Session operation, or Product default. A requirement
does not name executable handlers, select a Harness implementation, grant
authority, or imply activation. The Active Product resolves it through its
admitted capability catalog and policy.

### Capability Slot

A Product-declared location at which one or more implementations of a
Capability may bind. The slot defines composition shape, lifecycle scope,
refresh boundary, and allowed contribution sources.

### Capability Pack

One Product-approved, ordered contribution group for a single capability item
family after runtime-profile admission.

In code, `CapabilityPack[T]` contains a `pack_id`, source, priority, enabled
state, and ordered `T` items. Tool packs and command packs are examples.

A Capability Pack is not an installable archive, Product Package, Plugin, or
multi-family bundle. It does not discover contributions or grant authority.

### Product Capability Bundle

An assembly or distribution-level grouping of several related capability and
resource families that can be admitted into a Product.

For example, a `ppt-authoring` Product Capability Bundle may provide Skills,
prompt fragments, tool and command Capability Packs, deck assets, renderers,
and artifact handlers. Each family still passes through its own Product-owned
admission, trust, composition, and lifecycle rules.

A Product Capability Bundle does not become the Active Product. If PPT-specific
canvas state, session compatibility, compaction, approval, or artifact lifecycle
is required, use the PPT Product and an explicit Product Handoff.

### Capability Mount

The Product-owned activation of an admitted Product Capability Bundle or
Capability Pack for a specific runtime scope.

A Product may define `disabled`, `on_demand`, or `always` mount policy. Scoped
mounts from Product defaults, manual selection, Skills, and Method/Work steps are
additive and independently owned; releasing one scope must not remove another
scope's request. A Capability Mount is unrelated to an AppService control lease.

For example, Coding may mount `ppt-authoring` while remaining the Active
Product. The Product Session should snapshot continuity-critical mounted
identities and compatible versions.

## Package, Plugin, Extension, And Resource Model

### Package

An overloaded implementation word that must be qualified in architecture
documents.

Use Product Package for an installable Product, OEM Package for an installable
OEM configuration, and Resource Package for an installable resource
collection. Do not use unqualified Package when ownership matters.

### Resource Package

An installable or materialized collection of resources such as Skills, prompts,
themes, extensions, and Product-specific assets.

A Resource Package contributes content to an admitted Product. It does not
register or start a Product unless it also implements the separate Product
Package registration contract.

### Plugin

An optional, independently enabled contribution source resolved into resource
roots and, where supported, extension contributions.

A Plugin runs under Product and OEM activation and trust policy. It does not own
the Product lifecycle, select the Active Product, or acquire execution authority
merely by being installed.

### Extension

Executable or declarative optional behavior contributed through a defined
extension surface, such as a Tool, command, hook, policy interceptor, approval
replacement, renderer, or channel adapter.

An Extension is one possible contribution carried by a Plugin or Resource
Package. Product or OEM policy decides whether it is admitted and active.

### Skill

An instruction resource that teaches the model a specialized workflow,
domain convention, or Tool-usage pattern.

A Skill is Product content or an optional contribution. It is not executable
authority, a Product, or a replacement for a Tool or Extension.

### Product Asset

A Product-interpreted file used to create or present domain artifacts, such as
a deck template, slide layout, brand kit, image, document template, or design
asset.

Harness may discover and track the asset as a resource, while the Product owns
its semantic type, validation, preview, activation, and artifact behavior.

### Deck Asset

A PPT-domain Product Asset, such as a presentation template, slide layout,
master, theme, brand kit, or reusable media item.

A Deck Asset may be shipped with the PPT Product, an OEM overlay, or a
Product Capability Bundle. It is not a Skill and should not be modeled as one
merely to reuse relative filesystem paths.

## Canonical Launch Interpretations

### Neutral Platform Launch

```text
loushang
  -> resolve Default OEM
  -> resolve that OEM's Default Product
  -> create the selected Product Runtime
```

### OEM-Branded Launch

```text
acme
  -> start the shared Platform Host with OEM Profile "acme"
  -> select Product "coding"
  -> mount admitted OEM and ppt-authoring capabilities
```

In this example, `coding` remains the Active Product. The OEM Profile and
mounted capability identities are recorded separately.

### Full PPT Launch Or Handoff

```text
loushang ppt
  -> select Product "ppt"
  -> create a PPT Product Session
```

Use this path when PPT owns the session, canvas, deck lifecycle, compaction,
policy, or presentation semantics.

## Relationship Rules

- Harness provides mechanisms; Products provide domain defaults and semantics.
- A Product Package registers a Product; a Plugin contributes to a Product.
- An OEM Package may configure multiple Product Packages.
- One Platform Host may run multiple Products concurrently.
- One Product Session has exactly one Active Product.
- A Product may mount many admitted Capability Packs and Product Capability
  Bundles.
- A Product Capability Bundle augments a Product; it does not silently replace
  it.
- Product Handoff crosses Product-session boundaries explicitly.
- Installation, discovery, admission, activation, and execution are separate
  lifecycle decisions.

## Terms To Avoid

### Product Plugin

Avoid this term because it conflates Product registration with optional Plugin
contribution. Use Product Package unless the subject specifically implements
both contracts, and name both roles explicitly.

### PPT Skill Pack

Avoid this term when the package also contains Tools, commands, renderers, or
deck assets. Use `ppt-authoring` Product Capability Bundle. Use Skill pack only
for a collection containing Skills.

### OEM Product

Avoid this term for a branded launcher or Product overlay. Use OEM CLI, OEM
Profile, OEM Package, or Product with OEM Layer as appropriate.

### Multi-Product Session

Avoid this term. Use Multi-Product OEM for deployment availability, Product
Handoff for cross-Product transfer, or Composed Product if a genuinely new
Product Kernel owns the unified session.

### `loushang.<OEM>.cli`

Treat this as a possible Python module path, not an architecture concept or
required packaging convention. The canonical concepts are OEM CLI, OEM
Descriptor/Profile, registered launch entry point, and shared Platform Host.
