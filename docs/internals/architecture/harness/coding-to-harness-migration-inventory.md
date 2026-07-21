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

Classification defaults to the correct shared owner. `Keep product` entries
require a named product-kernel reason; historical location or lack of a second
consumer is not sufficient. Shared code may belong to Harness, Channel,
HarnessTUI, TUI, AI, Observability, Method, or Work according to its semantic
boundary.

## Current Long-Term Plan

Future Coding consolidation follows the accepted
[Coding To Shared-Layer Migration Plan](coding-shared-layer-migration-plan.md).
That plan introduces the mandatory owner/duplicate rebaseline ledger and the
current six delivery waves. The historical execution sections below remain a
record of completed foundation waves; they are not a promise that their old
module-level estimates remain unimplemented work.

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
| `coding.tools` | Removed | The complete facade is extinct. Reusable contracts, schema, normalization, registry, wrappers, workspace implementations, path/mutation, truncation (`loushang.harness.workspace.truncation`), renderers, and protocols are imported from Harness. No Coding compatibility or Pi-style aliases remain. |
| `coding.tool_pack` | Product adapter | Coding keeps only default seven-tool membership/order, Coding descriptions and prompt snippets, managed downloader default, and injection of Coding policy, approval, diagnostics, and execution services. |
| `coding.policy` | Product adapter | Approval contracts, headless resolvers, pending-request broker lifecycle, immutable policy subjects, command normalization, rules, matchers, evaluator chains, and sync/async validation live in `loushang.harness.approval` and `loushang.harness.policy`. Coding keeps risk rules, package trust defaults, allowlists, default decisions and wording, interactive payload projection, and compatibility methods. |
| removed `coding.exec` | Removed | `ExecRequest`, `ExecResult`, output records, backend/update protocols, and `ExecService` are publicly imported from `loushang.harness.workspace.exec`. Policy, session cwd resolution, tool projection, and extension behavior remain product-owned. |
| removed `coding.diagnostics.types`, `coding.diagnostics.service`, `coding.diagnostics.problem_bridge` | Removed | Diagnostic vocabulary, records, queries, summaries, startup-check contracts, the bounded in-memory engine, and the optional `ProblemRecord` bridge live under `loushang.harness.diagnostics`. Coding retains serialization, concrete checks, its `config` to `model` source policy, and presentation. |
| `coding.diagnostics.serialization`, concrete checks | Keep product | Keep camelCase payload projection, product observability-source classification, check selection, emission timing, remediation, and CLI/TUI behavior in Coding. `harness.session.SessionDiagnosticsRuntime` owns the common session scope/filtering and Agent/Tool failure correlation that the former Coding session bridge implemented. |
| `loushang.resource.frontmatter`; removed `coding.frontmatter` | Canonical owner | Parser records, errors, and behavior live in `loushang.harness.resources.frontmatter`. The legacy top-level resource path preserves object identity; Coding and method import the Harness owner directly. |
| `coding.source_info.SourceInfo`, `coding.extensions.types.SourceInfo` | Compatibility shim | `SourceInfo`, `SourceScope`, and `SourceOrigin` live in `loushang.harness.resources.source`. Coding command and extension paths preserve string and `Path` representations through the same harness class. Descriptor projection and executable identity remain in coding. |
| removed `coding.loader`, `coding.loader.types` | Removed | `ResourceDiagnostic` lives in `loushang.harness.resources.diagnostics`; neutral prompt, skill, theme, and extension descriptors, source kinds, snapshots, bundles, and merge decisions live in `loushang.harness.resources.types`. Consumers import those owners directly. |
| `coding.prompt.types`, removed `coding.prompt.templates`, assembler/preflight | Canonical owner / compatibility adapter | `PromptAssembly`, standard resource-aware assembly, the neutral Harness default prompt, and prompt/skill preflight live under `loushang.harness.capabilities.prompt_assembly` and `prompt_preflight`; prompt sections, deterministic traces, and injectable template expansion remain in `harness.capabilities.prompt`. Coding retains `DEFAULT_CODING_SYSTEM_PROMPT` and thin public-import/default-behavior adapters with canonical Harness type identities. |
| removed `coding.compaction.policy`, generic `coding.compaction.types` | Removed | `CompactionBudget`, deterministic threshold accounting, `ContextUsageEstimate`, and standard transcript compaction records are imported directly from `loushang.harness.context` or `loushang.harness.agent_transcript`. |
| removed `coding.compaction.compaction`, `coding.compaction.branch_summarization`, `coding.compaction.types`, `coding.compaction.summary_quality`, `coding.session.context_usage`, `coding.session.compaction_controller`, and `coding.session.retry_controller` | Product adapter | `harness.agent_transcript` owns Agent transcript token extraction/estimation, context usage snapshots and threshold decisions, turn-aware compaction plan/preparation/result/status, standard AI-backed compaction/turn-prefix/branch-summary execution, branch-delta selection, checkpoint commit/event lifecycle, overflow guard, retry classification/backoff/cancellation, and retry events. `harness.context` owns profile-driven summary evaluation and `SummaryResourceOperations`; a profile declares its resource-evidence tags, so `read` and `modified` are generic operations rather than Coding fields. `AgentSession` binds the Harness runtimes directly. Coding retains prompt/profile content, code file-operation decoration, extension hook translation, diagnostics wording, settings/default policy, and presentation. |
| `coding.domain.types` | Split candidate | Use as input for future `loushang.harness.adapter` shapes. Generic request/result types must not contain first-class method fields; carry method/work refs as opaque metadata. |
| `coding.session.types.RunState` | Compatibility shim | `RunState` lives in `loushang.harness.host.types`; Coding preserves the accepted session import with the same class identity. |
| `coding.session.types.AgentSessionState`, `ContextUsage`, `SessionStats`, `TokenUsageTotals` | Compatibility shim | `harness.session.inspection` owns the product-neutral Agent/transcript observation values and `AgentSessionInspector`. Coding preserves its accepted imports and keeps Pi stats plus UI/RPC/HTML projection. |
| removed `coding.session.export_html`, `coding.session.export_jsonl`, and `coding.session.introspection` | Harness profile / Product adapter | `harness.agent_transcript.export` owns current-Native JSONL branch export, HTML document composition/assets, standard transcript-kind/tree/ANSI/Markdown/default-tool presentation, and the immutable export request/profile contracts. `AgentSessionInspector` owns shared statistics including transcript token totals. Coding's `session.export` adapter selects paths and injects its theme, extension message renderer, tool resolver, and command/API projection. |
| removed `coding.session.queue_controller`, `prompt_controller`, `agent_event_router`, `session_event_bus`, `extension_message_controller`, `extension_event_sink`, and `extension_hooks` | Harness profile / Product adapter | Queue snapshots, `HostInputQueue`, and `TurnInputQueue` live in `loushang.harness.host`. `harness.session.SessionRuntime` is the single Agent-session owner for queue delivery, prompt ordering, Agent subscription/event routing, standard ApplicationMessage delivery/commit coordination, Host lifecycle, transcript-commit observation, and the ordered RuntimeEvent stream. `ExtensionInputRuntime`, `ExtensionAgentHookRuntime`, and `ExtensionAgentEventRuntime` live in the optional `harness.extensions.agent` profile, where typed input, control hooks, and observation-only lifecycle callbacks do not import Session. Coding injects AI message construction, preflight, Extension API argument mapping, retry, compaction, diagnostics, transcript, delivery policy, and its UI/RPC event projection adapter. |
| removed `coding.session.session_diagnostics_bridge` | Harness profile / Product adapter | `harness.session.SessionDiagnosticsRuntime` owns common session scope filtering, extension-diagnostic synchronization, failed assistant/tool projection, and policy-denial correlation. Coding binds its active transcript scope and extension diagnostics port, then retains Product-specific diagnostic selection, wording, and presentation. |
| `coding.session.AgentSession`, controllers, `coding.runtime.AgentSessionRuntime` | Product adapter | `harness.session.SessionFacade` now combines standard Product-facing session operations from one Product-supplied `SessionFacadePorts` bundle. `harness.session.SessionOperationRuntime` supplies explicit capability-grouped input, queue, lifecycle, identity, retry, and maintenance calls over the bound `SessionControlPort`; Coding RPC uses it while retaining Coding JSON mapping and task tracking. The standard Coding Channel adapter admits its `WorkOperation` through `loushang.work.WorkRuntime` and keeps Channel transport injected. `harness.agent_transcript.ProductTranscriptSession` owns the generic Product transcript-session wrapper, so Coding's `SessionManager` binds only its runtime/capability profile and exposes Coding-only runtime capabilities. `AgentSession` adapts `SessionFacade` and `harness.session.SessionRuntime` for run, turn, queue, runtime-event sequencing, and abort/idle coordination. It binds `AgentTranscriptNavigationRuntime`, `AgentTranscriptSelectionRuntime`, and `AgentTranscriptCompactionRuntime` directly; the former Coding controller wrappers are removed. `harness.session.AgentSessionInspector` owns common state/context/statistics/fork-candidate observation; Coding retains its Product RPC/HTML/UI projection. `harness.agent_transcript.AgentTranscriptRetryRuntime` owns retry lifecycle directly; Coding binds its settings and overflow classification, and has removed the redundant `RetryController`. `harness.extensions.agent` owns the extension-to-Agent input, hook, and observation-only lifecycle profile; `harness.extensions.ExtensionSessionRuntime` remains the neutral owner of extension binding/refresh/invalidation coordination. `harness.session.SessionLifecycleRuntime` owns the active session new/restore/fork/import/replacement/disposal transaction, Product store/hook ports, and default `at` fork profile. `harness.session.AgentTranscriptSessionRuntime` composes that transaction runtime with `harness.agent_transcript.AgentTranscriptDirectoryRuntime` current-root/all-root catalog reads, index refresh, coalesced scheduling, and current session-reference resolution; `AgentSessionRuntime` binds the facade directly. Coding CLI, RPC, builtins, and extension replacement now consume typed operation results; Pi-style dict lifecycle aliases and duplicate callback coordination are removed. `harness.agent_transcript` owns standard branch navigation, cancellation, summary transaction/event ordering, context replay, model/thinking persistence and cycling, fork candidates, transcript inspection, context accounting, and compaction/retry maintenance lifecycle. Coding injects its model catalog/auth resolution, `before`/`at` fork profile and resolver, extension lifecycle/tree hooks, branch-summary/compaction prompt/profile and model/credential selection, cwd/session-file acceptance, diagnostics, callbacks, index policy, and presentation. The core Session/Runtime and extension session contract use snake_case; Pi SDK aliases are intentionally removed. Async transcript state and persistence live in `harness.agent_transcript` and `harness.storage`. |
| removed `coding.session.resource_refresh_controller` | Harness profile / Product adapter | `harness.session.SessionResourceRefreshRuntime` owns ordered prepare, reload, optional extension discovery, disabled-skill activation, bundle commit, prompt/tool rebuild, and contained refresh failure routing. Coding binds `CodingResourceLoader`, roots, settings, current extension runner, diagnostic wording, watcher trigger, and Coding extension-runtime refresh behavior. |
| `coding.event` | Product adapter | The common runtime envelope, ordering, queue/compaction/retry/branch/metadata/package payloads, committed-record fact, strict `RuntimeEventView`, generic event-selector mechanics, and recursive snake_case JSON event serializer live in `loushang.harness.events`. `loushang.channel` carries a completed view as a separate runtime event family. Coding retains its accepted Agent/session dictionary, view mapping, tool render enrichment, and extension/TUI presentation policy; it no longer emits or accepts Pi/camelCase event aliases. |
| removed `coding.extensions.events`, `manifest`, `contributions`, `wrapper`, and `types`; `coding.extensions.loader` | Canonical split / Product adapter | Event declarations, manifest parsing, descriptor-driven loading, contribution projection, tool wrapping, records, and context contracts live in `loushang.harness.extensions`. Coding imports those owners directly; `ExtensionLoader` injects the Coding API, policy, and legacy-event choices. |
| `coding.extensions.api`, `runner`, `policy`, `hooks` | Product adapter | Neutral records, registration, conflict resolution, stable route planning, observer/interceptor/reducer dispatch, resource contribution execution, binding storage/lifetimes, generic bound/unbound runtime contexts, lifecycle records, and `harness.extensions.runtime.ExtensionRuntime` composition live in Harness. `harness.extensions.context` owns the standard extension context/command context/UI protocols and session lifecycle records. The runtime owns registry snapshots, commands/flags/shortcuts, generic input/event dispatch, tool wrapping, renderer/diagnostic/visibility projection, and resource discovery through injected context factories. Coding keeps descriptor loading with its API, typed model/thinking/command specialization, provider callback injection, concrete permission defaults, Product result reducers, session decisions, Agent tool-call adaptation, and event/wire projection. Pi-style Extension UI aliases are removed; the snake_case context API is the sole extension API. |
| `coding.bootstrap` | Keep product | Product assembly. It binds Coding's persisted Product-only capability profile to Harness resource/skill activation, prompt composition, and tool/command pack ordering; it may call harness engines but should not move. |
| `coding.runtime` | Product adapter | Generic binding leases, runtime contexts, current-session transitions, serialized operation phases, uncommitted-candidate rollback, replacement callback ordering, exclusive import staging, navigation abort scopes, and coalesced scheduling live in Harness. `harness.session.SessionLifecycleRuntime` owns the common active-session new/restore/fork/import/replacement/disposal flow and default fork semantics; `harness.session.AgentTranscriptSessionRuntime` adds the standard Agent transcript directory/index and current-reference facade. Coding keeps composition, cwd/session-file resolution and acceptance policy, its `before` user-message fork interpretation, extension event projection, diagnostics codes, transcript semantics, package operations, and index content. |
| `coding.ui` | Never harness | Product-owned TUI adapter and screen/controller state. Shared terminal primitives belong in `loushang.tui`, not harness. |
| `coding.mode` | Product adapter | `harness.host.rpc` owns the shared JSONL RPC host, standard session-operation handlers, state/model/diagnostic dispatch, task draining, and strict transport projection. `harnesstui.conversation.plain_mode` owns the plain/JSON output host and state observation. `channel` owns framing, correlation, cancellation, and delivery. Coding retains only the Work/domain operation binding plus injected event and diagnostic projections; no Pi aliases are retained. |
| `coding.cli` | Keep product | Product CLI. It may expose harness-backed behavior but remains coding-owned. |
| `coding.message` | Migrated and removed | `harness.conversation` owns the neutral envelope, repository, replay, and opaque-record behavior. The optional `harness.agent_transcript` profile owns standard Agent transcript payloads, codecs, state/context projection, the pure record factory, idempotent application-message commit, and an explicit Session v3 external importer. Native Product load accepts only the current format. Coding keeps only product presentation and orchestration policy. |
| `coding.store` | Product adapter / compatibility shim | `ConversationStore`, revision/CAS semantics, Memory/File backends, and the open Agent transcript service live in Harness. The current Native Agent transcript codec, journal policy, lock, file layout, discovery, `FileConversationStore` assembly, standard session-facing commit/label/context operations, catalog summary/query/index/tree read model, lifecycle mechanics, and `AgentTranscriptSessionFactory` header/create/load/recent-resume/fork orchestration now live in `harness.agent_transcript`. Coding's `ProductRuntimePlan` selects file/memory stores and transcript profiles; its `SessionManager` facade retains root/persist decisions, runtime/capability profile binding and compatibility validation, Product-only index fields and retention, CLI/UI policy, and compatibility names. Database/Redis providers and journal-offset projection checkpoints remain deferred. |
| `coding.control` | Product adapter | Transactional ordered layers and persistence, `ConfigFieldSpec` / `SchemaConfigCodec`, scoped revisions and `ConfigChange` records, subscriptions, issue collection, injected-runner value resolution, and the explicit activation DAG live in `loushang.harness.config`. Coding keeps `ControlConfig`, fields, defaults, validation, paths, removed-setting compatibility, convenience APIs, diagnostic wording, effect selection/order/callbacks, provider registration, persisted model-selection policy, commands, and UI. Harness neither executes shell commands nor stores credentials. `ModelRegistry` remains Product-owned; request authentication declarations and credential-to-header resolution remain AI-owned. Coding has no authentication lifecycle or credential store. |
| removed `coding.package`, `coding.plugin`, `coding.skill`; `coding.resources` | Canonical split complete / Product content | Package source/manifest/materialization, standard roots/layout, registry/resolver, discovery, skill-loading, structured package catalog, scoped source resolution, lifecycle summary, conflict diagnostics, and install/update/remove/uninstall ordering live under `loushang.harness.resources`. `coding.resource_runtime` binds Coding's built-in content, `CLAUDE.md` convention, prompt assembly, package security policy, and settings fallback; `coding.package_projection` owns the established Coding CLI/RPC schema. `coding.resources` retains only built-in product content. No legacy import facades remain. |
| `coding.workflow` | Product adapter | `loushang.harness.scenario` owns workflow schema, parser, runner, cancellation, waiting, event patterns, result values, fake adapter, read-only file assertions, and the injected command-runner protocol. Coding keeps CLI/reporting, model readiness, scenario activation, and legacy local-shell execution policy; shared scenario imports are direct. |
| `coding.platform` | Canonical split complete | Git metadata is owned by `harness.workspace.git`; text and image clipboard capabilities are owned by `tui.clipboard` and `tui.clipboard_image`. Internal consumers use those canonical paths and the retired Coding facades are absent. Product update/version, footer projection, and output guards remain in Coding. |
| `coding.work_shell` | Keep product | Coding adapter to `loushang.work`; do not move into Harness or Work. It subscribes to `RuntimeEvent`, then the Work-owned `loushang.work.agent_projection` bridge projects standard Agent/tool payloads into strict `WorkEventFact` values. Coding keeps run/session wiring, its custom message serializer, and Product policy. |

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
- a `coding.resource_runtime` product binding that injects Coding roots,
  activation, trust, prompt projection, and UI behavior without re-exporting
  Harness resource types.

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

The follow-on [Extension Context Runtime Boundary](extension-context-runtime-boundary.md)
is also complete: Harness owns the standard extension context and lifecycle
contracts while Coding's types are re-exports and internal consumers use the
Harness owner directly. Pi-style Extension UI aliases have been removed in
favor of the snake_case contract; event JSONL projection now uses the same
snake_case field vocabulary.

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
provider registration, and persisted model-selection behavior remain Product
concerns. Request authentication declarations and credential-to-header
resolution remain AI concerns; Coding does not add an authentication lifecycle.

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
`ExtensionRuntimeBindings`, active-tool policy, prompt rebuilds, session
mutation, and product model/diagnostic interpretation in Coding. The shared
live capability application now belongs to
`harness.session.capabilities`; Coding `ToolController` and
`CommandController` bind Product policy and protocol behavior to that runtime.
Harness `BashExecutionRuntime` owns the standard shell execution, abort,
streaming, and transcript-recording path.

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

Frontmatter parsing lives in `loushang.harness.resources.frontmatter`.
`loushang.resource.frontmatter` remains a legacy top-level path, while
`loushang.coding.frontmatter` is removed and Coding and method internal
consumers import the Harness owner directly.

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

`PackageOperationsRuntime` now owns the shared package session lifecycle
ordering, while `PackageCatalogDiagnosticsRecorder` records typed catalog
diagnostics before Coding's Pi/CLI projection. Coding binds settings scope,
source preparation, resource refresh, materializer policy, and its wire schema;
see [Package Session Operations Boundary](package-session-operations-boundary.md).

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
the `ContextUsageEstimate` result record live under `loushang.harness.context`.
The optional `harness.agent_transcript` profile owns Agent message token
extraction/estimation, model context-window adaptation, usage snapshots, and
threshold decisions. Coding injects its selected compaction policy and summary
strategy rather than rebuilding the accounting.

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
- Freeze Product configuration semantics and model-selection ownership, not neutral
  configuration mechanisms. `ControlConfig` fields, defaults, validation,
  paths, removed-setting compatibility, convenience APIs, diagnostic wording,
  and effect selection/order/callbacks remain Product-owned.
- Do not route `ModelRegistry`, provider registration, persisted model
  selection, or AI request authentication through Harness. Harness neither
  executes shell commands nor stores credentials; command-backed values require
  an injected Product runner.
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
