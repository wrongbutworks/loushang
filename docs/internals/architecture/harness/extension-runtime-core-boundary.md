# Harness Extension Runtime Core Boundary

## Status

Status: implementation complete, including the follow-on control-plane routing
closure, for integration into `lane/harness`.

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
- stable dependency-aware route planning, failure-contained observer dispatch,
  opaque-state reducers/interceptors, and sequential input transformation;
- resource contribution execution and `promptPaths`, `skillPaths`, and
  `themePaths` normalization;
- registered-tool execution wrapping with an injected context factory.
- `ExtensionRuntime`, which composes already-loaded extensions into the common
  registry, route plan, dispatcher, resource discovery, command/flag/shortcut,
  tool, renderer, diagnostic, and extension-visibility surface.
- `ExtensionSessionRuntime`, which applies the existing lifecycle coordinator
  to a bound Product session's runtime bindings, start/refresh events, reload
  resource refresh, diagnostics, and context invalidation.

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
- the `ExtensionRunner` adapter and Product reducers that connect the
  Harness-owned `ExtensionRuntime` to Coding session, prompt, context, and
  Agent result types.

`loushang.coding.extensions.loader.ExtensionLoader` now only injects the Coding
API factory, Coding permission policy, and legacy event names into the Harness
loader. The Coding `manifest`, `events`, `contributions`, and `wrapper` modules
are compatibility re-exports. Shared records imported through
`coding.extensions.types` are the same Harness-owned objects.

## Runtime Composition

`ExtensionRuntime` starts after a Product has loaded, trusted, and selected
extensions. It owns the mechanical composition of the standard extension
surfaces: registration resolution, dispatch routing, resource contribution
execution, context-factory based tool wrapping, and diagnostic/visibility
projection. Its two context factories are explicit injection points: the
per-extension factory supports dispatched hooks and tools, while the optional
resource factory preserves a Product's resource-refresh context semantics.

The runtime has no Product session state and does not interpret model choices,
approval outcomes, UI state, or Agent-specific hook results. Coding's
`ExtensionRunner` only performs descriptor loading with Coding API injection,
binds Coding's typed runtime context, maps legacy event objects and session
decisions, and supplies the Coding error callback. It must not reimplement
registry snapshots, resource discovery, generic input/event dispatch, command
completion, flag state, or extension visibility serialization.

The optional Agent session profile owns `ExtensionInputRuntime`,
`ExtensionAgentHookRuntime`, and `ExtensionAgentEventRuntime`. They deliver
standard extension-originated input, compose Agent context/tool hooks, and
mirror Agent lifecycle facts without importing a Product. A Product still
supplies its extension API, runtime binding factory, session replacement/fork
semantics, diagnostics wording, and transport/UI projection.

These session-profile modules may depend on stable Agent/AI message and tool
value contracts because they operate a live Agent session. They are separate
from the neutral extension core: they must not import Coding, a Product,
provider execution, authentication, model resolution, or UI implementation.

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
| **Interceptor** | Handlers form a pipeline; each sees the output of the previous | Step failure is governed by `on_error` (skip / fail_chain) | hook, policy |
| **Replacement** | Only one active provider per slot; the first active provider in resolved order wins and conflicts are diagnosed | Failure propagates to the Product-selected fallback; there is no chain to skip | approval, model_provider, channel adapter, storage backend |

Harness owns the scheduling categories. Product adapters and OEMs decide
which extensions are active in each category and inject policy for each slot.

## Extension Routing And Ordering

Extension execution is compiled into an event-scoped route plan. The descriptor
and registered-handler records carry explicit ordering and error-policy fields:

```python
@dataclass(frozen=True)
class ExtensionSurfaceDescriptor:
    type: ExtensionSurfaceType
    name: str
    extension_id: str
    source_path: Path
    active: bool = True
    priority: int = 0
    permission_requirements: tuple[str, ...] = ()
    diagnostics: tuple[ResourceDiagnostic, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)
    # Appended to preserve the legacy positional constructor contract.
    after: tuple[str, ...] = ()       # canonical route/extension references
    before: tuple[str, ...] = ()
    on_error: Literal["skip", "fail_chain"] = "skip"
```

Routes use stable topological ordering with priority and registration order as
tie-breakers. When `after` or `before` constraints create a cycle, Harness
preserves edges outside the strongly connected component, emits a diagnostic,
and uses priority plus registration order inside the conflicting component.
Legacy `LoadedExtension.hooks` values synthesize registrations in existing
extension and handler order.

## ExtensionSurfaceType Gaps

The control-plane closure adds executable `policy` and `approval` contribution
paths. Method and Channel surfaces remain owned by their respective layers and
are not added as unprocessed Harness vocabulary:

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
    # implemented control-plane contributions
    "policy",          # inject a PolicyEvaluator chain member
    "approval",        # select an ApprovalResolver replacement
]
```

Runtime values use focused control-contribution records rather than mutable
descriptor metadata. Policy contributions compose in resolved route order;
approval is an exclusive replacement slot with deterministic conflict
diagnostics. Policy contributions fail the chain by default; advisory skip
semantics must be explicit. The selected approval replacement validates its
result and reports route/source diagnostics before propagating failures, while
cancellation remains undiagnosed. Product/OEM code supplies activation and
trust decisions before composition; Harness applies inactive filtering
consistently across executable surfaces. See the
[Control Plane Runtime Boundary](control-plane-runtime-boundary.md) for the
runtime contracts and compatibility matrix.

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
  -> loushang.harness.extensions.runtime
  -> loushang.harness.extensions
  -> loushang.harness.resources / tools / contributions
  -> stable agent tool value primitives
```

`loushang.harness.extensions` must not import coding, method, work, TUI, AI,
provider, UI, session, or another product package. Coding must not reintroduce
parallel implementations of Harness-owned manifest, loader, registry,
dispatcher, resource contribution, runtime composition, or tool-wrapper
behavior.

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
