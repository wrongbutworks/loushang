# Coding To Harness Migration Inventory

## Status

This is an ownership inventory, not an implementation plan.

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

## Current Package Inventory

| Current module | Classification | Target / action |
| --- | --- | --- |
| `coding.commands` | Split candidate | `CommandDef` / `CommandEffect` value types already moved to `loushang.harness.commands`. Catalog, slash parsing, handlers, and session command execution stay in coding. |
| `coding.tools.types`, `schema`, `wrapper`, `factory`, `registry`, `authoring`, `normalize`, `protocol` | Split candidate | Move product-neutral tool definition, schema, wrapper, and registry mechanics to `loushang.harness.tools.core`. Keep coding defaults and product descriptions in coding. |
| `coding.tools.presentation`, `rendering`, `builtin_renderers`, `output_preview` | Split candidate | Move neutral presentation records and renderer registry mechanics to `loushang.harness.presentation`. Keep terminal/product rendering and coding-specific preview choices in coding. |
| `coding.tools.truncate` | Compatibility shim | Neutral line/byte truncation and shared limits live in `loushang.harness.workspace.truncation`. Coding keeps grep line limits, product wording, detail projection, and camelCase compatibility aliases. |
| `coding.tools.operations` | Compatibility shim | Operation protocols, sync-or-async result resolution, `LocalToolOperations`, and the default singleton live in `loushang.harness.workspace.operations`. Coding keeps normalization, Pi adapters, payload projection, and abort behavior. |
| `coding.tools.path_utils` | Split candidate | Configurable resolution, current-user expansion, canonical identity, Unicode normalization, and optional platform/user-input variants live in `loushang.harness.workspace.paths`. Coding keeps `@` syntax, default correction policy, public wrappers, and camelCase aliases. |
| `coding.tools.file_mutation_queue` | Compatibility shim | Canonical per-path mutation coordination lives in `loushang.harness.workspace.mutation_queue`. Coding paths re-export the harness functions and registry; the Pi-style camelCase alias stays coding-owned. |
| `coding.tools.read`, `ls`, `find`, `grep` | Split candidate | May become optional `loushang.harness.tools.workspace` read-only tools after policy boundaries are clear. Coding decides default activation. |
| `coding.tools.write`, `edit`, `edit_diff`, `bash`, `process`, `policy` | Split candidate | Operation, path, mutation, and exec substrate ownership is established. Destructive-operation policy, approval, result projection, tool cancellation, and default activation stay product-owned. |
| `coding.policy` | Split candidate | Move approval request/decision/resolver contracts and headless defaults to `loushang.harness.approval` or `loushang.harness.policy`. Keep coding risk rules and interactive UI integration in coding. |
| `coding.exec` | Compatibility shim | `ExecRequest`, `ExecResult`, output records, backend/update protocols, and `ExecService` live in `loushang.harness.workspace.exec`. Coding keeps the public compatibility path; policy, session cwd resolution, tool projection, and extension behavior remain product-owned. |
| `coding.diagnostics.types`, `coding.diagnostics.service` | Compatibility shim | Diagnostic vocabulary, records, queries, summaries, startup-check contracts, and the bounded in-memory engine live in `loushang.harness.diagnostics`. Coding paths re-export the same Harness-owned objects. |
| `coding.diagnostics.serialization`, `coding.diagnostics.problem_bridge`, concrete checks | Keep product | Keep camelCase payload projection, observability mapping, check selection, emission timing, remediation, session bridges, and CLI/TUI behavior in Coding. |
| `loushang.resource.frontmatter`, `coding.frontmatter` | Compatibility shim | Parser records, errors, and behavior live in `loushang.harness.resources.frontmatter`. Legacy paths preserve object identity; coding and method internal consumers use the harness owner. |
| `coding.source_info.SourceInfo`, `coding.extensions.types.SourceInfo` | Compatibility shim | `SourceInfo`, `SourceScope`, and `SourceOrigin` live in `loushang.harness.resources.source`. Coding command and extension paths preserve string and `Path` representations through the same harness class. Descriptor projection and executable identity remain in coding. |
| `coding.loader.ResourceDiagnostic`, `coding.loader.types.ResourceDiagnostic` | Compatibility shim | The focused resource record lives in `loushang.harness.resources.diagnostics`. Coding compatibility paths preserve object identity; resource checks, message selection, emission timing, and remediation remain product-owned. |
| Remaining `coding.loader.types` | Keep product | Prompt, skill, theme, and extension descriptors, source kinds, snapshots, roots, precedence, and merge decisions remain coding-owned. Generic merge primitives require a separate accepted boundary. |
| `coding.prompt.types` | Split candidate | Move only neutral prepared-prompt/trace contracts after they satisfy the neutrality evidence gate. Keep templates, preflight, and assembler policy in coding. |
| `coding.compaction.policy`, `coding.compaction.types.ContextUsageEstimate` | Compatibility shim | `CompactionBudget`, deterministic threshold accounting, and `ContextUsageEstimate` live in `loushang.harness.context`. Coding compatibility paths re-export the same Harness-owned objects. |
| Remaining `coding.compaction.types`, `coding.session.context_usage` | Split candidate | Keep message estimation, model adaptation, context usage snapshots, decisions, branch state, summarization, transcript rebuild, and Coding compaction policy in Coding. Context item refs and packing contracts require a later accepted boundary. |
| `coding.domain.types` | Split candidate | Use as input for future `loushang.harness.adapter` shapes. Generic request/result types must not contain first-class method fields; carry method/work refs as opaque metadata. |
| `coding.session` | Split candidate | Move only generic host lifecycle records such as idle/abort/dispose/queue snapshot if needed. Keep `AgentSession`, controllers, product event bus, resource watchers, command execution, and transcript behavior in coding. |
| `coding.event` | Keep product | Coding session event protocol and product projection stay coding. Harness may define separate neutral events later. |
| `coding.extensions.contributions` | Compatibility shim | Descriptor, registry, indexing, and duplicate-key contracts live in `loushang.harness.contributions`. Coding keeps `LoadedExtension` projection and re-exports the same harness-owned classes. |
| Remaining `coding.extensions` | Split candidate | Keep extension runtime, manifests, loaders, permissions, activation, command handlers, runtime bindings, and hooks in coding/OEM. Extract middleware or observer contracts only after a product-neutral invocation shape is proven. |
| `coding.bootstrap` | Keep product | Product assembly. It may call harness engines but should not move. |
| `coding.runtime` | Keep product | Coding session runtime host. It may adopt harness lifecycle protocols later. |
| `coding.ui` | Never harness | Product-owned TUI adapter and screen/controller state. Shared terminal primitives belong in `loushang.tui`, not harness. |
| `coding.mode` | Keep product | Transitional print/RPC mode adapters stay coding until channel is implemented. |
| `coding.cli` | Keep product | Product CLI. It may expose harness-backed behavior but remains coding-owned. |
| `coding.message`, `coding.store` | Keep product | Coding transcript entries, JSONL transforms, session persistence, and file locking stay coding-owned. |
| `coding.control` | Keep product | Auth, model registry, settings, and persistence stay outside harness. |
| `coding.package`, `coding.plugin`, `coding.resources`, `coding.skill` | Keep product | Coding package/plugin/resource semantics and materialization stay product-owned. |
| `coding.workflow` | Keep product | Coding workflows and workflow testing harnesses stay coding-owned. |
| `coding.platform` | Keep product | Clipboard, git, version, terminal/platform helpers stay product-owned unless a tiny neutral helper is separately justified. |
| `coding.work_shell` | Keep product | Coding adapter to `loushang.work`; do not move into harness or work. |

## Recommended Migration Order

### Slice 1: Approval, Tools Core, Presentation

Status: closed on `lane/harness`; see
[Slice 1 Closure Status](slice-1-status.md).

Purpose: validate the OEM/extension contribution model without touching agent
loop, TUI render loop, or AI provider behavior.

Move only:

- neutral tool definition/schema/registry contracts;
- neutral presentation records and renderer registry contracts;
- approval request/decision/resolver protocols and headless defaults.

Keep in coding:

- concrete tools;
- default tool packs;
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

Slice 2B may move only neutral execution context descriptors after a Coding
adapter and an independent contract probe validate the shared shape. Keep
`ToolContext`, `ExtensionRuntimeBindings`, `ToolController`, model and
diagnostics fields, active-tool policy, prompt rebuilds, session mutation, and
concrete execution in coding.

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

Normalization, Pi compatibility adapters, tool cancellation, path resolution,
mutation queueing, policy, AI content projection, renderers, and concrete tools
remain in coding.

### Workspace Paths And Mutation

Status: workspace path and mutation implementation complete for integration into
`lane/harness`; see
[Workspace Path And Mutation Boundary](workspace-path-mutation-boundary.md).

Harness now owns configurable path resolution, current-user expansion,
canonical absolute identity, opt-in Unicode/platform input helpers, and
canonical per-path mutation coordination. Coding compatibility paths re-export
the harness queue functions and registry.

Coding keeps `@` input syntax, the default path-correction configuration,
public path wrappers, camelCase aliases, workspace root and sandbox policy,
approval, and concrete tool behavior.

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
identity, product resource descriptors, search roots, precedence, merge policy,
resource checks, diagnostic emission policy, and remediation text remain
product-owned.

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

Purpose: let future products share idle/abort/dispose/queue contracts.

Move minimal lifecycle protocols only after the first product-facing host shape
is clear. Do not move `AgentSession` wholesale.

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
- Do not move concrete coding tools as part of a tool-core slice.
- Do not move prompt templates, AGENTS.md policy, slash semantics, or command
  handlers.
- Do not add broad top-level packages for workspace, context, memory, or
  session.
- Do not add new top-level harness exports unless they are intentionally public.

Each implementation slice should update this inventory if the final ownership
differs from the current classification.
