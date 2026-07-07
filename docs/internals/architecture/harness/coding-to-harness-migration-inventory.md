# Coding To Harness Migration Inventory

## Status

This is an ownership inventory, not an implementation plan.

It records how current `loushang.coding` modules should be classified before
code moves into `loushang.harness`.

## Classification

| Category | Meaning |
| --- | --- |
| Move candidate | Product-neutral substrate that can likely move to harness. |
| Split candidate | Contains shared mechanism and coding policy; only the shared part may move. |
| Keep product | Coding-specific assembly, policy, storage, UI, or workflow. |
| Never harness | Explicitly outside harness by subsystem boundary. |

## Current Package Inventory

| Current module | Classification | Target / action |
| --- | --- | --- |
| `coding.commands` | Split candidate | `CommandDef` / `CommandEffect` value types already moved to `loushang.harness.commands`. Catalog, slash parsing, handlers, and session command execution stay in coding. |
| `coding.tools.types`, `schema`, `wrapper`, `factory`, `registry`, `authoring`, `normalize`, `protocol` | Split candidate | Move product-neutral tool definition, schema, wrapper, and registry mechanics to `loushang.harness.tools.core`. Keep coding defaults and product descriptions in coding. |
| `coding.tools.presentation`, `rendering`, `builtin_renderers`, `output_preview`, `truncate` | Split candidate | Move neutral presentation records and renderer registry mechanics to `loushang.harness.presentation`. Keep terminal/product rendering and coding-specific preview choices in coding. |
| `coding.tools.read`, `ls`, `find`, `grep` | Split candidate | May become optional `loushang.harness.tools.workspace` read-only tools after policy boundaries are clear. Coding decides default activation. |
| `coding.tools.write`, `edit`, `edit_diff`, `bash`, `process`, `file_mutation_queue`, `policy` | Split candidate | Move only neutral workspace operation/exec request-result shapes and staging mechanics. Destructive operation policy, approval, and default activation stay product-owned. |
| `coding.policy` | Split candidate | Move approval request/decision/resolver contracts and headless defaults to `loushang.harness.approval` or `loushang.harness.policy`. Keep coding risk rules and interactive UI integration in coding. |
| `coding.exec` | Split candidate | Move neutral exec request/result/service protocol to `loushang.harness.workspace.exec`. Keep product policy and CLI-facing behavior in coding. |
| `coding.diagnostics` | Split candidate | Move neutral diagnostic record/status/query types to `loushang.harness.diagnostics`. Keep coding health checks and remediation text in coding. |
| `coding.loader.types`, `coding.source_info`, `loushang.resource.frontmatter` | Split candidate | Move generic resource/source metadata/frontmatter pieces to `loushang.harness.resources`. Keep prompt/theme/skill loading policy in coding. |
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

### Slice 2: Workspace Exec

Purpose: separate process/file operation mechanics from coding policy.

Move only neutral request/result/protocol shapes. Keep command allow/deny policy,
workspace root selection, and product explanation text in coding.

### Slice 3: Resources And Source Metadata

Purpose: avoid expanding `loushang.resource` as a broad top-level package.

Move frontmatter parsing, source metadata, and generic diagnostics into
`loushang.harness.resources` only when internal imports can be redirected
without introducing harness -> product dependencies.

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
