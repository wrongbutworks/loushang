# Coding To Harness Migration Inventory

## Status

This is an ownership inventory and the execution order for the accelerated
runtime consolidation.

It records current ownership and the remaining action for modules migrating
from `loushang.coding` into `loushang.harness`.

Completed foundation markers remain cumulative: context, compaction, journal,
and branch implementation complete; parent-linked transcript repositories and
rebuildable indexes are Harness-owned; product runtime includes coalesced index scheduling;
and the multi-view tool-output projection core live in Agent is
consumed by Harness and Product adapters. The Conversation Runtime Core builds
on these owners rather than replacing their lower-level contracts.

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

## Product Runtime Injection Planning

The current ownership inventory remains authoritative for what has migrated
and what still belongs to Coding. The implemented
[Product Runtime Injection Architecture](product-runtime-injection/README.md)
now provides a Product-neutral runtime-profile resolver, strict snapshot,
factory registry, session sealing, and turn-boundary rebinding. Coding now
adopts a product-owned plan for its selected file/memory store, current Agent
transcript profile, and default compaction behavior. `SessionManager` binds
those factories for create/load/fork and persists the resolved snapshot; Coding
does not recreate selection, lifecycle, Native file codec, or file-layout
mechanics. Coding still owns the `persist` and root-selection decisions,
compaction prompt/model behavior, and all future OEM/extension admission
policy. The implementation does not change the classification of unrelated
entries.

## Current Package Inventory

| Current module | Classification | Target / action |
| --- | --- | --- |
| `coding.commands` | Product adapter | `CommandDef` / `CommandEffect` remain under `loushang.harness.commands`; neutral descriptors, slash parsing, completion, alias/conflict resolution, precedence, catalog lookup, ordered dispatch, and ordered capability-pack composition live under `loushang.harness.capabilities`. Coding keeps concrete command definitions, source precedence policy, handlers, routing, diagnostics, resource projection, and UI. |
| `coding.tools.types`, `schema`, `wrapper`, `registry`, `authoring`, `normalize` | Compatibility shim | Reusable tool definition, schema, normalization, wrapping, and registry mechanics live under `loushang.harness.tools`; Coding preserves accepted imports. |
| `coding.tools.factory`, `coding.tools.builtins` | Split candidate | Harness owns reusable workspace-tool construction, neutral activation accounting/refresh mechanics, and post-admission capability-pack ordering. Coding keeps default pack membership, activation policy, policy injection, and product-tuned metadata. |
| `coding.tools.presentation`, `rendering`, `builtin_renderers`, `output_preview` | Split candidate | Harness owns neutral presentation records and reusable workspace renderers/previews. Keep terminal/product projections and Coding protocol details in Coding. |
| `coding.tools.truncate` | Compatibility shim | Neutral line/byte truncation and shared limits live in `loushang.harness.workspace.truncation`. Coding keeps grep line limits, product wording, detail projection, and camelCase compatibility aliases. |
| `coding.tools.operations` | Compatibility shim | Operation protocols, sync-or-async result resolution, `LocalToolOperations`, and the default singleton live in `loushang.harness.workspace.operations`. Coding keeps normalization, Pi adapters, payload projection, and abort behavior. |
| `coding.tools.path_utils` | Split candidate | Configurable resolution, current-user expansion, canonical identity, Unicode normalization, and optional platform/user-input variants live in `loushang.harness.workspace.paths`. Coding keeps `@` syntax, default correction policy, public wrappers, and camelCase aliases. |
| `coding.tools.file_mutation_queue` | Compatibility shim | Canonical per-path mutation coordination lives in `loushang.harness.workspace.mutation_queue`. Coding paths re-export the harness functions and registry; the Pi-style camelCase alias stays coding-owned. |
| `coding.tools.read`, `ls`, `find`, `grep`, `write`, `edit`, `edit_diff`, `bash`, `process`, `ignore`, `external_tools` | Compatibility shim | Reusable implementations live in `loushang.harness.tools.workspace`. Coding injects product metadata, policy/approval, activation, and compatibility projections. |
| `coding.tools.policy` | Compatibility shim | Neutral policy-enforcement plumbing accepts an injected evaluator and Harness approval resolver. Coding retains risk classification and concrete `PolicyEngine` defaults. |
| `coding.policy` | Product adapter | Approval contracts, headless resolvers, pending-request broker lifecycle, immutable policy subjects, command normalization, rules, matchers, evaluator chains, and sync/async validation live in `loushang.harness.approval` and `loushang.harness.policy`. Coding keeps risk rules, package trust defaults, allowlists, default decisions and wording, interactive payload projection, and compatibility methods. |
| `coding.exec` | Compatibility shim | `ExecRequest`, `ExecResult`, output records, backend/update protocols, and `ExecService` live in `loushang.harness.workspace.exec`. Coding keeps the public compatibility path; policy, session cwd resolution, tool projection, and extension behavior remain product-owned. |
| `coding.diagnostics.types`, `coding.diagnostics.service` | Compatibility shim | Diagnostic vocabulary, records, queries, summaries, startup-check contracts, and the bounded in-memory engine live in `loushang.harness.diagnostics`. Coding paths re-export the same Harness-owned objects. |
| `coding.diagnostics.serialization`, `coding.diagnostics.problem_bridge`, concrete checks | Keep product | Keep camelCase payload projection, observability mapping, check selection, emission timing, remediation, session bridges, and CLI/TUI behavior in Coding. |
| `loushang.resource.frontmatter`, `coding.frontmatter` | Compatibility shim | Parser records, errors, and behavior live in `loushang.harness.resources.frontmatter`. Legacy paths preserve object identity; coding and method internal consumers use the harness owner. |
| `coding.source_info.SourceInfo`, `coding.extensions.types.SourceInfo` | Compatibility shim | `SourceInfo`, `SourceScope`, and `SourceOrigin` live in `loushang.harness.resources.source`. Coding command and extension paths preserve string and `Path` representations through the same harness class. Descriptor projection and executable identity remain in coding. |
| `coding.loader.ResourceDiagnostic`, `coding.loader.types.ResourceDiagnostic` | Compatibility shim | The focused resource record lives in `loushang.harness.resources.diagnostics`. Coding compatibility paths preserve object identity; resource checks, message selection, emission timing, and remediation remain product-owned. |
| Remaining `coding.loader.types` | Compatibility shim | Product-neutral prompt, skill, theme, and extension descriptors, source kinds, snapshots, bundles, and merge decisions live in `loushang.harness.resources.types`. Coding keeps compatibility aliases. |
| `coding.prompt.types`, `coding.prompt.templates`, assembler/preflight | Product adapter | Prompt sections, prepared prompts, deterministic composition traces, and injectable template expansion live under `loushang.harness.capabilities.prompt`; active resource selection, skill disabling, prompt/skill lookup, and context/fragment projection live in `harness.resources.activation`. Coding preserves compatibility imports and keeps system prompt text, skill XML, prompt syntax/diagnostics, and runtime footer content. |
| `coding.compaction.policy`, `coding.compaction.types.ContextUsageEstimate` | Compatibility shim | `CompactionBudget`, deterministic threshold accounting, and `ContextUsageEstimate` live in `loushang.harness.context`. Coding compatibility paths re-export the same Harness-owned objects. |
| Remaining `coding.compaction.types`, `coding.session.context_usage` | Product adapter | Neutral context items, packing, strategies, coordinator lifecycle, salience, summary profiles, opaque-record turn/cut planning, split-turn/tool-result mechanics, previous-summary accounting, and checkpoint replay now live in Harness. Coding keeps compatibility records, message/aggregate token adapters, trigger decisions, exact prompts, model calls, content weights, and artifact projection. |
| `coding.domain.types` | Split candidate | Use as input for future `loushang.harness.adapter` shapes. Generic request/result types must not contain first-class method fields; carry method/work refs as opaque metadata. |
| `coding.session.types.RunState` | Compatibility shim | `RunState` lives in `loushang.harness.host.types`; Coding preserves the accepted session import with the same class identity. |
| removed `coding.session.queue_controller`, `prompt_controller`, `agent_event_router`, and `session_event_bus`; reduced `extension_message_controller` | Harness profile / Product adapter | Queue snapshots, `HostInputQueue`, and `TurnInputQueue` live in `loushang.harness.host`. `harness.session.SessionRuntime` is the single Agent-session owner for queue delivery, prompt ordering, Agent subscription/event routing, standard ApplicationMessage delivery/commit coordination, Host lifecycle, transcript-commit observation, and the ordered RuntimeEvent stream. Coding injects AI message construction, preflight, Extension API argument mapping, retry, compaction, diagnostics, transcript, delivery policy, and its UI/RPC event projection adapter. |
| `coding.session.AgentSession`, controllers, `coding.runtime.AgentSessionRuntime` | Product adapter | `AgentSession` is now a Coding facade over `harness.session.SessionRuntime` for run, turn, queue, runtime-event sequencing, and abort/idle/dispose coordination. `harness.session.SessionLifecycleRuntime` owns the active session new/restore/fork/import/replacement/disposal transaction, Product store/hook ports, and default `at` fork profile. Coding injects its `before`/`at` fork profile and resolver, extension lifecycle events, cwd/session-file acceptance, diagnostics, callbacks, index policy, and presentation. Coding retains controller policy/adapters, concrete commands, tool defaults/materialization, compaction/tree semantics, Product event projection, and storage-provider selection. Async transcript state and persistence live in `harness.agent_transcript` and `harness.storage`. |
| `coding.event` | Keep product | The common runtime envelope, ordering, queue/compaction/retry/branch/metadata/package payloads, and committed-record fact live in `loushang.harness.events`. Coding retains its accepted Agent/session dictionary only as a JSON, RPC, print, TUI, extension, filtering, and render-enrichment projection. |
| `coding.extensions.events`, `manifest`, `loader`, `contributions`, `wrapper` | Compatibility shim | Event declarations, manifest parsing, descriptor-driven loading, contribution projection, and tool wrapping live in `loushang.harness.extensions`. Coding paths preserve imports and inject Coding API/policy/legacy-event adapters. |
| `coding.extensions.api`, `runner`, `types`, `policy`, `hooks` | Product adapter | Neutral records, registration, conflict resolution, stable route planning, observer/interceptor/reducer dispatch, resource contribution execution, binding storage/lifetimes, and generic bound/unbound runtime contexts live in Harness. Coding keeps typed model/thinking/command specialization, provider/UI callback injection, concrete permission defaults, Product result reducers, session decisions, and Agent tool-call adaptation. |
| `coding.bootstrap` | Keep product | Product assembly. It binds Coding's persisted Product-only capability profile to Harness resource/skill activation, prompt composition, and tool/command pack ordering; it may call harness engines but should not move. |
| `coding.runtime` | Product adapter | Generic binding leases, runtime contexts, current-session transitions, serialized operation phases, uncommitted-candidate rollback, replacement callback ordering, exclusive import staging, navigation abort scopes, and coalesced scheduling live in Harness. `harness.session.SessionLifecycleRuntime` now owns the common active-session new/restore/fork/import/replacement/disposal flow and default fork semantics. Coding keeps composition, cwd/session-file resolution and acceptance policy, its `before` user-message fork interpretation, extension event projection, diagnostics codes, transcript semantics, package operations, and index content. |
| `coding.ui` | Never harness | Product-owned TUI adapter and screen/controller state. Shared terminal primitives belong in `loushang.tui`, not harness. |
| `coding.mode` | Keep product | Transitional print/RPC mode adapters stay coding until channel is implemented. RPC now uses an explicit transport projection for known dataclasses, paths, mappings, lists, and tuples while rejecting cycles, sets, arbitrary objects, `__dict__` discovery, non-finite floats, and `repr()` fallback. |
| `coding.cli` | Keep product | Product CLI. It may expose harness-backed behavior but remains coding-owned. |
| `coding.message` | Migrated and removed | `harness.conversation` owns the neutral envelope, repository, replay, and opaque-record behavior. The optional `harness.agent_transcript` profile owns standard Agent transcript payloads, codecs, state/context projection, the pure record factory, idempotent application-message commit, and an explicit Session v3 external importer. Native Product load accepts only the current format. Coding keeps only product presentation and orchestration policy. |
| `coding.store` | Product adapter / compatibility shim | `ConversationStore`, revision/CAS semantics, Memory/File backends, and the open Agent transcript service live in Harness. The current Native Agent transcript codec, journal policy, lock, file layout, discovery, `FileConversationStore` assembly, standard session-facing commit/label/context operations, catalog summary/query/index/tree read model, and create/restore/detached-copy/fork/disposal lifecycle mechanics now live in `harness.agent_transcript`. Coding's `ProductRuntimePlan` selects file/memory stores and transcript profiles; its `SessionManager` facade retains root/persist decisions, runtime-profile binding, Product-only index fields and retention, CLI/UI policy, and compatibility names. Database/Redis providers and journal-offset projection checkpoints remain deferred. |
| `coding.control` | Product adapter | Transactional ordered layers and persistence, `ConfigFieldSpec` / `SchemaConfigCodec`, scoped revisions and `ConfigChange` records, subscriptions, issue collection, injected-runner value resolution, and the explicit activation DAG live in `loushang.harness.config`. Coding keeps `ControlConfig`, fields, defaults, validation, paths, removed-setting compatibility, convenience APIs, diagnostic wording, effect selection/order/callbacks, provider registration, credential handling, model/auth interpretation, persisted selection policy, commands, and UI. Harness neither executes shell commands nor stores credentials; `ModelRegistry` and `AuthManager` do not move. |
| `coding.package`, `coding.plugin`, `coding.resources`, `coding.skill` | Split candidate | Package source/manifest/materialization, standard roots/layout, registry/resolver, discovery, skill-loading, structured package catalog, scoped source resolution, lifecycle summary, and conflict diagnostics now live under `loushang.harness.resources`. Coding keeps built-in content registration, compatibility convention activation, additional roots, trust/approval policy, settings injection, CLI/RPC projection, and compatibility facades. |
| `coding.workflow` | Compatibility shim / Product adapter | `loushang.harness.scenario` owns workflow schema, parser, runner, cancellation, waiting, event patterns, result values, fake adapter, read-only file assertions, and the injected command-runner protocol. Coding keeps CLI/reporting, model readiness, scenario activation, legacy local-shell execution policy, and compatibility exports. |
| `coding.platform` | Split candidate | Route neutral workspace/git and operating-system mechanisms to focused Harness modules when reusable. Keep product update/version policy and output guards in Coding; clipboard and terminal integration belong to Product/TUI rather than Harness. |
| `coding.work_shell` | Keep product | Coding adapter to `loushang.work`; do not move into Harness or Work. It subscribes to `RuntimeEvent`, then the explicit `loushang.work.projection` bridge projects Agent/tool payloads into strict `WorkEvent` values. Coding keeps run/session wiring and Product policy. |

## Accelerated Dependency-First Execution

The remaining migration proceeds as capability waves across all of Coding. It
does not select the next module only from the Resource area, and it does not
move the module with the highest fan-in without first checking ownership.

The global dependency knots are:

- `loader` / `package` / `plugin` / `policy` / `prompt`;
- `bootstrap` / `runtime` / `session` / public re-export paths;
- `cli` / `ui` / `workflow` / command adapters.

Break these knots from their reusable foundations upward. The next execution
order is:

### Wave 1: Resource And Package Runtime

Status: implementation complete for integration into `lane/harness`.

Move the entire product-neutral resource/package dependency closure in one
semantic branch. Ordered commits inside the branch should cover:

- neutral policy-decision records and evaluator protocols needed by package
  materialization, while Coding keeps concrete risk and trust rules;
- remaining resource descriptors, package source identities, package manifests,
  scope/layout/precedence records, and built-in package descriptors;
- filesystem and package discovery, deterministic catalog/merge/reload,
  materialization, registry/resolver, and `AGENTS.md` convention engines;
- Coding compatibility imports and a reduced `DefaultResourceLoader` facade
  that injects product roots, activation, trust, prompt projection, and UI
  behavior.

This is one capability batch, not separate slices for types, roots, manifests,
materialization, loader, and shims. The batch is complete only when Coding no
longer contains a second implementation of shared discovery, merge, or package
runtime behavior.

Deliver Wave 1 on one `harness/resource-package-runtime` branch with an ordered
commit series rather than nested task branches:

1. establish neutral policy, resource, source, manifest, layout, and catalog
   foundations plus import guards;
2. move materialization, discovery, merge/reload, built-in registration, and
   convention engines with focused Harness tests;
3. cut Coding consumers over to Harness and reduce legacy modules to product
   adapters or compatibility re-exports;
4. close behavior-parity, startup-smoke, architecture-boundary, and non-live
   regression tests, then update ownership documentation.

The wave must preserve current resource precedence, diagnostics, package-source
handling, local and remote materialization contracts, instruction discovery,
and Coding startup behavior. API cleanup and compatibility-shim removal are not
allowed to obscure the ownership transfer; schedule them after the wave is
green.

### Wave 2: Extension Runtime Core

Status: implementation complete for integration into `lane/harness`; see
[Extension Runtime Core Boundary](extension-runtime-core-boundary.md).

Harness now owns generic extension manifest parsing, descriptor-driven loading,
contribution registration and projection, deterministic conflict resolution,
failure-contained observer and input dispatch, resource contribution execution,
and tool wrapping. Coding keeps permission defaults, activation choices,
product handlers, model/provider bindings, session projection, specialized
result reducers, and UI commands.

### Wave 2 Follow-On: Control Plane Runtime

Status: implementation complete for integration into `lane/harness`; see
[Control Plane Runtime Boundary](control-plane-runtime-boundary.md).

Harness now owns event-scoped extension route planning, dependency ordering,
generic observer/interceptor/reducer execution, neutral policy subjects and
rules, evaluator chains, canonical effective-command normalization, neutral
enforcement audit records, and pending approval lifecycle. Coding retains
Product reducers, risk defaults and wording, interactive payload projection,
session-event audit projection and persistence, and compatibility methods.

### Wave 3: Persistence, Context, And Workflow Mechanics

Status: context, journal, conversation repository/catalog/replay, branch, and
turn-aware compaction-planning implementation complete for integration into
`lane/harness`; see
[Context, Compaction, And Journal Foundations](context-compaction-journal-foundations.md)
and [Conversation Runtime Core Boundary](conversation-runtime-core-boundary.md).

Extract neutral context items and group-aware packing, selectable compaction
strategies and coordination, file locking, profiled atomic JSONL mechanics,
opaque header/record codecs, parent-linked branch/fork engines, conversation
catalog/replay, and opaque-record turn-aware cut planning. Coding keeps its
compatibility compaction records, transcript payload schema, custom message
codecs, prompts, model calls, artifact semantics, Product projection, and
storage policy. Work
keeps normalization, its in-memory/query/subscription behavior, and
WorkOperation/WorkEvent schemas while adopting only matching JSONL I/O. AI owns
base-message codecs, Agent owns extension-message codec protocols and registry,
and each Product owns its custom transcript codecs. The follow-on Runtime Data
Foundations wave now owns rebuildable generic JSON projection indexes while
Product projection schemas and journal-offset checkpoints remain Product-owned
or deferred.

Deliver this as one semantic wave with three substantial batches: compatibility
baseline plus complete contracts, complete Harness engines, then concurrent
Coding/Work cutover plus duplicate removal and closure. Characterization tests
land with the contract or adapter they protect; they are not a separate waiting
phase. Do not split records, protocols, codecs, or individual adapters into
small merge units.

The Scenario Runtime follow-on completed the workflow execution ownership
decision without conflating test-scenario mechanics with `loushang.method` or
`loushang.work`; see [Scenario Runtime Boundary](scenario-runtime-boundary.md).
Harness owns the reusable runner while Product adapters retain input, command,
artifact, and completion policy.
The later Agent Transcript Profile wave completed this ownership transfer and
removed `coding.message`; see
[Agent Transcript Profile Boundary](agent-transcript-profile-boundary.md).

### Wave 4: Session And Runtime Consolidation

Status: product runtime core implementation complete for integration into
`lane/harness`.

Status: host turn and session orchestration core implementation complete for
integration into `lane/harness`; see
[Host Turn And Session Orchestration Core Boundary](host-turn-session-orchestration-core.md)
and [Product Runtime Core Boundary](product-runtime-core-boundary.md).

Harness now owns product runtime binding storage and generation leases, generic
bound/unbound extension contexts, turn and retry state machines, resource
watch/refresh ordering, extension bind/refresh/invalidate lifecycle, opaque
session operation transactions, callback ordering, import staging, navigation
abort scopes, and coalesced runtime scheduling. Coding keeps concrete messages,
create/restore/fork/import/clone decisions, session files and projections,
extension event/decision semantics, diagnostics wording, commands, Product
controller adapters, control/model/auth, transcript semantics, channels, and UI.

Each wave may span several reviewable commits, but it should merge as one
coherent ownership transfer. A wave is split only when a product boundary or
independent validation boundary requires it.

### Wave 5: Product Capability Composition

Status: product capability composition core implementation complete for
integration into `lane/harness`. Coding's Product-only profile binding is also
complete; see
[Product Capability Composition Core Boundary](product-capability-composition-core.md).

Harness now owns neutral command descriptors, catalogs, conflicts, completion,
slash parsing and ordered dispatch; ordered prompt sections, composition traces,
and injectable template expansion; and tool availability, request, activation,
missing-name, refresh, diff, revision, and rebind coordination. Coding adopts
those owners through compatibility adapters.

Coding keeps command definitions and handlers, prompt content and resource
projection, default tool packs and activation policy, Agent materialization,
execution context, diagnostics, audit events, approval/risk policy, and UI.
Coding persists the resolved capability snapshot separately from its
store/transcript `runtimeProfile` and validates it on persistent resume. This
wave does not introduce a universal Product manifest, admit executable OEM or
extension factories, or move model/auth/settings into Harness.

### Product Configuration Runtime

Status: implementation complete for integration into `lane/harness` on the
semantic branch `harness/product-configuration-runtime`; see
[Product Configuration Runtime Boundary](product-configuration-runtime-boundary.md).

Harness now owns transactional layered configuration, Product-injected schema
mechanics, typed scopes and revisioned change records, value resolution with an
injected runner, and explicit activation DAG ordering and reporting. Coding
adopts those mechanisms while retaining `ControlConfig`, all field semantics,
defaults, validation, paths, removed-setting compatibility, convenience APIs,
diagnostic wording, and configuration effect order and callbacks.

The activation runtime is neither a service locator nor a Product or extension
manifest. Harness does not execute a shell or store credentials. `ModelRegistry`,
`AuthManager`, provider registration, auth resolution, credential handling, and
persisted model-selection behavior remain with their existing AI or Product
owners.

## Completed And Accepted Capability History

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

Status: resource and package runtime implementation complete for integration
into `lane/harness`.
See [Platform Resource Layout Boundary](platform-resource-layout-boundary.md).

Harness owns `LOUSHANG_HOME`/`~/.loushang`, the standard
`<workspace>/.loushang` layout, shared resource directories, scope vocabulary,
the overridable precedence preset, reusable `AGENTS.md` discovery, optional
compatibility conventions, and built-in/package loading mechanisms.

Coding registers `loushang.coding.resources`, selects enabled conventions,
add product roots and filters, apply trust/approval policy, and project the
Harness resource snapshot into Coding prompts, sessions, commands, and UI.

### Slice 4: Context

Status note: context budget and accounting implementation complete; later
waves extend the same owner with packing, compaction, salience, and summary
profiles.

Status: context budget, accounting, item, packing, compaction, salience, and
summary-profile implementation complete for integration into `lane/harness`;
see [Context Budget And Accounting Boundary](context-budget-accounting-boundary.md),
[Context, Compaction, And Journal Foundations](context-compaction-journal-foundations.md),
and [Runtime Data Foundations](runtime-data-foundations.md).

Purpose: define shared context budget and packing contracts without moving
coding compaction policy.

`CompactionBudget`, deterministic percentage/reserve threshold accounting, and
the `ContextUsageEstimate` result record now live under
`loushang.harness.context`. Coding compatibility paths re-export the Harness
owners, while Coding continues to estimate message tokens, adapt model context
windows, build usage snapshots, and decide whether to compact.

Context item refs, bundles, diagnostics, packing, standard compaction
strategies, explainable salience signals, summary-profile mechanics, and the
generic split-turn/non-cut-role planning mechanism now live in Harness. Coding
retains exact transcript summarization and branch prompt text, custom transcript
serialization, content-specific salience weights, role mappings and planner
configuration, model calls, artifacts, and transcript rebuild semantics.

### Slice 5: Host And Lifecycle

Status: host runtime core implementation complete for integration into
`lane/harness`; the host turn/session orchestration core is also complete. See
[Host Runtime Boundary](host-runtime-boundary.md) and
[Host Turn And Session Orchestration Core Boundary](host-turn-session-orchestration-core.md).

Purpose: let future products share idle/abort/dispose/queue contracts.

Harness now owns host status/snapshots, driver-delegating lifecycle
coordination, generic steering/follow-up queue and turn mechanics, retry and
compaction single-flight state, scoped runtime event sequencing and ordered
mirroring, resource watch/refresh,
extension lifecycle coordination, and session/navigation transactions. Coding
uses those mechanisms while retaining `AgentSession`, Product controller policy
and adapters, Product event schemas, storage composition and replacement decisions, prompt
text, resource activation/projection, extension policy, and UI semantics.

The independent reference driver and neutral queue/event fixtures satisfy the
neutrality evidence gate without moving `AgentSession` wholesale or creating a
second agent loop.

### Slice 6: Contribution Model

Status: contribution inventory implementation complete; extension runtime core implementation
complete for integration into `lane/harness`; see
[Contribution Inventory Boundary](contribution-inventory-boundary.md) and
[Extension Runtime Core Boundary](extension-runtime-core-boundary.md).

Purpose: support OEM and extension contributions across products.

Contribution descriptors and generic inventory indexing live in
`loushang.harness.contributions`. Extension manifests, runtime contribution
projection, loading, registration, conflict resolution, observer/input
dispatch, resource contributions, and tool wrapping live in
`loushang.harness.extensions`. Coding compatibility paths re-export the same
Harness-owned records and provide thin product adapters.

Activation and permission defaults, concrete product handlers, rich runtime
bindings, specialized session/model/tool reducers, and UI projection remain
Coding-owned. Product-neutral Harness tests provide the independent contract
probe for the moved invocation shape.

## Guardrails

- Do not add `loushang.harness` imports from `loushang.agent`.
- Do not add product imports from `loushang.harness`.
- Default reusable concrete implementations to Harness; keep only
  domain-specific tool semantics in products.
- Freeze Product configuration semantics and credential ownership, not neutral
  configuration mechanisms. `ControlConfig` fields, defaults, validation,
  paths, removed-setting compatibility, convenience APIs, diagnostic wording,
  and effect selection/order/callbacks remain Product-owned.
- Do not route credentials, `ModelRegistry`, `AuthManager`, provider
  registration, auth resolution, or persisted model selection through Harness.
  Harness neither executes shell commands nor stores credentials; command-backed
  values require an injected Product runner.
- Do not move product prompt content, section selection/order, command
  definitions/handlers, or source precedence policy. Neutral template
  expansion, prompt composition, slash parsing, catalog, and dispatch mechanics
  belong to Harness. Reusable `AGENTS.md` discovery belongs to Harness; Product
  owns convention activation and prompt projection.
- Do not add broad top-level packages for workspace, context, memory, or
  session.
- Do not add new top-level harness exports unless they are intentionally public.

Each semantic migration branch should update this inventory if the final
ownership differs from the current classification.
