# Harness Extension Runtime Core Boundary

## Status

Status: implementation complete for integration into `lane/harness`.

This boundary moves the product-neutral extension runtime core into
`loushang.harness.extensions`. Coding remains a product adapter and preserves
accepted import paths without maintaining a second implementation.

## Harness Ownership

Harness owns these mechanisms:

- extension event vocabulary and manifest declaration parsing;
- `LoadedExtension`, contribution registration records, input results, and
  neutral activation-decision records;
- `ExtensionContributionAPI` for hooks, tools, commands, flags, shortcuts, and
  message renderer registration;
- descriptor-driven Python module loading, legacy-object adaptation, manifest
  attachment, and contribution projection;
- deterministic command naming, first-wins flag/shortcut/tool resolution,
  source provenance, and duplicate diagnostics;
- ordered failure-contained observer dispatch and sequential input
  transformation;
- resource contribution execution and `promptPaths`, `skillPaths`, and
  `themePaths` normalization;
- registered-tool execution wrapping with an injected context factory.

The implementation is split across focused modules under
`loushang.harness.extensions`: `manifest`, `types`, `api`, `loader`, `registry`,
`dispatch`, `resources`, `contributions`, and `wrapper`. These modules are not
exported from top-level `loushang.harness`.

Harness consumes already-discovered `ExtensionDescriptor` values. It does not
choose search roots, trust an extension, enable a product capability, or decide
whether a descriptor should be passed to the loader. A product must apply its
trust, approval, and activation policy before executable extension code is
loaded.

## Coding Adapter

Coding keeps:

- `ExtensionAPI` additions for session entries, messages, model selection,
  thinking level, labels, and provider registration;
- concrete permission-level defaults and capability mapping in
  `policy_from_manifest`;
- rich Coding extension contexts and runtime bindings;
- session switch/fork/compact/tree decisions and Coding event projection;
- system-prompt augmentation, model/provider behavior, Agent tool-call result
  adaptation, compaction behavior, and UI integration;
- the `ExtensionRunner` composition adapter that connects Harness engines to a
  Coding session.

`loushang.coding.extensions.loader.ExtensionLoader` now only injects the Coding
API factory, Coding permission policy, and legacy event names into the Harness
loader. The Coding `manifest`, `events`, `contributions`, and `wrapper` modules
are compatibility re-exports. Shared records imported through
`coding.extensions.types` are the same Harness-owned objects.

## Policy Injection

Harness supplies a neutral `ExtensionPolicyDecision` and a conservative
descriptor-enabled default. It does not interpret product permission levels or
capabilities. Products inject an `ExtensionPolicyResolver` into the loader.

Harness also leaves runtime state opaque. `ExtensionContributionAPI` only uses
capability-shaped callbacks when a product binds them. Coding's binding record
may contain additional session/model/UI callbacks without pulling those fields
into the shared contract.

## Failure And Ordering Contract

Extension order and handler registration order are stable. One failing handler
adds a provenance-bearing diagnostic, invokes the optional runtime-error
callback, and does not stop later handlers.

Commands with duplicate names receive deterministic numeric invocation
suffixes while avoiding literal-name collisions. Duplicate tools, flags, and
shortcuts are first-wins and produce diagnostics for rejected contributions.
Products may replace this policy later by supplying a different registry layer;
the core does not infer user intent.

## Compatibility

Accepted Coding imports remain valid, including:

```python
from loushang.coding.extensions import ExtensionLoader, LoadedExtension
from loushang.coding.extensions.manifest import parse_extension_manifest
from loushang.coding.extensions.policy import ExtensionPolicyDecision
```

Compatibility paths preserve import behavior and class identity. New
cross-product code should import the focused Harness owner directly.

## Dependency Direction

The target direction is:

```text
Coding extension/session adapter
  -> loushang.harness.extensions
  -> loushang.harness.resources / tools / contributions
  -> stable agent tool value primitives
```

`loushang.harness.extensions` must not import coding, method, work, TUI, AI,
provider, UI, session, or another product package. Coding must not reintroduce
parallel implementations of Harness-owned manifest, loader, registry,
dispatcher, resource contribution, or tool-wrapper behavior.

## Validation

The migration must prove:

- a product-neutral extension can register, load, resolve, dispatch, and
  contribute resources without Coding runtime objects or Coding vocabulary;
- failure containment, ordering, conflicts, source provenance, and input
  reduction remain deterministic;
- accepted Coding paths share Harness-owned object identity;
- Coding loader, API, runner, resource, and hook behavior remains compatible;
- Harness import boundaries and top-level export discipline remain intact;
- startup and the non-live test suite remain green.
