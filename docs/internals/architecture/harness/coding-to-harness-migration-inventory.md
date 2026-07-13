# Coding To Harness Migration Inventory

## Status

This is an ownership inventory and the execution order for the accelerated
runtime consolidation.

It records current ownership and the remaining action for modules migrating
from `loushang.coding` into `loushang.harness`.

## Classification

| Category | Meaning |
| --- | --- |
| Move candidate | Product-neutral substrate that can likely move to harness. |
| Split candidate | Contains shared mechanism and coding policy; only the shared part may move. |
| Compatibility shim | Harness owns the implementation; an accepted legacy path re-exports that surface. |
| Keep product | Coding-specific assembly, policy, storage, UI, or workflow. |
| Never harness | Explicitly outside harness by subsystem boundary. |

Classification defaults to Harness. `Keep product` entries require a named
product-kernel reason; historical location or lack of a second consumer is not
sufficient.

## Current Package Inventory

| Current module | Classification | Target / action |
| --- | --- | --- |
| `coding.commands` | Split candidate | `CommandDef` / `CommandEffect` value types already moved to `loushang.harness.commands`. Catalog, slash parsing, handlers, and session command execution stay in coding. |
| `coding.tools.types`, `schema`, `wrapper`, `registry`, `authoring`, `normalize` | Compatibility shim | Reusable tool definition, schema, normalization, wrapping, and registry mechanics live under `loushang.harness.tools`; Coding preserves accepted imports. |
| `coding.tools.factory`, `coding.tools.builtins` | Split candidate | Harness owns reusable workspace-tool construction. Coding keeps default pack membership, activation, policy injection, and product-tuned metadata. |
| `coding.tools.presentation`, `rendering`, `builtin_renderers`, `output_preview` | Split candidate | Harness owns neutral presentation records and reusable workspace renderers/previews. Keep terminal/product projections and Coding protocol details in Coding. |
| `coding.tools.truncate` | Compatibility shim | Neutral line/byte truncation and shared limits live in `loushang.harness.workspace.truncation`. Coding keeps grep line limits, product wording, detail projection, and camelCase compatibility aliases. |
| `coding.tools.operations` | Compatibility shim | Operation protocols, sync-or-async result resolution, `LocalToolOperations`, and the default singleton live in `loushang.harness.workspace.operations`. Coding keeps normalization, Pi adapters, payload projection, and abort behavior. |
| `coding.tools.path_utils` | Split candidate | Configurable resolution, current-user expansion, canonical identity, Unicode normalization, and optional platform/user-input variants live in `loushang.harness.workspace.paths`. Coding keeps `@` syntax, default correction policy, public wrappers, and camelCase aliases. |
| `coding.tools.file_mutation_queue` | Compatibility shim | Canonical per-path mutation coordination lives in `loushang.harness.workspace.mutation_queue`. Coding paths re-export the harness functions and registry; the Pi-style camelCase alias stays coding-owned. |
| `coding.tools.read`, `ls`, `find`, `grep`, `write`, `edit`, `edit_diff`, `bash`, `process`, `ignore`, `external_tools` | Compatibility shim | Reusable implementations live in `loushang.harness.tools.workspace`. Coding injects product metadata, policy/approval, activation, and compatibility projections. |
| `coding.tools.policy` | Compatibility shim | Neutral policy-enforcement plumbing accepts an injected evaluator and Harness approval resolver. Coding retains risk classification and concrete `PolicyEngine` defaults. |
| `coding.policy` | Split candidate | Move approval request/decision/resolver contracts and headless defaults to `loushang.harness.approval` or `loushang.harness.policy`. Keep coding risk rules and interactive UI integration in coding. |
| `coding.exec` | Compatibility shim | `ExecRequest`, `ExecResult`, output records, backend/update protocols, and `ExecService` live in `loushang.harness.workspace.exec`. Coding keeps the public compatibility path; policy, session cwd resolution, tool projection, and extension behavior remain product-owned. |
| `coding.diagnostics.types`, `coding.diagnostics.service` | Compatibility shim | Diagnostic vocabulary, records, queries, summaries, startup-check contracts, and the bounded in-memory engine live in `loushang.harness.diagnostics`. Coding paths re-export the same Harness-owned objects. |
| `coding.diagnostics.serialization`, `coding.diagnostics.problem_bridge`, concrete checks | Keep product | Keep camelCase payload projection, observability mapping, check selection, emission timing, remediation, session bridges, and CLI/TUI behavior in Coding. |
| `loushang.resource.frontmatter`, `coding.frontmatter` | Compatibility shim | Parser records, errors, and behavior live in `loushang.harness.resources.frontmatter`. Legacy paths preserve object identity; coding and method internal consumers use the harness owner. |
| `coding.source_info.SourceInfo`, `coding.extensions.types.SourceInfo` | Compatibility shim | `SourceInfo`, `SourceScope`, and `SourceOrigin` live in `loushang.harness.resources.source`. Coding command and extension paths preserve string and `Path` representations through the same harness class. Descriptor projection and executable identity remain in coding. |
| `coding.loader.ResourceDiagnostic`, `coding.loader.types.ResourceDiagnostic` | Compatibility shim | The focused resource record lives in `loushang.harness.resources.diagnostics`. Coding compatibility paths preserve object identity; resource checks, message selection, emission timing, and remediation remain product-owned. |
| Remaining `coding.loader.types` | Move candidate | Product-neutral prompt, skill, theme, and extension descriptors, source kinds, snapshots, bundles, and merge decisions should move under `loushang.harness.resources`. Coding keeps only product projection and compatibility aliases. |
| `coding.prompt.types` | Split candidate | Move only neutral prepared-prompt/trace contracts after they satisfy the neutrality evidence gate. Keep templates, preflight, and assembler policy in coding. |
| `coding.compaction.policy`, `coding.compaction.types.ContextUsageEstimate` | Compatibility shim | `CompactionBudget`, deterministic threshold accounting, and `ContextUsageEstimate` live in `loushang.harness.context`. Coding compatibility paths re-export the same Harness-owned objects. |
| Remaining `coding.compaction.types`, `coding.session.context_usage` | Split candidate | Keep message estimation, model adaptation, context usage snapshots, decisions, branch state, summarization, transcript rebuild, and Coding compaction policy in Coding. Context item refs and packing contracts require a later accepted boundary. |
| `coding.domain.types` | Split candidate | Use as input for future `loushang.harness.adapter` shapes. Generic request/result types must not contain first-class method fields; carry method/work refs as opaque metadata. |
| `coding.session.types.RunState` | Compatibility shim | `RunState` lives in `loushang.harness.host.types`; Coding preserves the accepted session import with the same class identity. |
| `coding.session.queue_controller`, `coding.session.session_event_bus` | Split candidate | Queue snapshots, `HostInputQueue`, and `OrderedEventBus` live in `loushang.harness.host`. Coding keeps queue input/Agent delivery, logs, product queue events, and its specialized session event bus. |
| `coding.session.AgentSession`, controllers, `coding.runtime.AgentSessionRuntime` | Split candidate | `AgentSession` delegates prompt/continue/abort/idle/dispose coordination to `HostRuntime`. Keep product controllers, event schema, resource watchers, commands, transcript behavior, session replacement, tree/fork/import, and store policy in Coding. |
| `coding.event` | Keep product | Coding session event protocol and product projection stay coding. Harness may define separate neutral events later. |
| `coding.extensions.contributions` | Compatibility shim | Descriptor, registry, indexing, and duplicate-key contracts live in `loushang.harness.contributions`. Coding keeps `LoadedExtension` projection and re-exports the same harness-owned classes. |
| Remaining `coding.extensions` | Split candidate | Keep extension runtime, manifests, loaders, permissions, activation, command handlers, runtime bindings, and hooks in coding/OEM. Extract middleware or observer contracts only after a product-neutral invocation shape is proven. |
| `coding.bootstrap` | Keep product | Product assembly. It may call harness engines but should not move. |
| `coding.runtime` | Keep product | Coding session runtime host. It may adopt harness lifecycle protocols later. |
| `coding.ui` | Never harness | Product-owned TUI adapter and screen/controller state. Shared terminal primitives belong in `loushang.tui`, not harness. |
| `coding.mode` | Keep product | Transitional print/RPC mode adapters stay coding until channel is implemented. |
| `coding.cli` | Keep product | Product CLI. It may expose harness-backed behavior but remains coding-owned. |
| `coding.message`, `coding.store` | Keep product | Coding transcript entries, JSONL transforms, session persistence, and file locking stay coding-owned. |
| `coding.control` | Keep product | Frozen during runtime consolidation: auth resolution, model registry, settings, provider registration, credential handling, and selection persistence stay outside Harness. Harness receives already-resolved runtime dependencies and never stores credentials. Revisit ownership separately after consolidation. |
| `coding.package`, `coding.plugin`, `coding.resources`, `coding.skill` | Split candidate | Move package source/manifest/materialization, standard roots/layout, registry/resolver, discovery, and skill-loading mechanisms under `loushang.harness.resources`. Coding keeps built-in content, convention activation, additional roots, trust/approval policy, settings, CLI projection, and compatibility paths. |
| `coding.workflow` | Keep product | Coding workflows and workflow testing harnesses stay coding-owned. |
| `coding.platform` | Keep product | Clipboard, git, version, terminal/platform helpers stay product-owned unless a tiny neutral helper is separately justified. |
| `coding.work_shell` | Keep product | Coding adapter to `loushang.work`; do not move into harness or work. |

## Recommended Migration Order

### Slice 1: Approval, Tools Core, Presentation

Status: closed on `lane/harness`; see
[Slice 1 Closure Status](slice-1-status.md).

Purpose: validate the OEM/extension contribution model without touching agent
loop, TUI render loop, or AI provider behavior.

The original contract-only move is complete. Runtime consolidation now extends
this ownership to reusable concrete tools while preserving the same product
policy boundary.

Harness owns:

- neutral tool definition/schema/registry contracts;
- neutral presentation records and renderer registry contracts;
- approval request/decision/resolver protocols and headless defaults.
- reusable workspace tool definitions, execution helpers, and neutral
  renderers.

Keep in Coding:

- default tool packs;
- product-tuned tool metadata;
- risk classification and approval defaults;
- interactive approval UI;
- command handlers;
- session controllers.

### Slice 2: Execution Context And Runtime Contributions

Status: Slice 2A implementation complete for runtime tool contribution adapter
verification. Slice 2B is eligible under the neutrality evidence gate but is
not yet implemented; see
[Slice 2 Execution Context Design](slice-2-execution-context-design.md).

Purpose: define the neutral live execution/context and runtime contribution
boundary before migrating dynamic extension registration or live tool execution
context.

Slice 2A routes coding runtime extension tool registration through neutral
`ToolContribution` projection and resolver verification. Duplicate overwrite,
active-tool policy, prompt rebuilds, diagnostics mapping, session mutation, and
concrete execution remain coding-owned.

The reusable `ToolContext` now lives with the workspace tool pack after a
Coding adapter and independent contract probe validated its shape. Keep
`ExtensionRuntimeBindings`, `ToolController`, active-tool policy, prompt
rebuilds, session mutation, and product model/diagnostic interpretation in
Coding.

### Workspace Execution

Status: workspace execution implementation complete for integration into
`lane/harness`; see
[Workspace Execution Boundary](workspace-execution-boundary.md).

Purpose: separate process/file operation mechanics from coding policy.

Harness now owns neutral bounded-output truncation, exec request/result records,
backend/update protocols, and local subprocess execution. Coding compatibility
paths re-export those harness objects.

Command allow/deny policy, workspace root and relative cwd selection, extension
runtime behavior, bash result projection, and product explanation text remain
in coding. This migration does not introduce a neutral execution context or
by itself satisfy the neutrality evidence gate for Slice 2B.

### Workspace Operations

Status: workspace operation implementation complete for integration into
`lane/harness`; see
[Workspace Operation Boundary](workspace-operation-boundary.md).

Harness now owns the neutral operation protocols, sync-or-async result
resolution, local filesystem backend, and default singleton. Coding public
paths re-export those same objects.

The later workspace tool-pack migration now owns normalization, compatibility
operation adapters, cancellation, reusable result projection, renderers, and
concrete tools. Product policy and activation remain in Coding.

### Workspace Paths And Mutation

Status: workspace path and mutation implementation complete for integration into
`lane/harness`; see
[Workspace Path And Mutation Boundary](workspace-path-mutation-boundary.md).

Harness now owns configurable path resolution, current-user expansion,
canonical absolute identity, opt-in Unicode/platform input helpers, and
canonical per-path mutation coordination. Coding compatibility paths re-export
the harness queue functions and registry.

The workspace tool pack now carries the accepted `@`, `~`, Unicode-space,
macOS screenshot, normalization, and user-input path compatibility wrappers so
all products can opt into the same input behavior. Allowed roots, sandbox
policy, approval defaults, and activation remain product-owned.

### Workspace Tool Pack

Status: reusable concrete workspace tools implemented for integration into
`lane/harness`; see [Workspace Tool Pack Boundary](workspace-tool-pack-boundary.md).

Harness owns the reusable read, list, find, grep, write, edit, and bash tool
definitions plus their context, normalization, operation adapters, process,
external-tool, ignore, diff, preview, truncation-projection, and renderer
support. Coding implementation modules preserve accepted imports as aliases.

Coding retains builtin pack membership and activation, product descriptions,
`PolicyEngine` risk rules, approval defaults and UI, workspace root policy,
commands, session projection, and presentation surfaces.

### Diagnostics Core

Status: diagnostics core implementation complete for integration into
`lane/harness`; see
[Diagnostics Core Boundary](diagnostics-core-boundary.md).

Harness now owns diagnostic vocabulary, records, queries, summaries,
startup-check contracts, bounded retention, fingerprinting, duplicate
aggregation, filtering, error reports, resource/exception normalization, and
caller-supplied startup-check execution.

Coding compatibility paths re-export the Harness objects. Coding keeps
serialization, observability problem mapping, concrete checks, emission policy,
remediation, session projection, exports, and CLI/RPC/TUI presentation.

### Slice 3: Resources And Source Metadata

Status: frontmatter parsing implementation complete; resource provenance implementation complete
for integration into `lane/harness`; see
[Resource Frontmatter Boundary](resource-frontmatter-boundary.md) and
[Resource Provenance Boundary](resource-provenance-boundary.md).

Purpose: avoid expanding `loushang.resource` as a broad top-level package.

Frontmatter parsing now lives in `loushang.harness.resources.frontmatter`.
`loushang.resource.frontmatter` and `loushang.coding.frontmatter` are
compatibility shims, while coding and method internal consumers import the
harness owner directly.

Source metadata now lives in `loushang.harness.resources.source`, preserving
adapter-selected string or `Path` representations. The neutral resource
diagnostic record lives in `loushang.harness.resources.diagnostics`.
Accepted coding paths re-export the harness classes, while coding executable
identity, product content, convention activation, additional/override roots,
trust policy, resource checks, diagnostic emission policy, and remediation text
remain product-owned. Platform roots, standard conventions, scope/precedence
presets, descriptors, discovery, merging, and package mechanisms are assigned
to Harness by the later
[Platform Resource Layout Boundary](platform-resource-layout-boundary.md).

### Resource And Package Runtime

Status: platform resource layout ownership accepted; implementation pending.
See [Platform Resource Layout Boundary](platform-resource-layout-boundary.md).

Harness will own `LOUSHANG_HOME`/`~/.loushang`, the standard
`<workspace>/.loushang` layout, shared resource directories, scope vocabulary,
the overridable precedence preset, reusable `AGENTS.md` discovery, optional
compatibility conventions, and built-in/package loading mechanisms.

Coding will register `loushang.coding.resources`, select enabled conventions,
add product roots and filters, apply trust/approval policy, and project the
Harness resource snapshot into Coding prompts, sessions, commands, and UI.

### Slice 4: Context

Status: context budget and accounting implementation complete for integration
into `lane/harness`; item refs, bundles, diagnostics, and packing contracts
remain deferred; see
[Context Budget And Accounting Boundary](context-budget-accounting-boundary.md).

Purpose: define shared context budget and packing contracts without moving
coding compaction policy.

`CompactionBudget`, deterministic percentage/reserve threshold accounting, and
the `ContextUsageEstimate` result record now live under
`loushang.harness.context`. Coding compatibility paths re-export the Harness
owners, while Coding continues to estimate message tokens, adapt model context
windows, build usage snapshots, and decide whether to compact.

Context item refs, bundles, diagnostics, and general packing contracts remain
deferred. Transcript summarization, branch summaries, product salience rules,
and transcript rebuild semantics remain Coding-owned.

### Slice 5: Host And Lifecycle

Status: host runtime core implementation complete for integration into
`lane/harness`; see [Host Runtime Boundary](host-runtime-boundary.md).

Purpose: let future products share idle/abort/dispose/queue contracts.

Harness now owns host status/snapshots, driver-delegating lifecycle
coordination, generic steering/follow-up queue ledger mechanics, and ordered
event dispatch. Coding uses those mechanisms while retaining `AgentSession`,
its product controllers and event schema, session persistence/replacement, and
product prompt text, resource activation/projection, extension policy, and UI
semantics.

The independent reference driver and neutral queue/event fixtures satisfy the
neutrality evidence gate without moving `AgentSession` wholesale or creating a
second agent loop.

### Slice 6: Contribution Model

Status: contribution inventory implementation complete for integration into
`lane/harness`; middleware and observer contracts remain deferred; see
[Contribution Inventory Boundary](contribution-inventory-boundary.md).

Purpose: support OEM and extension contributions across products.

Contribution descriptors, registry indexing, and duplicate-key reporting now
live in `loushang.harness.contributions`. Coding compatibility paths re-export
the same harness-owned classes, while `surfaces_from_loaded_extension` remains
the product projection adapter.

Extension manifests, loaders, activation and permission policy, concrete
handlers, runtime bindings, hooks, and session events remain coding-owned.
Middleware and observer contracts should move only after a Coding adapter and
an independent contract probe prove a neutral invocation shape.

## Guardrails

- Do not add `loushang.harness` imports from `loushang.agent`.
- Do not add product imports from `loushang.harness`.
- Default reusable concrete implementations to Harness; keep only
  domain-specific tool semantics in products.
- Keep `coding.control` frozen during runtime consolidation. Do not route auth,
  credentials, model registries, provider registration, or persisted model
  selection through Harness.
- Do not move product prompt templates/assembly, slash semantics, or command
  handlers. Reusable `AGENTS.md` discovery belongs to Harness; Product owns
  convention activation and prompt projection.
- Do not add broad top-level packages for workspace, context, memory, or
  session.
- Do not add new top-level harness exports unless they are intentionally public.

Each implementation slice should update this inventory if the final ownership
differs from the current classification.
