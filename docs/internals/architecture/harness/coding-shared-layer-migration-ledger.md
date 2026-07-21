# Coding Shared-Layer Migration Ledger

This is the rolling implementation ledger for
[the Coding shared-layer migration plan](coding-shared-layer-migration-plan.md).
It is deliberately a ledger, not a second design document: a wave cannot start
until its source regions, final owners, injection points, and deletion condition
are listed here.

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
| Agent prompt/context/session-decision reducers formerly in `coding.extensions.runner.ExtensionRunner` | `harness.extensions.agent.hooks` and `harness.extensions.session_runtime` | Coding supplies bound context, CWD, API binding, `before_agent_start` factory/result coercer, and session-decision compatibility coercer. | Complete: shared dispatchers own the reducer mechanics; Coding retains aliases and provider behavior. |
| removed `harness.session.extension_{hooks,events,input}` modules | `harness.extensions.agent.{hooks,lifecycle,input}` | Session only consumes the profile during Agent-session composition. Input receives normalized typed requests plus queue/delivery ports; lifecycle is an observation-only extension callback adapter with injected clock/correlation values; Coding retains wire parsing/defaults. | Complete: consumers import the profile directly, input has no Session import, and Session no longer re-exports the profile. |
| `coding.extensions.runner.ExtensionRunner` loader/API/alias portions | Coding adapter | `ExtensionAPI`, policy resolver, loader legacy names, provider actions, and Coding error dictionary remain Product-owned. | It is complete only when it is a thin adapter over the existing shared runtime and dispatchers. |
| `coding.event` runtime projection, views, serializer, and presentation policy | Existing `harness.events` fact/view APIs; no new event owner | Coding retains `AgentSessionEvent`, Pi aliases, camelCase schema, rendering, transcript decision, and wording. | Production consumers use the common runtime API where possible; there is no duplicate neutral event engine. |

Wave 2 contract probes:

- a fake Product executes context, before/after tool, before-agent-start, and
  session-decision hooks with no Coding import;
- invalid hook results, route ordering, block behavior, and runtime failure
  reporting preserve existing diagnostics;
- Coding extension provider actions and JSON/print/RPC event projections stay
  behaviorally unchanged;
- architecture tests forbid Coding imports from the new shared dispatchers and
  forbid a new Harness event schema for Coding aliases;
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
| 3 | `coding.session.builtin_commands` admitted subset (`session`, `name`, `export`, `import`, `compact`, `reload`, `new`, `resume`, `fork`, `clone`, `tree`); `coding.session.command_controller` standard-source forwarding; command descriptor and resource/extension projection helpers | `harness.session.command_pack`, existing `harness.session.SessionCommandRuntime`, `harness.commands`, and `harness.extensions.commands` |
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
| Descriptor construction for the admitted standard command subset | Existing Coding builtin descriptor source over `harness.commands.SessionCommandDescriptor` | Coding selects names, descriptions, aliases, visibility, and source priority. | Deferred: move only after the public command-list ordering contract is explicitly preserved. |
| Parsing and typed result adaptation for the admitted subset | `harness.session.command_pack` over existing session identity, export/import, operation, lifecycle, and navigation runtimes | Coding supplies ports and result projection; selected commands use the bound-port availability contract. | Complete: the corresponding `builtin_commands` handlers delegate to Harness and no longer contain parsing/execution logic. |
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
