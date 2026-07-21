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
| `coding.diag_export` archive writer and redaction | `harness.diagnostics.export` | Coding supplies archive path, README, manifest projection, artifact list, and diagnostic JSON projection. | Complete: Coding is a thin product adapter. |
| `coding.source_info` descriptor conversion | `harness.resources.source` | Coding only supplies its resource descriptor values. | Complete: production resource consumers import Harness directly. |
| `coding.source_info` executable, package, and Git inspection | `observability.runtime_identity` | Coding supplies package/module identity, executable name, and display title. | Complete: Coding has no subprocess, package metadata, or PATH logic. |
| `coding.model_selection` normalization and presentation-neutral ordering | `ai.model` | Coding retains preferred models and Coding persistence wording. | Complete: non-policy consumers import `ai.model`. |
| `coding.model_selection` session model application and discovery | `harness.session.model_selection` | Products inject preferred candidate selection and persistence callbacks. | Complete: Coding is the preferred-candidate adapter. |
| `coding.observability` configuration lifecycle | `observability.runtime` | Coding supplies CLI/environment names, `.loushang` default paths, and diagnostic source mapping. | Complete: Coding is a path/profile adapter. |

Wave 1 contract probes:

- The diagnostics archive writer accepts a product-projected manifest and
  diagnostics, redacts both structured values and text artifacts, and rejects
  unsafe archive member names.
- Runtime identity collection works for a non-Coding package/module pair.
- Session model selection works with a fake session and a caller-supplied
  candidate chooser; it has no Coding import.
- Observability lifecycle configuration restores a pre-existing sink after the
  product context exits.

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
| `coding.control.settings_manager` layered settings mechanics | `harness.config.SettingsRuntime` over `ScopedConfigRuntime` | `ControlConfig`, field codecs, defaults, removed-field handling, and typed Product setters |
| `coding.cli.__main__` stream binding, output guard, and disposal fallback | `channel.ProductHostLifecycle` | Argument grammar, mode selection, Product startup policy, output format, and command handlers |

These are adapter collapses rather than new protocol layers. Harness and Channel
do not import Coding, and no RPC/CLI wire fields changed in this wave. The
lifecycle contract is verified with independent Harness/Channel fakes plus the
existing Coding settings and CLI regressions.
