# Coding Shared-Layer Owner Rebaseline

## Status

Status: Wave R baseline for `lane/harness`.

This is the mandatory owner rebaseline from
[Coding To Shared-Layer Migration Plan](coding-shared-layer-migration-plan.md).
It records the state after `lane/harness` commit `336adbf2`. Figures are
production Python LOC from `wc -l`, excluding tests, documentation, re-exports,
and resource assets. A later wave may claim migration LOC only after it deletes
the identified Coding implementation and records the actual delta here.

## Classification

| Classification | Meaning |
| --- | --- |
| `shared adopted` | A shared owner already performs the mechanism. The Coding code is a Product binding, projection, or adapter and must not be counted again. |
| `duplicate candidate` | Coding still implements a reusable mechanism, pending a concrete port/profile contract and a fake-Product probe. |
| `product adapter` | Coding binds shared mechanisms to Product policy, content, or compatibility. It may shrink but is not a mechanical move. |
| `product kernel` | Coding owns semantics, compatibility, UI, provider/model policy, or final presentation. It stays in Coding. |

## Session And Host

| Source region | LOC | Current shared owner or adopted mechanism | Classification | Next action |
| --- | ---: | --- | --- | --- |
| `coding.bootstrap` | 1,491 | Config activation, capability composition, resources, diagnostics, `SessionRuntime` | `product adapter` + `duplicate candidate` | Wave 4 bootstrap-transaction contract |
| `coding.runtime.agent_session_runtime` | 1,187 | `SessionLifecycleRuntime`, `AgentTranscriptSessionRuntime`, transcript catalog | `product adapter` | First transcript-store cutover complete; retain Product ports and continue facade audit |
| `coding.session.agent_session` | 1,890 | `SessionRuntime`, `SessionFacade`, transcript maintenance, queue, retry, compaction | `product adapter` | Facade deletion only after the factory contract |
| `coding.session.builtin_commands` | 716 | `harness.session.command_pack` | `shared adopted` | Close descriptor/projection deletion only |
| `coding.session.command_controller` | 239 | `SessionCommandRuntime`, command sources | `shared adopted` | Retain Product source/result binding |
| `coding.mode.rpc_mode` | 2,687 -> thin adapter | `harness.host.rpc` owns JSONL host/router/task tracker, standard operation handlers, state/model/diagnostic dispatch; Channel owns framing | `product adapter` | Complete: Coding injects event and diagnostics projections |
| `coding.mode.print_mode`, `channel_mode`, `base` | 1,201 -> thin adapters | `harnesstui.conversation.plain_mode` owns plain/JSON host lifecycle and state observation; `harness.host.mode` owns lifecycle contracts; Channel owns operation framing | `product adapter` + `shared adopted` | Print/base cutover complete; Channel operation binding retains Work/domain policy |
| `coding.prompt_command` | 323 | Prompt assembly and command parsing | `product kernel` | Retain Coding Work semantics |

Coding remains responsible in this group for service factories, the Coding
transcript store, CWD/session-file acceptance, model/provider decisions,
extension API, prompts, resource package, final RPC schema, and output wording.

## Extensions, Events, And Configuration

| Source region | LOC | Current shared owner or adopted mechanism | Classification | Next action |
| --- | ---: | --- | --- | --- |
| `coding.extensions.runner` | 495 | `harness.extensions.agent.*`, `harness.extensions.session_runtime` | `product adapter` | Shrink-only adapter audit |
| `coding.extensions.api/loader/policy` | 210 | Harness extension contracts and loader | `product adapter` | Retain Coding API and permission delta |
| `coding.event.*` | 1,045 -> ~160 canonical | `harness.events.session_types` and `harness.events.session_projection` own shared session dictionaries, standard views, render enrichment, stream shaping, and snake_case serialization | `product adapter` | Delete the thin Coding import surfaces after downstream imports move; retain only RuntimeEvent-to-session/Product/Work mapping, cancellation/transcript policy, and final presentation |
| `coding.control.settings_manager` | 1,400 | `ScopedConfigRuntime`, schema codec, JSON store | `product kernel` | Wave 6 only by proven shared field group |
| `coding.control.types` | 177 | No complete shared owner | `product kernel` | Split only cross-product settings |
| `coding.policy.*` | 515 | Harness rule, approval, and resource-policy mechanisms | `product adapter` + `product kernel` | Extract profiles, not rules mechanically |
| `coding.tool_pack`, `resource_runtime` | 346 | Workspace tool composition and resource/package engines | `product adapter` | Retain Coding membership, order, descriptions, context-file conventions |
| `coding.compaction.adapter`, `profiles` | 359 | Transcript capability and summary-profile mechanism | `product adapter` + `product kernel` | Retain Coding executor and prompt text |

## Leaf And Interaction Regions

| Source region | LOC | Current shared owner or adopted mechanism | Classification | Next action |
| --- | ---: | --- | --- | --- |
| `coding.source_info`, `model_selection` | 187 | `harness.resources.source`, `observability.runtime_identity`, `ai.model`, session model selection | `shared adopted` | Remove residual facade imports only |
| `coding.interaction.*` | 777 | TUI and HarnessTUI primitives | `product adapter` + `product kernel` | Wave 5/6 only after neutral screen-host probe |
| `coding.model_selection_tui` | 279 | AI model values and TUI primitives | `product adapter` | Require a second Product workflow before extraction |
| `coding.diagnostics.*`, `diag_export`, `observability` | 472 | Harness diagnostics/export and observability runtime | `shared adopted` | Retain Coding JSON/CLI/path adapters |
| `coding.sdk_surface` | 138 | No universal SDK contract | `product kernel` | Retain; only a generic verifier may enter test support |

## Non-Duplicates

Do not recreate the existing shared implementations for session
runtime/facade/lifecycle, transcript factory and directory, retry/compaction/
queue, resources/packages, configuration layering, command composition, JSONL
parsing, or extension Agent hooks. Replacing a Coding call to one of these with
another wrapper does not count as migration.

## Wave 4 Scope Gate: Product Bootstrap Transaction

The remaining material duplicate candidate is the Product bootstrap
transaction: activation ordering, cleanup, failure capture, and final factory
invocation around already-bound ports. A narrow Harness contract is admitted
only when it:

1. sequences injected activation steps, cleanup, failure capture, and final
   factory invocation without importing Coding;
2. reuses `ConfigActivationRuntime`, `CapabilityCompositionRuntime`,
   `SessionLifecycleRuntime`, and `SessionRuntime`, rather than adding a
   resolver, lifecycle, or service locator;
3. receives prompt, model/auth, resource, tool/command, approval,
   session-file/CWD, and extension behavior from typed Product ports or the
   existing runtime profile binding; and
4. is exercised by a fake Product through success, failed activation with
   reverse cleanup, and final disposal.

The initial boundary is the transaction portions of `coding.bootstrap` and
`coding.runtime.agent_session_runtime`. `AgentSession` remains a Product
adapter until a separate facade audit identifies methods that only forward the
existing Harness surface.

The first admitted slice is narrower than a bootstrap engine:
`ProductTranscriptSessionLifecycleStore` now owns transcript create, restore,
fork, runtime-session association, and failed-build cleanup. Coding provides
its transcript session type, CWD restore validation, fork policy, and runtime
session constructor. `ConfigActivationRuntime` already owns ordered activation
and optional rollback; no second bootstrap transaction is admitted until a
later adapter audit finds a reusable remainder.

## Measurement Rule

The first Wave 4 implementation records exact pre-change LOC for each extracted
function/class, post-cutover Coding LOC, shared LOC added, and net deleted
Coding implementation. The first store cutover changes
`coding.runtime.agent_session_runtime` from 1,187 to 1,158 LOC (-29) and
`harness.session.transcript_lifecycle` from 216 to 371 LOC (+155); tests do not
enter either figure. Historical 18,000--20,000 LOC estimates are not a delivery
metric.
