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
- typed Coding specialization and product callback injection for the
  Harness-owned runtime binding/context mechanisms defined by the
  [Product Runtime Core Boundary](product-runtime-core-boundary.md);
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

## Extension Injection Categories

Extensions fall into three categories with different execution semantics:

| Category | Behaviour | Failure strategy | Examples |
| --- | --- | --- | --- |
| **Contribution** | All declarations are aggregated; each runs independently | One failure produces a diagnostic; others continue | tool, command, skill, method, prompt, resource_root |
| **Interceptor** | Handlers form a pipeline; each sees the output of the previous | Step failure is governed by `on_error` (skip / fail_chain) | hook, policy, approval |
| **Replacement** | Only one active provider per slot; later registrations replace earlier ones | Not applicable — only one runs | model_provider, channel adapter, storage backend |

Harness owns the scheduling categories. Product adapters and OEMs decide
which extensions are active in each category and inject policy for each slot.

## Extension Routing And Ordering

Current extension execution uses insertion order. The descriptor already
carries `priority` and should grow explicit ordering and error-policy fields:

```python
@dataclass(frozen=True)
class ExtensionSurfaceDescriptor:
    type: ExtensionSurfaceType
    name: str
    extension_id: str
    source_path: Path
    active: bool = True
    priority: int = 0
    after: tuple[str, ...] = ()       # run after these surfaces (by name or extension_id)
    before: tuple[str, ...] = ()      # run before these surfaces
    on_error: Literal["skip", "fail_chain"] = "skip"
    permission_requirements: tuple[str, ...] = ()
    diagnostics: tuple[ResourceDiagnostic, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)
```

When `after` or `before` constraints create a cycle, harness emits a diagnostic
and falls back to insertion order for the conflicting set.

## ExtensionSurfaceType Gaps

The current `ExtensionSurfaceType` literal covers nine surfaces. Several
surface types that OEM products need are not yet defined:

```python
ExtensionSurfaceType = Literal[
    # existing
    "command",
    "tool",
    "prompt",
    "skill",
    "hook",
    "model_provider",
    "ui",
    "autocomplete",
    "resource_root",
    # proposed — each requires a harness processing path
    "policy",          # inject a PolicyEvaluator
    "approval",        # inject an ApprovalResolver
    "method",          # register a method resource
    "channel",         # register a channel adapter
]
```

Each new surface type requires:
1. a `from_surface()` factory in the corresponding Harness module that loads
   and validates the extension's source;
2. an injection path from `ExtensionInventory` to the Harness engine that
   consumes it (e.g. host runtime, policy broker, channel registry);
3. contract tests proving an OEM can ship the surface in a plugin without
   importing product packages.

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
