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
| `coding.tools.read`, `ls`, `find`, `grep` | Split candidate | May become optional `loushang.harness.tools.workspace` read-only tools after policy boundaries are clear. Coding decides default activation. |
| `coding.tools.write`, `edit`, `edit_diff`, `bash`, `process`, `file_mutation_queue`, `policy` | Split candidate | Move only neutral workspace operation/exec request-result shapes and staging mechanics. Destructive operation policy, approval, and default activation stay product-owned. |
| `coding.policy` | Split candidate | Move approval request/decision/resolver contracts and headless defaults to `loushang.harness.approval` or `loushang.harness.policy`. Keep coding risk rules and interactive UI integration in coding. |
| `coding.exec` | Compatibility shim | `ExecRequest`, `ExecResult`, output records, backend/update protocols, and `ExecService` live in `loushang.harness.workspace.exec`. Coding keeps the public compatibility path; policy, session cwd resolution, tool projection, and extension behavior remain product-owned. |
| `coding.diagnostics` | Split candidate | Move neutral diagnostic record/status/query types to `loushang.harness.diagnostics`. Keep coding health checks and remediation text in coding. |
| `loushang.resource.frontmatter`, `coding.frontmatter` | Compatibility shim | Parser records, errors, and behavior live in `loushang.harness.resources.frontmatter`. Legacy paths preserve object identity; coding and method internal consumers use the harness owner. |
| `coding.source_info.SourceInfo`, `coding.extensions.types.SourceInfo` | Compatibility shim | `SourceInfo`, `SourceScope`, and `SourceOrigin` live in `loushang.harness.resources.source`. Coding command and extension paths preserve string and `Path` representations through the same harness class. Descriptor projection and executable identity remain in coding. |
| `coding.loader.ResourceDiagnostic`, `coding.loader.types.ResourceDiagnostic` | Compatibility shim | The neutral record lives in `loushang.harness.resources.diagnostics`. Coding compatibility paths preserve object identity; diagnostic services, messages, phases, and recording policy remain product-owned. |
| Remaining `coding.loader.types` | Keep product | Prompt, skill, theme, and extension descriptors, source kinds, snapshots, roots, precedence, and merge decisions remain coding-owned. Generic merge primitives require a separate accepted boundary. |
| `coding.prompt.types` | Split candidate | Move only neutral prepared-prompt/trace contracts if a second product needs them. Keep templates, preflight, and assembler policy in coding. |
| `coding.compaction.types`, `coding.session.context_usage` | Split candidate | Move context budget/usage/accounting contracts to `loushang.harness.context`. Keep summarization services, transcript rebuild, and coding compaction policy in coding. |
| `coding.domain.types` | Split candidate | Use as input for future `loushang.harness.adapter` shapes. Generic request/result types must not contain first-class method fields; carry method/work refs as opaque metadata. |
| `coding.session` | Split candidate | Move only generic host lifecycle records such as idle/abort/dispose/queue snapshot if needed. Keep `AgentSession`, controllers, product event bus, resource watchers, command execution, and transcript behavior in coding. |
| `coding.event` | Keep product | Coding session event protocol and product projection stay coding. Harness may define separate neutral events later. |
| `coding.extensions` | Split candidate | Later extract neutral contribution descriptors and hook/middleware contracts if validated by OEM/product needs. Keep extension runtime, manifest policy, permissions, and product activation in coding/OEM. |
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
verification. Slice 2B is gated pending a second product consumer; see
[Slice 2 Execution Context Design](slice-2-execution-context-design.md).

Purpose: define the neutral live execution/context and runtime contribution
boundary before migrating dynamic extension registration or live tool execution
context.

Slice 2A routes coding runtime extension tool registration through neutral
`ToolContribution` projection and resolver verification. Duplicate overwrite,
active-tool policy, prompt rebuilds, diagnostics mapping, session mutation, and
concrete execution remain coding-owned.

Slice 2B may move only neutral execution context descriptors after a second
product consumer validates the shared shape. Keep `ToolContext`,
`ExtensionRuntimeBindings`, `ToolController`, model and diagnostics fields,
active-tool policy, prompt rebuilds, session mutation, and concrete execution
in coding.

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
satisfy the separate second-product gate for Slice 2B.

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
diagnostic services, and remediation text remain product-owned.

### Slice 4: Context

Purpose: define shared context budget and packing contracts without moving
coding compaction policy.

Move usage/budget/ref contracts. Keep transcript summarization, branch summaries,
and product salience rules in coding.

### Slice 5: Host And Lifecycle

Purpose: let future products share idle/abort/dispose/queue contracts.

Move minimal lifecycle protocols only after the first product-facing host shape
is clear. Do not move `AgentSession` wholesale.

### Slice 6: Contribution Model

Purpose: support OEM and extension contributions across products.

Move contribution records and middleware/observer contracts only after tools,
approval, and presentation have proven the shape.

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
