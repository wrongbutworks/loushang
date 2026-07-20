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

## Later Waves

The following rows are intentionally broad until their waves are scheduled.
They are not estimates or approval to duplicate an existing Harness owner.

| Wave | Source regions to ledger before implementation | Intended shared owners |
| --- | --- | --- |
| 2 | Coding event projections and extension agent bridge | `harness.session`, `harness.extensions`, `harnesstui` |
| 3 | Standard session commands, tool/package bindings, transcript export | `harness.session`, `harness.commands`, `harness.agent_transcript` |
| 4 | `AgentSession`, runtime composition, bootstrap activation | existing `ProductRuntimePlan`, runtime resolver/binder, `harness.session` |
| 5 | RPC, print, channel host, shared conversation interaction | `channel`, `harness.session`, `harnesstui`, `tui` |
| 6 | Config composition, common defaults, CLI and Work/Method bridges | `harness.config`, `ai`, `work`, `method`, `tui` |

Each later row must be expanded to the same level as Wave 1 before code changes
begin. A product facade is not complete until the old implementation is deleted
or reduced to declared product data and ports.
