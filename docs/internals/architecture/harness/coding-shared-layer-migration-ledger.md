# Coding Shared-Layer Migration Ledger

This is the rolling implementation ledger for
[the Coding shared-layer migration plan](coding-shared-layer-migration-plan.md).
It is deliberately a ledger, not a second design document: a wave cannot start
until its source regions, final owners, injection points, and deletion condition
are listed here.

[Coding Shared-Layer Owner Rebaseline](coding-shared-layer-owner-rebaseline.md)
is the Wave R evidence for this ledger. It distinguishes shared mechanisms that
are already adopted from actual Coding duplicates; only the latter may support a
future migration LOC claim.

## Ownership Rules

Move an implementation out of `loushang.coding` when it implements a mechanism,
bridge, public contract, or reusable default and every product difference can be
supplied through a port, profile, callback, or plan. The final owner follows the
kind of capability, not the name of the old package.

Neutral Harness core remains independent from Agent and AI. Declared optional
integration packages, including `harness.session` and
`harness.agent_transcript`, may use stable public Agent and AI value contracts;
they must not own provider registration, credentials, or product model policy.

## Wave 1: Leaf Foundations (Complete)

| Source region | Shared owner | Product injection or retained Coding owner | Status |
| --- | --- | --- | --- |
| `coding.diagnostics.problem_bridge` | `harness.diagnostics.observability_bridge` | Products may supply phase/source resolvers. Coding supplies its `config -> model` source override. | Complete: the Coding bridge was deleted. |
| `coding.diagnostics.debug_status` problem-store formatting | `observability.problem_text` | Coding keeps CLI text and default diagnostic export command. | Complete: reusable formatting has no Coding import. |
| removed `coding.diag_export` archive writer and redaction | `harness.diagnostics.export` | Products may replace the shared `DiagnosticBundleProfile`; Loushang products use the standard archive, manifest, README, artifact set, and diagnostic projection. | Complete: Coding imports the shared bundle operation directly. |
| `coding.source_info` descriptor conversion | `harness.resources.source` | Coding only supplies its resource descriptor values. | Complete: production resource consumers import Harness directly. |
| removed `coding.source_info` executable, package, and Git inspection | `observability.runtime_identity` | `coding.diagnostics.profile` supplies package/module aliases, executable name, and display title through `RuntimeIdentityProfile`. | Complete: Coding has no source-info facade, subprocess, package metadata, or PATH logic. |
| `coding.model_selection` normalization and presentation-neutral ordering | `ai.model` | Coding retains preferred models and Coding persistence wording. | Complete: non-policy consumers import `ai.model`. |
| `coding.model_selection` session model application and discovery | `harness.session.model_selection` | Products inject preferred candidate selection and persistence callbacks. | Complete: Coding is the preferred-candidate adapter. |
| removed `coding.observability` configuration lifecycle | `harness.diagnostics.observability_runtime` over `observability.runtime` | Coding supplies only its `config -> model` diagnostic-source policy. Shared defaults own `.loushang` paths and stable session labels. | Complete: CLI and TUI bind the shared contexts directly. |

Wave 1 contract probes:

- The diagnostics archive writer accepts a product-projected manifest and
  diagnostics, redacts both structured values and text artifacts, and rejects
  unsafe archive member names.
- Runtime identity collection works for a non-Coding package/module pair.
- Session model selection works with a fake session and a caller-supplied
  candidate chooser; it has no Coding import.
- Observability lifecycle configuration restores a pre-existing sink after the
  product context exits.

## Top-Level Work, Diagnostics, And Bootstrap Collapse (Complete)

This batch applies the same ownership test to root-level `coding/*.py` files;
placement at the Product package root does not imply Product ownership.

| Removed or reduced Coding region | Canonical owner | Retained Product input |
| --- | --- | --- |
| removed `work_executor.py`, `work_runtime.py`, `work_shell.py`, and `work.coding` | `work.session.SessionWorkRuntime` composed over the existing `work.WorkRuntime` | `coding.domain.work` supplies `domain="coding"`, `SubmitCodingTurn`, and the Agent-event fact projector. |
| `prompt_command.py` and print/channel/CLI Work bindings | existing `harnesstui.conversation` hosts plus `work.session` | Coding retains its renderer, failure wording, Method metadata preparation, and Product binding names. |
| removed `diag_export.py`, `observability.py`, and `source_info.py` | existing Harness diagnostics and Observability packages | `coding.diagnostics.profile` supplies only source aliases and runtime-identity labels. |
| `sdk_surface.py` | `harness.sdk_surface` inspection algorithm | Coding retains the required public entry-name tuple and default module binding. |
| `bootstrap.py` standard activation effects | existing `harness.session.bootstrap` activation graph and `StandardAgentSessionConfigurationRuntime` | Coding supplies Extension construction, source-identity check, prompt/model/tool/session factories, and Product defaults. |

Implementation accounting, excluding tests and documentation:

- Coding Python: 11,969 to 11,010 LOC, a net reduction of 959 LOC.
- root-level `coding/*.py`: 3,473 to 2,358 LOC, a reduction of 1,115 LOC.
- Work/Prompt Coding region: 867 to 392 LOC, a reduction of 475 LOC.
- diagnostics/source/SDK Coding region: 427 to 127 LOC, a reduction of 300 LOC.
- `coding.bootstrap`: 773 to 567 LOC, a reduction of 206 LOC.
- shared mechanisms added or expanded: approximately 1,110 LOC, giving a
  Coding-deletion/shared-addition ratio of approximately 0.86.

The old Coding files are deleted rather than retained as aliases. Architecture
probes require `work.session`, `harness.sdk_surface`, Harness diagnostics, and
the standard session bootstrap runtime to remain free of Coding imports.

## Root Product Plan And Shared Adapters (Complete)

This batch removes the remaining root-level runtime/capability implementations
without introducing a second resolver, transcript lifecycle, resource loader,
selection runtime, or plain-prompt host.

| Removed or reduced Coding region | Existing or extended shared owner | Retained Product input |
| --- | --- | --- |
| removed `coding.runtime_profile` | `harness.agent_transcript.AgentTranscriptProfileRuntime` composed over the existing runtime resolver/binder, transcript stores/profile, and compaction capability | `coding.product_plan` declares Product IDs, metadata key, store/profile implementation identities, and current defaults. |
| removed `coding.capability_plan` | existing `harness.capabilities.composition_runtime` via `standard_capability_composition_plan` | `coding.product_plan` selects the standard composition profile; future Coding deltas remain declared Product data. |
| `coding.session_manager` runtime binding | the shared Agent transcript profile runtime | Coding retains session-root and persistence decisions plus restored-header Product validation. |
| `coding.model_selection_tui` | existing `harness.session.model_selection` and `harnesstui.selection` catalog/runtime | Coding retains preferred-model policy, settings persistence, and its persistence-warning wording. |
| `coding.resource_runtime` | existing `ResourceLoader` through `ResourceLoaderProfile` and `ProfiledResourceLoader` | Coding retains built-in package identity, context-file compatibility names, prompt assembly, package security policy, and default loader choice. |
| duplicated helpers in `coding.prompt_command` and HarnessTUI plain mode | existing `harnesstui.conversation.plain_prompt_host` | Coding retains Work/Method preparation, renderer, Product diagnostics, and final wording. |
| `coding.tool_pack` audit | existing Harness workspace tool factories and contribution/activation runtimes | Retained in Coding: the file is Product membership/order, descriptions, prompt snippets, downloader default, policy, approval, diagnostics, and execution-service binding. No duplicate shared tool engine was added. |

Implementation accounting, excluding tests and documentation:

- Coding Python: 11,007 to 10,363 LOC, a net reduction of 644 LOC.
- root-level `coding/*.py`: 2,358 to 1,708 LOC, a reduction of 650 LOC.
- removed runtime/capability implementations: 404 LOC, replaced by the
  38-line declarative `coding.product_plan`.
- `coding.model_selection_tui`: 165 to 38 LOC.
- `coding.resource_runtime`: 154 to 95 LOC.
- `coding.prompt_command`: 324 to 251 LOC.
- shared implementation added or expanded: 761 lines and 69 lines removed,
  including the reusable Agent transcript binding, for a Coding-deletion/shared-
  addition ratio of approximately 0.85.

Product-neutral probes bind `research`/`design` transcript, capability,
resource, model-selection, and plain-prompt adapters without importing Coding.
The old Coding implementations are deleted rather than retained as facades.

## HarnessTUI Conversation Product Binding Collapse (Complete)

This batch removes the remaining Coding-owned copies of the standard
conversation interaction and Agent presentation bindings. It extends existing
HarnessTUI owners rather than introducing a second controller, action host,
history projector, tool projector, surface workflow, or model selector.

| Removed or reduced Coding region | Existing or extended shared owner | Retained Product input |
| --- | --- | --- |
| removed `coding.interaction.intent` | `harnesstui.conversation.intents` | Coding adds no private grammar; future Product intents can be composed at the Product boundary. |
| removed `coding.interaction.controller`, `screen_host`, and `tui_profile` | existing `harnesstui.conversation.controller`, `host`, `action_presentation`, and `info` | `coding.ui.product_binding` injects the command catalog, callbacks, logger, problem prefix, and Product copy. |
| removed `coding.presentation.tui.screen` and `tool_transcript` | optional `harnesstui.conversation.agent_binding` over the existing neutral history, tool, plain, and screen projectors | Coding retains its renderer/glyph profile and attachment-to-AI conversion. |
| reduced `coding.presentation.tui.history` and removed `coding.presentation.session` | `harnesstui.conversation.agent_binding` and `session_view` | Coding retains only persisted SessionManager history loading. |
| standard command/model/settings surface construction | existing `harnesstui.surface` and `harnesstui.selection` profiles/factories | Coding retains settings fields, terminal diagnostics, approval UI, model-application callback, and Product subtitle. |

Closure probes require:

- the neutral conversation modules to remain free of Agent, AI, and Coding
  imports while the optional Agent binding remains free of Coding imports;
- Coding UI construction to use the shared controller, routing profile, local
  action registry, action host, history/tool projectors, and surface factories;
- deleted Coding modules to remain absent rather than returning as compatibility
  re-exports;
- prompt, command, model, queue, retry, compaction, history, tool transcript,
  plain-mode, and screen-mode behavior tests to remain unchanged.

Implementation accounting, excluding tests and documentation:

- Coding Python: 10,363 to 9,520 LOC, a net reduction of 843 LOC.
- Coding source changes delete 1,153 lines and add 310 lines, including the
  96-line Product binding; nine duplicate implementation modules are removed.
- HarnessTUI Python: 15,728 to 16,739 LOC, a net increase of 1,011 LOC.
- Shared source changes add 1,014 lines and remove 3 lines. The additions are
  contracts and compositions over existing owners, not replacement engines.
- Across Coding and HarnessTUI production Python, the batch adds 168 net lines
  while moving the reusable ownership out of Coding.

## Wave 2: Event And Extension Product Adapter Collapse (Complete)

The detailed contract is
[Event And Extension Product Adapter Collapse](event-extension-adapter-collapse-boundary.md).
This is an adapter-collapse Wave, not a mandate to move Coding wire contracts
into Harness.

| Source region | Shared owner | Product injection or retained Coding owner | Deletion condition |
| --- | --- | --- | --- |
| removed `coding.extensions.hooks.HookDispatcher` | `harness.extensions.agent.hooks.ExtensionToolHookDispatcher` | Product supplies context factory and runtime error projection. | Complete: Coding module deleted after focused Agent-hook equivalence tests and a no-Coding-import probe. |
| Agent prompt/context/session-decision reducers formerly in `coding.extensions.runner.ExtensionRunner` | `harness.extensions.agent.hooks` and `harness.extensions.session_runtime` | Coding supplies bound context, CWD, API binding, `before_agent_start` factory/result coercer, and session-decision coercer. | Complete: shared dispatchers own the reducer mechanics; Coding retains provider behavior and Product coercers. |
| removed `harness.session.extension_{hooks,events,input}` modules | `harness.extensions.agent.{hooks,lifecycle,input}` | Session only consumes the profile during Agent-session composition. Input receives normalized typed requests plus queue/delivery ports; lifecycle is an observation-only extension callback adapter with injected clock/correlation values; Coding retains wire parsing/defaults. | Complete: consumers import the profile directly, input has no Session import, and Session no longer re-exports the profile. |
| `coding.extensions.runner.ExtensionRunner` loader/API portions | Coding adapter over `harness.extensions.runner.ExtensionRunner` | `ExtensionAPI`, policy resolver, loader configuration, provider actions, and Coding error dictionary remain Product-owned. | Complete: the Coding runner is a thin loader/policy binding; shared reducer and dispatch mechanics live in Harness with snake_case-only extension events. |
| `coding.event` runtime projection, views, serializer, and presentation policy | `harness.events.session_types`, `session_projection`, `runtime_views`, `recording_policy`, and `session_serialization` | Coding retains `AgentSessionEvent`, Product/Work mapping, rendering, and final wording. Harness owns runtime-view selection/stream shaping, delivery hints, transcript-write decisions, and cancellation classification. The shared wire schema is snake_case-only; no duplicate neutral event engine exists. | Complete: production consumers use the Harness implementations; Coding keeps only established thin import facades and no Pi/camelCase aliases. |

Wave 2 contract probes:

- a fake Product executes context, before/after tool, before-agent-start, and
  session-decision hooks with no Coding import;
- invalid hook results, route ordering, block behavior, and runtime failure
  reporting preserve existing diagnostics;
- Coding extension provider actions remain unchanged; JSON/print/RPC event
  projections use the canonical snake_case fields;
- architecture tests forbid Coding imports from the new shared dispatchers and
  forbid a second event schema or alias layer;
- `harness.extensions.agent` has no `harness.session` import, while neutral
  `harness.extensions` modules do not eagerly import or re-export the Agent
  profile; lifecycle callback order and timestamps are deterministic under an
  injected clock.

## Wave 4, Slice A: Agent Session Adapter Collapse (Complete)

The detailed boundary is
[Session Agent Runtime Boundary](session-agent-session-boundary.md).

| Source region | Shared owner | Product injection or retained Coding owner | Deletion condition |
| --- | --- | --- | --- |
| `coding.session.agent_session` composition and operation coordination | `harness.session.composition`, `harness.session.operations_runtime`, and `harness.session.agent_adapter` | Coding supplies model restoration, resource/package policy, provider/footer behavior, compaction and branch-summary executors, replacement validation, and Product callbacks. | Complete: after an integration merge reintroduced direct assembly, `AgentSession` was restored from 1,732 to 522 lines; the shared modules have no Coding import. |

Wave 4, Slice A closure probes:

- AgentSession, retry, export, and tool regressions pass without changing the
  public session or RPC surface;
- Harness owns resource watching, command/preflight forwarding, extension
  lifecycle, event dispatch, approval lifecycle, transcript export, and
  composed-session initialization;
- a source-level architecture probe rejects `loushang.coding` imports from
  the new session adapter modules;
- the Coding implementation reduction is 70.5% (1,219 of 1,729 lines), with
  the remaining code limited to the product responsibilities listed above;
- the implementation diff deletes 1,399 Coding lines and adds 1,949 shared
  Harness lines (a 0.72 deletion/addition ratio); tests and documentation are
  excluded from this accounting.

## Later Waves

Wave 3's initial command-handler cutover is implemented in
[Standard Session Command Pack Boundary](session-command-pack-boundary.md).
The remaining rows are intentionally broad until their waves are scheduled.
They are not estimates or approval to duplicate an existing Harness owner.

| Wave | Source regions to ledger before implementation | Intended shared owners |
| --- | --- | --- |
| 3 | `coding.session.builtin_commands` admitted subset (`session`, `name`, `export`, `import`, `compact`, `reload`, `new`, `resume`, `fork`, `clone`, `tree`); `coding.session.command_controller` standard-source forwarding; command descriptor and result projection helpers | `harness.session.command_pack`, existing `harness.session.SessionCommandRuntime`, `harness.commands`, and `harness.extensions.commands` |
| 4 | `AgentSession`, runtime composition, bootstrap activation | existing `ProductRuntimePlan`, runtime resolver/binder, `harness.session` |
| 5 | RPC, print, channel host, shared conversation interaction | `channel`, `harness.session`, `harnesstui`, `tui` |
| 6 | Config composition, common defaults, CLI and Work/Method bridges | `harness.config`, `ai`, `work`, `method`, `tui` |

Each later row must be expanded to the same level as Wave 1 before code changes
begin. A product facade is not complete until the old implementation is deleted
or reduced to declared product data and ports.

### Wave 5 Scope Gate: Session RPC Operations

The detailed boundary is [Session RPC Operation Cutover Boundary](session-rpc-operation-boundary.md).

| Source region | Shared owner | Product injection or retained Coding owner | Deletion condition |
| --- | --- | --- | --- |
| JSONL command registry and unknown-command fallback | `channel` | Coding registers its RPC methods and projects its legacy error frame. | Complete: `JsonlCommandRouter` has no Harness/Coding import or wire-schema defaults. |
| Prompt task lifetime and standard session-operation invocation | `channel` task tracking plus existing `harness.session.SessionOperationRuntime` | Coding parses aliases, acknowledges preflight, and projects errors/results. | Pending: admitted handlers delegate through bound ports with no duplicate operation executor. |
| RPC model/auth, package, bash, extension UI, event, state, and transcript handlers | Coding | Product policy and public wire contract. | Retained by design. |

### Wave 3 Scope Gate

| Source region | Shared owner | Product injection or retained Coding owner | Deletion condition |
| --- | --- | --- | --- |
| Shared command descriptor contract and resource/extension projection | `harness.commands` and `harness.extensions.commands` | Coding retains builtin command data, descriptor ordering, and source priority. | Complete: generic descriptor types and resource/extension projections have no Coding import. |
| Descriptor construction for the admitted standard command subset | `harness.session.list_standard_session_command_descriptors` | Coding selects the bound capability ports; standard descriptions and ordering are Harness-owned. | Complete: Coding no longer owns a standard slash-command definition list. |
| Parsing and typed result adaptation for the admitted subset | `harness.session.command_pack` over existing session identity, export/import, operation, lifecycle, and navigation runtimes | Coding supplies ports and wraps the neutral mapping in `CommandExecutionResult`. | Complete: `coding.session.builtin_commands` is deleted. |
| Ordered composition and dispatch | existing `harness.session.SessionCommandRuntime` plus `harness.session.command_sources` | Coding binds extension runner, diagnostics mapping, result projection, and builtin source. | Complete: no second dispatcher or catalog is introduced; extension/resource source adapters have no Coding import. |
| Clipboard, tool/extension rendering, changelog, settings/model/terminal/hotkeys/quit/share | Coding or their already declared future owner | Product wording, rendering, model/auth/provider policy, and UI routes. | Not in Wave 3; no LOC is counted as migrated. |

Wave 3 closure probes:

- a fake Product executes every admitted command through public Harness ports
  with no Coding import;
- invalid invocations and unavailable existing capability groups return typed
  results before a Product port is called;
- standard, extension, and resource sources preserve current priority and
  dispatch order through the existing `SessionCommandRuntime`;
- Coding preserves its catalog and result fixtures after projecting the shared
  result, then deletes the admitted duplicate handlers;
- `harness.session.command_pack` has no Coding, provider/auth, transport, or
  UI import.

### Wave 4 First Slice: Product Transcript Lifecycle Store (Complete)

| Source region | Shared owner | Product injection or retained Coding owner | Deletion condition |
| --- | --- | --- | --- |
| removed `coding.runtime.agent_session_runtime._CodingSessionLifecycleStore` | `harness.session.ProductTranscriptSessionLifecycleStore` | Coding supplies transcript create/restore/fork/dispose ports, CWD restore validation, session construction, fork selection, lifecycle hooks, and extension/diagnostic behavior. | Complete: Harness owns the common transcript-to-runtime lifecycle adapter and releases a transcript when Product runtime construction fails. |
| proposed bootstrap transaction | existing `ConfigActivationRuntime` and capability/session runtimes | Coding retains activation callbacks, Product services, prompt/model/resource/tool policy, CWD/session-file acceptance, and final session construction. | Deferred: no second bootstrap engine is admitted while the existing activation runtime owns ordering and rollback. |

Wave 4 first-slice accounting: `coding.runtime.agent_session_runtime` is 1,187
to 1,158 LOC (-29); `harness.session.transcript_lifecycle` is 216 to 371 LOC
(+155). Tests and documentation do not count as migrated implementation.

Wave 4 first-slice probes:

- a fake Product creates and forks a runtime session through the shared store
  without importing Coding;
- failed Product runtime construction disposes the opened transcript;
- Coding lifecycle, bootstrap, and import-boundary regressions preserve CWD,
  fork, extension, and diagnostic behavior.

### Session Adapter Cull And RPC Lifecycle Port (Complete)

The requested public-facade and RPC audit confirms that most of the proposed
cutover already landed in earlier waves. Prompt, queue, abort, compaction, and
retry handlers already use `SessionOperationRuntime`; moving them again would
create a duplicate engine. The remaining lifecycle handlers now use explicit
Harness `SessionLifecycleOperationPorts`, while Channel continues to own JSONL
framing and Coding retains validation, error wording, compatibility fields, and
response projection.

| Source region | Actual change | Ownership result |
| --- | ---: | --- |
| `coding.session.agent_session` | 1,890 to 1,874 LOC (-16) | Removed only `abort`, `compact_session`, and bash state aliases that forwarded Harness methods. Coding compaction, bash, diagnostics, package, model, extension, and event behavior remains Product-owned. |
| `coding.mode.rpc_mode` | 2,739 to 2,758 LOC (+19) | Added explicit lifecycle port binding; no RPC capability was deleted. The increase is intentional wiring, not a migration reduction. |
| `harness.session.operations` | shared port/runtime contract | Owns neutral lifecycle callback dispatch for Product hosts. |

This wave's net Coding reduction is 0 after the explicit RPC binding is
included. The earlier 800--1,200 LOC projection is superseded by this audit;
future reduction must come from a separately proven handler or Product adapter
removal, not from reclassifying existing Harness calls.

The lifecycle port now also exposes `clone_session` explicitly. RPC hosts use
that capability when available; the Coding adapter keeps a fallback to the
existing fork-at-current-position operation for older runtime implementations.
This makes clone part of the neutral operation grammar without changing the
Coding wire contract.

### Session Tool, Bash, And Provider Collapse (Complete)

The standard command pack now owns `tools`, `extensions`, `copy`, and
`changelog` parsing/execution. Coding supplies tool/extension data, clipboard
implementation, changelog content, and the final Product result projection.

`ToolActivationProfile` owns default tool selection and new-tool activation.
`SessionToolRuntime` remains the live rebinding mechanism; Coding only supplies
its preferred order, builtin set, and activation policy.

`BashExecutionRuntime` now owns the native Harness command-execution surface.
The Coding `BashController` and its Pi-style `execute_pi_style` and
`record_pi_style_result` entry points were removed. Native extension `user_bash`
interception remains an injected Coding extension policy callback and receives
only the typed native result shape.

`ExtensionProviderRuntime` owns provider register/unregister/query lifecycle in
Harness. Coding retains only the AI-native provider configuration conversion;
provider registration, API source cleanup, and runtime lookup are shared.

### Session Composition, Bootstrap, Settings, And CLI Lifecycle (Complete)

The following implementation-only surfaces now have shared owners without
moving Coding content or command syntax:

| Source region | Shared owner | Coding retained |
| --- | --- | --- |
| `coding.runtime.agent_session_runtime` lifecycle forwarding | `harness.session.SessionLifecycleOperationAdapter` | CWD/session-file acceptance, fork policy, Coding hooks, diagnostics, and resource policy |
| `coding.bootstrap` resource activation ordering and contained diagnostics | `harness.bootstrap.ResourceBootstrapRuntime` and `BootstrapActivationRuntime` | Resource loader, extension factory, flags, prompt/tool rebuild, and Product diagnostics callbacks |
| removed `coding.control.settings_manager` and `coding.control.types` | `harness.config.agent.SettingsManager` and standard Agent settings records over the existing `SettingsRuntime` / `ScopedConfigRuntime` / `LayeredConfig` chain | Coding settings paths, command-backed value execution, `ModelRegistry`, and Product-only policy/presentation |
| `coding.cli.__main__` stream binding, output guard, and disposal fallback | `channel.ProductHostLifecycle` | Argument grammar, mode selection, Product startup policy, output format, and command handlers |

These are adapter collapses rather than new protocol layers. Harness and Channel
do not import Coding, and no RPC/CLI wire fields changed in this wave. The
lifecycle contract is verified with independent Harness/Channel fakes plus the
existing Coding settings and CLI regressions.

### Wave 6, Slice B: Generic Product CLI Surfaces (In Progress)

The detailed boundary is [Product CLI Lifecycle Boundary](../channel/product-cli-lifecycle-boundary.md).
This slice extracts only object-shape and lifecycle mechanisms. It does not move
Coding argument grammar, mode selection, package/work/method handlers, product
wording, or RPC schemas.

| Source region | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| repeated prompt/print/mode turn loops and TTY probing | `channel.ProductHostLifecycle` | Turn values, runner selection, output, and disposal candidates | Complete |
| prompt/stdin/file/image input resolution | `harness.host.prompt_input` | CLI argument grammar and product prompt policy | Complete |
| model listing normalization and metadata formatting | `harness.session.model_selection` | Preferred model candidates and persistence wording | Complete |
| command descriptor listing projection | `harness.commands.project_command_descriptor` | Descriptor source selection and JSON/TSV output | Complete |
| skill/plugin/session catalog listing projections | `harness.resources.*`, `harness.agent_transcript.catalog` | Discovery, settings, query grammar, and output format | Complete |
| diagnostic record/error/summary serialization | `harness.diagnostics.serialization` | Existing call sites only; camelCase output retained | Complete |
| package catalog and materialization record projection | `harness.resources.packages.projection` | Coding retains resource discovery, materializer policy, and command selection | Complete |

Slice B accounting (implementation only): `coding.cli.__main__` is 3,358 to
2,941 LOC (-417); the former Coding diagnostics serializer is deleted (83 LOC);
the shared mechanisms add approximately 890 LOC across Channel/Harness. The
deletion/addition ratio is approximately 0.71. Tests and documentation are not
counted. The lower ratio is intentional: this slice establishes reusable
contracts and does not delete product handlers or CLI grammar.

### Slice B implementation follow-up: standard operation leaves

The following additional leaves are now shared without changing Coding's
argument grammar, operation order, security policy, or output fields:

| Coding source mechanism | Shared owner | Product injection or retained Coding owner | Status |
| --- | --- | --- | --- |
| resource enable/disable and plugin-source toggle mutation | `harness.cli.resource_toggles` | Coding supplies `PackageSecurityPolicy`, remote-source labeling, and diagnostic capture | Complete |
| asynchronous package install/materialize/update/remove/uninstall orchestration | `harness.cli.package_lifecycle` | Coding supplies install-source policy and JSONL serialization | Complete |
| session command invocation, slash normalization, result extraction, and raw/JSON formatting | `harness.cli.command_execution` | Coding supplies CLI argument values and stream/error projection | Complete |
| new/restore/continue/fork session selection | `harness.cli.session_resolution` over `harness.session` lifecycle ports | Coding supplies parsed CLI values and product runtime | Complete |
| `provider/model`, `provider:endpoint:model`, and explicit provider+model parsing | `loushang.ai.model.parse_model_selection_reference` | Coding retains preferred model candidates and persistence wording | Complete |
| extension flag discovery and application | `harness.cli.extension_flags` | Coding retains second-pass argparse typing and help text | Complete |
| Method catalog normalization, lookup, plan projection, and text/JSON formatting | `harness.cli.method_listing` | Coding supplies discovery and `MethodCompiler(domain="coding")` callbacks | Complete |
| Work event-log inspection, tailing, plan projection, and text/JSON formatting | `loushang.work.cli` | Coding retains CLI flag grammar and Work runtime binding | Complete |

After these leaves, the implementation-only `coding.cli.__main__` count is
1,994 lines (2,941 at the start of this follow-up). The remaining CLI code is
deliberately not counted as shared yet: Method/Work preparation, Coding
resource discovery and package materialization policy, mode selection, prompt
policy, approval/tool setup, and final product/TUI/RPC projection still carry
product semantics or require an explicit owner decision.

The shared operation modules have independent fake-capability probes under
`tests/harness/cli`. They return typed results and leave wire formatting to the
Product host; no second session, package, or transport engine is introduced.

Closure probes:

- CLI/model/prompt/channel regressions preserve existing output and lifecycle
  behavior;
- Harness/Channel modules have no Coding import;
- malformed resource and command objects remain best-effort and are skipped as
  before;
- diagnostic JSON retains the existing field names; any snake_case protocol
  change requires explicit approval in a later contract migration.

### Wave 6, Slice C: Shared Workspace Policy Engine (Complete)

`coding.policy.engine` was an implementation duplicate over the existing
Harness policy subjects, matchers, command normalization, and rule evaluator.
The evaluator now lives in `harness.policy_engine.PolicyEngine` and accepts a
product rule-id namespace plus product-supplied rule values. Coding retains a
thin `PolicyEngine` binding that preserves its historic `coding.*` rule ids and
default policy values; no decision codes, messages, or tool behavior changed.

| Source region | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| `coding.policy.engine` rule assembly and action/tool evaluation | `harness.policy_engine.PolicyEngine` | Product namespace binding and policy defaults | Complete |

Slice C accounting: the Coding implementation shrank from 298 to 17 LOC
(-281); Harness gained the shared implementation at 300 LOC. The shared module
has no Product imports. Coding policy and workspace-tool regressions remain
covered by the existing tests, with independent Harness probes for non-Coding
rule namespaces.

The same slice also collapsed the callback-backed approval lifecycle. The
`ApprovalBroker` wrapper, presenter lifecycle, timeout/cancellation behavior,
and result correlation now live in `harness.approval.InteractiveApprovalResolver`.
Coding keeps only its `action`/`risk` payload projector and a thin subclass:

| Source region | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| `coding.policy.approval.InteractiveApprovalResolver` | `harness.approval.InteractiveApprovalResolver` | Coding approval payload fields | Complete |

Approval accounting: Coding shrank from 135 to 56 LOC (-79); Harness gained
104 LOC of parameterized lifecycle and presenter code. Existing Coding approval
tests and independent Harness policy probes pass; the shared approval module has
no Product imports.

Package source trust evaluation is also now a shared resource capability. The
`PackageSecurityPolicy` and `PackageSourceSecurityReport` types moved to
`harness.resources.packages.security`; Coding only re-exports them while it
continues to choose when a package operation asks for a security decision.
This keeps trusted-host/source configuration injectable for Design, PPT, and
other Products without changing the existing package wire shape.

### Wave 6, Slice D: Session Observability Binding (Complete)

The repeated CLI/session observability binding now lives in
`harness.diagnostics.observability_runtime`. It owns scope parsing, explicit or
environment-derived output paths, startup/session labels, sink binding, and
debug enable/disable lifecycle. Coding keeps only its source classification
(`config` problems are presented as `model`); the historic wrapper module has
now been deleted.

| Source region | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| removed `coding.observability` session/startup context and debug file lifecycle | `harness.diagnostics.observability_runtime` | Coding diagnostic source mapping | Complete |

Slice D initially reduced the adapter from 157 to 109 LOC; the top-level
collapse later deleted the remaining 109 LOC and bound CLI/TUI directly to the
shared context. No debug/trace environment variables or file naming behavior
changed.

### Wave 6, Slice E: Top-Level Session Bootstrap Leaves (Complete)

Several top-level Coding helpers were implementation-only session mechanics,
despite being located beside the Product bootstrap entry point. They now live
under the Harness session package and accept only neutral values or existing
Harness ports:

| Source region | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| preferred model detail/selection matching and candidate ordering | `harness.session.model_preferences` | `PREFERRED_CODING_MODELS` and the settings persistence binding | Complete |
| cwd/project/resource consistency audit | `harness.session.cwd_audit` | Coding settings/resource object extraction and diagnostic capture | Complete |
| no-tools normalization and initial tool activation selection | `harness.session.bootstrap_utils` | Product bootstrap argument wiring | Complete |
| resource prompt override lookup and fragment assembly | `harness.session.bootstrap_utils` | Product default prompt and resource content | Complete |
| scoped model/thinking suffix parsing | `harness.session.bootstrap_utils` | Product model registry lookup and payload assembly | Complete |

This is a leaf extraction, not a second bootstrap runtime. Harness does not
construct Coding services or sessions; it only exposes reusable value-level
operations. Coding's public import names remain available while their
implementation ownership moves to Harness.

Slice E accounting: Coding shrank by approximately 178 implementation lines
(`bootstrap.py` 1,381→1,315 and `model_selection.py` 137→67 in this slice),
while Harness gained approximately 312 lines plus focused Harness probes.
Existing Coding model/bootstrap behavior is unchanged; the new Harness tests
exercise the same operations without importing Coding.

### Wave 7, Slice A: Agent Bootstrap Construction Collapse (Complete)

The Agent construction boundary is now explicit in `harness.session.bootstrap`.
Harness owns the neutral construction request/result contracts and the shared
pipeline that:

1. builds the initial Agent state and constructor kwargs;
2. creates a workspace registry when requested;
3. registers Product-provided extension tools;
4. records extension diagnostics through a Product callback;
5. resolves initial active tools; and
6. invokes the Product session factory.

Coding retains the service factories, resource/extension policies, model
resolution, prompt defaults, image policy, approval binding, and the concrete
`AgentSession` constructor. No Coding type is imported by the Harness module,
and no second session runtime was introduced.

| Source region | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| bootstrap service/result data contracts | `harness.session.bootstrap` | Product-specific service types supplied as generic values | Complete |
| Agent initial state and constructor kwargs | `AgentBootstrapRuntime` | Agent factory selection and Product session factory | Complete |
| tool registry/extension contribution/active-tool pipeline | `AgentSessionConstructionRuntime` | Extension pack IDs, diagnostics normalization, and tool policy | Complete |

Slice A accounting: `coding/bootstrap.py` is approximately 1,315→1,277 LOC;
the shared construction contracts/runtime add approximately 240 LOC. The
reduction is intentionally limited to the construction boundary: the
remaining bootstrap code is activation policy and Product service wiring,
which cannot move without changing ownership or duplicating the existing
resource activation runtime. Independent Harness construction probes and the
Coding bootstrap/session regression suite pass.

### Wave 7, Slice B: Model and Provider Resolution Collapse (Complete)

Model catalog mechanics are now owned by `harness.model_catalog`. The shared
catalog wraps the existing AI registry types without changing `loushang.ai`:
layered builtin/user/project loading, provider/model registration, reference
resolution, endpoint selection, and model construction are all reusable by
other Products. Coding keeps only the historical import name as a zero-logic
alias and continues to provide its preferred model list and Product defaults.

Session bootstrap resolution also moved to explicit Harness operations in
`harness.session.model_resolution`. It provides default-model fallback,
stable failure classification, startup diagnostic recording, and scoped
model/thinking pattern projection through typed callbacks. No runtime
capability is discovered through `getattr`; Products bind the catalog and
diagnostics ports explicitly.

| Source region | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| `coding.control.model_registry` registry/reload/resolve/build implementation | `harness.model_catalog` | public zero-logic import alias | Complete |
| bootstrap default-model fallback and failure diagnostics | `harness.session.model_resolution` | model preference/default selection | Complete |
| enabled model/thinking pattern parsing and scoped payload assembly | `harness.session.model_resolution` | Product settings wiring | Complete |

Slice B accounting: `coding/control/model_registry.py` shrank from 176 to 5
LOC and `coding/bootstrap.py` from approximately 1,277 to 1,178 LOC. Harness
gained the shared catalog and resolution helpers, with no changes to
`loushang.ai.model` and no external wire behavior changes. Focused Coding
regressions and independent Harness model-resolution probes pass.

### Wave 7, Slice C: Session Public Adapter Audit (Already Complete)

This requested slice is already present in the integration baseline and must
not be repeated as a second migration. Commits `7c8fb1e1` and `808767a0` moved
the common session facade, inspection, retry, transcript export, tool,
extension, lifecycle, and maintenance coordination to Harness. The current
`coding.session.AgentSession` is 522 LOC, down from approximately 1,732 LOC;
its remaining code is composition wiring and Product behavior.

| Remaining AgentSession region | Owner | Classification |
| --- | --- | --- |
| model/provider binding and preferred selection | Coding + Harness/AI ports | Product policy binding |
| resource/package/tool contribution wiring | Coding resource policy + Harness runtimes | Product adapter |
| compaction and branch-summary callbacks | Coding | Product prompt/executor semantics |
| extension provider/footer/replacement callbacks | Coding + Harness extension ports | Product API and presentation |
| context-usage camelCase projection | Coding public projection | Transform, not a pure forwarder |

The audit found no remaining 600–900 LOC block that is both pure forwarding and
safe to delete. Removing these methods would either change the public Coding
projection or move Coding-specific prompt, provider, footer, cwd, package, or
extension semantics into Harness. Therefore this slice has **0 additional
LOC** and is accepted by existing session architecture gates rather than being
artificially expanded. The next large reduction should target Settings
Composition or CLI Product Host, where shared mechanisms still have separate
owners.

### Wave 7, Slice D: Model Selection TUI Runtime (Complete)

The model-selection UI flow was a second copy of generic terminal interaction:
filtering, completion projection, palette resolution, cancellation, ambiguity
presentation, and the final apply-result message. Those operations now live in
`harnesstui.selection.runtime` behind the explicit
`ModelSelectionViewPort` contract. The port supplies normalized
`ModelChoice` values, the current value, and an apply callback; it does not
expose a Coding session or discover capabilities dynamically.

Harness owns the AI/model-value projection and standard session acquisition;
HarnessTUI owns endpoint/detail view projection over its existing selection
catalog and interaction runtime. Coding retains preferred-model policy,
settings persistence, and persistence-warning wording. Its module contains
only those Product bindings; no generic interaction, acquisition, or selection
runtime is duplicated there.

| Source region | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| model list filtering, completion, palette resolution and result presentation | `harnesstui.selection.runtime` | Product persistence warning | Complete |
| model-selection apply/persistence boundary | `ModelSelectionViewPort` | `apply_model_selection` and warning policy | Complete |
| model details, endpoint identity and current-session projection | `harness.session.model_selection` and `harnesstui.selection.binding` | preferred-model policy | Complete |

Slice D final accounting: `coding/model_selection_tui.py` shrank from 279 to
38 LOC (-241), including 127 LOC in this follow-on. Harness owns the AI-aware
session data contract; HarnessTUI converts those records into view models by
extending the existing selection binding rather than creating another runtime.
HarnessTUI has no direct AI import, no shared module imports Coding, and
independent fake-Product probes cover acquisition, endpoint identity,
completion, and application.

### Wave 7, Slice E: CLI Standard Operation Host (Complete)

Coding previously repeated the same capability call, error projection, output
write, and early-return loop around shared CLI leaf operations. The reusable
host behavior now lives in `harness.cli.host_operations`, while
`CliOperationSequence` owns ordered sync/async early-exit dispatch.

| Source region | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| session catalog query validation, projection and output | `harness.cli.host_operations` | query values and selected format | Complete |
| export, model/command/diagnostic/skill/plugin list execution | `harness.cli.host_operations` | operation enablement and declared order | Complete |
| resource toggle and package lifecycle CLI result/error writing | `harness.cli.host_operations` | package security and diagnostic callbacks | Complete |
| command invocation CLI result/error writing | `harness.cli.host_operations` | command arguments and result-format choice | Complete |
| first-handled standard operation dispatch | `harness.cli.CliOperationSequence` | Product stage selection, insertion and order | Complete |
| TTY selection, output guard, launch conflicts and runtime-mode projection | `harness.cli.CliLaunchPlan` | `CliArgs` to plan projection | Complete |

Coding still owns Method visibility, package catalog fallback, diagnostics
archive export, argument grammar, bootstrap policy, Work binding, and final
mode selection. These are not hidden behind a compatibility facade.

Slice E accounting (production implementation only):
`coding/cli/__main__.py` changed from 1,994 to 1,725 LOC. The diff removes 575
Coding lines and adds 306 lines of request/stage/plan declaration, for a net
Coding reduction of 269 LOC. Harness adds approximately 601 production lines
across the operation host, launch plan, sequence runtime, and public exports,
giving a gross deleted/shared-added ratio of approximately 0.96. Tests and documentation are
excluded from the ratio. The detailed boundary is documented in
`cli-product-host-collapse.md`; the complete Coding CLI and independent Harness
CLI suites remain green with unchanged operation precedence, output, and exit
codes.

### Wave 7, Slice F: Standard Agent Settings Profile (Complete)

The former Coding settings manager already delegated its storage and
transaction mechanics to `SettingsRuntime`, `ScopedConfigRuntime`, and
`LayeredConfig`, but Coding still owned every standard Agent setting record,
field codec, getter, setter, and collection mutation. These reusable surfaces
now live in the optional `harness.config.agent` profile. The profile composes
the existing config stack and does not introduce another settings engine.

| Source region | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| standard Agent settings records and defaults | `harness.config.agent.types` | Product-only additions and overlays | Complete |
| standard field codecs, validation, getters, setters, and mutations | `harness.config.agent.SettingsManager` | none | Complete |
| layered load/merge/persist/reload, snapshots, listeners, issue drain | existing `harness.config` runtimes | none | Reused, not duplicated |
| settings paths and command-backed value execution | Coding | `.loushang/coding` path and shell-runner policy | Retained |
| model catalog policy | Coding/AI | preferred models and Product selection policy | Retained |

The neutral config core remains free of Agent and AI imports. Only the explicit
`config.agent` profile admits stable Agent/AI value types, and the entire config
package remains free of Coding imports. Production Coding consumers now import
the shared settings owner directly; `coding.control` retains only its public
export identity alongside Product-owned control services.

Slice F accounting (production implementation only): the deleted Coding
implementation was 1,580 LOC (`settings_manager.py` 1,403 plus `types.py` 177).
The shared profile contains 1,640 LOC including its 59-line public export, a
gross deleted/shared-added ratio of 0.96. Coding Python fell from 15,737 to
14,157 LOC. The behavior suite moved to the shared owner and the broader config,
Coding control/package, and architecture regression completed with 211 passing
tests.

### Wave 7, Slice G: Agent Session Lifecycle Binding Collapse (Complete)

The remaining Coding runtime still repeated standard Agent Product effects
around the already shared `ProductSessionRuntime`. Those effects now extend
their existing owners; no `AgentProductSessionRuntime` or second lifecycle
engine was introduced.

| Source region | Existing shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| after-commit index/replacement callbacks and restore/import failure routing | `ProductSessionRuntime` | none | Complete |
| standard transcript create/open/fork/dispose/rename/delete binding | `ProductTranscriptSessionBinding` | `SessionManager` selection | Complete |
| approval, runtime-host, extension switch/fork/start/shutdown, and disposal hooks | `AgentSessionAdapterMixin` lifecycle-hook builder | none | Complete |
| session diagnostic capture with structured details | `SessionDiagnosticsRuntime` | diagnostic service injection | Complete |
| Agent message `at`/`before` fork target and selected-text projection | `ProductSessionRuntime` Agent transcript helper | Coding default position | Complete |
| missing cwd public exception | Harness validation plus Coding translator | Coding public error type | Retained |

Slice G accounting (production implementation only):
`coding/runtime/agent_session_runtime.py` shrank from 639 to 229 LOC (-410,
64% source compression). Total Coding Python fell from 14,156 to 13,746 LOC.
The shared changes extend existing session, transcript, diagnostics, and Agent
adapter modules rather than adding a synonymous runtime. Independent Harness
bindings and the complete Coding Agent-session characterization suite preserve
fork, cwd, import, extension ordering, replacement, index, and diagnostic
behavior.

### Wave 7, Slice H: Bootstrap Activation Collapse (Complete)

The remaining Coding bootstrap repeated the standard Agent activation graph
and several leaf bindings. The graph now composes the existing Harness
activation, resource, package, diagnostics, transcript, and model-catalog
owners. No second bootstrap, session, resource, or lifecycle engine was added.
The detailed boundary is
[Bootstrap Activation Collapse Boundary](bootstrap-activation-collapse-boundary.md).

| Source region | Existing shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| seven-stage Agent startup ordering and first-failure propagation | `BootstrapActivationRuntime` plus `standard_agent_session_activation_plan` | seven Product effect callbacks | Complete |
| standard resource/extension/diagnostic port binding | `create_standard_resource_bootstrap_runtime` over `ResourceBootstrapRuntime` | Coding extension runtime factory | Complete |
| extension flag application and tool registration | `harness.extensions.ExtensionRuntime` and `harness.bootstrap` | Coding loader/policy and legacy pack identifiers | Complete |
| package sources, roots, install root, lock diagnostics | existing `harness.resources.packages` components | Coding package security policy | Complete |
| startup checks and cwd audit recording | existing `harness.diagnostics` and `harness.session.cwd_audit` | Coding executable identity check | Complete |
| prompt/model/context bootstrap leaves | existing `harness.session` and `harness.agent_transcript` | Coding default prompt, model preference, image message | Complete |
| project model-catalog reload | `ModelCatalog.reload_if_project_layer` | `.loushang/models` path convention | Complete |

Slice H accounting (production implementation only):
`coding/bootstrap.py` shrank from 1,178 to 773 LOC and
`coding/session/package_controller.py` from 232 to 205 LOC, a total Coding
reduction of 432 LOC. The remaining bootstrap code is the public Product
factory surface, Coding service/default construction, seven injected effects,
and concrete `AgentSession`/runtime binding. Private helper tests were moved to
the canonical Harness owner rather than preserving a Coding facade.

### Wave 7, Slice I: CLI Application Composition (Complete)

The remaining Coding CLI still copied the standard Agent argument value object,
extension bootstrap parser, two-pass application phase order, standard
operation queue, and repeated prepared-turn lifecycle arguments. These
mechanisms now extend the existing `harness.cli` package; no parser, session
runtime, or transport was duplicated.

| Source mechanism | Shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| standard Agent CLI dataclass and argparse namespace projection | `harness.cli.AgentCliArgs` | Method/Work additive fields | Complete |
| standard package/diagnostics/observability argv normalization and extension flag bootstrap parsing | `harness.cli.agent_args` and `harness.cli.extension_flags` | Method subcommand aliases | Complete |
| bootstrap parse, validation, guarded runtime/session creation, final parse, operations, and host phase order | `harness.cli.CliApplicationRuntime` | Product services, tool policy, observability context, and runner bindings | Complete |
| standard export/catalog/package/command/model precedence | `harness.cli.run_standard_cli_operations` | Method and package-catalog stage insertions | Complete |
| first/last prepared-turn images, follow-ups, and disposal flags | `harness.cli.run_keyword_cli_turns` | Method/Work prepared-turn metadata and Product runners | Complete |
| standard launch intent projection | `harness.cli.agent_cli_launch_plan` | Method/Work launch overlay | Complete |
| standard resource/session/catalog request projection and ephemeral bootstrap policy | existing `harness.cli` capability modules | Method catalog insertion and package security callbacks | Complete |
| resource-loader flags, session path, image policy, and offline activation | `harness.cli.agent_args` | Coding service factory and resource package content | Complete |
| tool settings to policy/approval projection | `harness.tools.workspace.factory` | Coding rule-id policy factory and interactive approval presentation | Complete |
| post-resolution extension/name/model/thinking configuration | `harness.cli.session_configuration` | model persistence policy and warning wording | Complete |
| fake workflow pre-runtime exit | `harness.scenario.cli` | Coding workflow runner and CLI flag | Complete |

Production accounting: `coding/cli` changed from 2,441 to 1,602 physical
Python LOC (-839 net). The cumulative patch deletes 1,525 Coding
implementation lines and adds 686 Coding binding lines. Shared production
additions are approximately 1,779 lines, for a gross
deletion/shared-addition ratio of 0.86. The larger shared addition establishes
typed, independently tested contracts rather than moving the old function
intact. Channel remains the owner of streams, output protection, turn ordering,
and disposal.

### Wave 7, Slice J: HarnessTUI Conversation Adapter Extinction (Complete)

Reusable conversation presentation and routing mechanics no longer have a
second implementation under Coding. This slice extends four existing
HarnessTUI owners and deletes the Coding event facade; it does not add a new
projector, controller, runtime, application, queue adapter, or package.
The detailed boundary is
[Coding Conversation Adapter Extinction](coding-conversation-adapter-extinction.md).

| Source mechanism | Existing shared owner | Coding retained | Status |
| --- | --- | --- | --- |
| normalized Session event routing and message/tool lifecycle | `harnesstui.conversation.projection` | visibility flags and Agent tool-result binding | Complete |
| queue-source normalization | `harnesstui.conversation.runtime_view` | explicit Session queue sources | Reused |
| mapping-shaped tool event/result projection and standard workspace presentation policy | `harnesstui.conversation.tool_transcript` | `AgentToolResult` conversion, optional Product renderer and final command-label policy | Complete |
| structural Agent message and command-history projection | `harnesstui.conversation.history` | persisted-session acquisition, kind dispositions and tool binding | Complete |
| abort-settling/follow-up/steer/local/dispatch decision order | `harnesstui.conversation.host` | Coding intents, local-action declarations, command catalog and copy | Complete |
| Plain/Screen effects and rendering | existing `plain_target`, `screen_target`, `screen_app` and TUI transcript engine | Product title, glyphs, status copy and theme | Reused |

Production accounting: Coding Python changed from 12,475 to 11,969 physical
LOC (-506 net). The affected Coding implementation changed from 1,369 to 863
LOC. The four existing HarnessTUI owner files changed from 1,106 to 1,715 LOC
(+609), giving a net Coding-reduction/shared-addition ratio of 0.83. No
compatibility facade replaces `coding.presentation.tui.events`, and
`CodingTuiProfile` is removed rather than re-exported. Independent HarnessTUI
tests cover structural event, history, tool and routing behavior; architecture
gates keep HarnessTUI free of Coding, Agent and AI imports.
