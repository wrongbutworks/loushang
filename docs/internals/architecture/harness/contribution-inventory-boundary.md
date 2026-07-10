# Harness Contribution Inventory Boundary

## Status

Status: accepted for `lane/harness`.

This document defines product-neutral contribution descriptors, inventory
indexing, and duplicate-key reporting as `loushang.harness.contributions`
responsibilities. Coding keeps extension discovery, manifest projection,
activation policy, permissions, runtime bindings, hooks, and command behavior.

## Decision

`loushang.harness.contributions` owns:

- `ContributionType` and its accepted extension-surface alias;
- `ContributionDescriptor` and `ExtensionSurfaceDescriptor`;
- `ContributionRegistry` and `ExtensionInventory`;
- `DuplicateContributionKeyError` and its extension-surface alias.

The generic and extension-shaped names refer to the same harness-owned classes.
This preserves existing class identity while giving non-coding consumers a
neutral import path.

The descriptor records contribution kind, name, opaque contributor identity,
source path, activation state, priority, permission requirements, diagnostics,
and metadata. Harness stores and indexes those values but does not interpret
them. In particular, `extension_id` remains an opaque contributor identifier;
it does not make Harness responsible for loading or trusting an extension.

The registry preserves insertion order and indexes contributions by type,
contributor, and `(type, name)` key. Multiple matching keys remain observable.
`get()` raises the duplicate-key error rather than choosing a winner. Product
adapters decide applicability, precedence, activation, override, and conflict
remediation.

## Coding Adapter

`loushang.coding.extensions.contributions` remains the Coding projection and
compatibility module. It owns:

- `surfaces_from_loaded_extension`;
- `contributions_from_loaded_extension`;
- manifest-to-contribution projection;
- runtime command, tool, and hook projection;
- Coding's choice of source metadata vocabulary.

The adapter imports the descriptor and registry classes from Harness. It may
read `LoadedExtension`-shaped objects, but Harness must not import
`LoadedExtension`, extension manifests, concrete tools, or Coding runtime
bindings.

## Compatibility

Accepted Coding imports remain available:

```python
from loushang.coding.extensions import ExtensionInventory
from loushang.coding.extensions import ExtensionSurfaceDescriptor
from loushang.coding.extensions.contributions import ContributionRegistry
```

These paths re-export the same harness-owned classes. Harness-owned classes
keep their harness `__module__`; compatibility paths preserve imports, not a
second implementation or Coding-owned class identity.

Existing constructor fields, registry methods, insertion ordering, duplicate
visibility, exception attributes, and error text remain unchanged. No broad
contribution symbols are added to top-level `loushang.harness.__all__`.

## Coding-Owned Behavior

This migration does not move or redesign:

- `LoadedExtension`, `ExtensionManifest`, or manifest parsing;
- extension search roots, loading, dependency validation, or policy decisions;
- permission enforcement, enablement defaults, or OEM override policy;
- concrete command, tool, prompt, skill, UI, or provider handlers;
- runtime bindings, extension contexts, hooks, middleware, or observers;
- session events, controller behavior, resource refresh, or diagnostics display;
- tool contribution resolution already owned by
  `loushang.harness.tools.contribution`.

Hook and observer contracts remain deferred until a product-neutral invocation
shape is proven. This inventory migration moves records and indexing only.

## Dependency Direction

The target direction is:

```text
coding extension loader / manifest and runtime projection
  -> loushang.harness.contributions
  -> loushang.harness.resources.diagnostics
```

`loushang.harness.contributions` must not import coding, method, work, TUI, AI,
agent runtime, provider, or product packages. It may depend on neutral Harness
resource diagnostics and Python standard-library value types.

## Validation

The migration must prove:

- descriptor values and frozen-record behavior remain unchanged;
- registry insertion order and all indexes remain unchanged;
- duplicate keys remain visible and `get()` preserves its exception contract;
- accepted Coding paths share Harness class identity;
- `LoadedExtension` projection produces Harness-owned records;
- Coding internal consumers import the Harness owner directly;
- extension runtime behavior and focused Coding tests remain unchanged;
- Harness import boundaries and top-level export discipline still pass.
