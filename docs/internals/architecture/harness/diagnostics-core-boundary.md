# Harness Diagnostics Core Boundary

## Status

Status: accepted for `lane/harness`.

This document defines neutral diagnostic records, query and summary contracts,
startup-check records, and the bounded in-memory diagnostic engine as
`loushang.harness.diagnostics` responsibilities. Coding keeps concrete checks,
observability projection, serialization, remediation, session integration, and
user-interface behavior.

## Record Decision

`loushang.harness.diagnostics.types` owns:

- `DiagnosticLevel`;
- `DiagnosticPhase`;
- `DiagnosticSource`;
- `DiagnosticRecord`;
- `ErrorReport`;
- `DiagnosticSummary`;
- `DiagnosticsQuery`;
- `StartupCheckResult`;
- `StartupCheck`.

The current level, phase, and source vocabulary moves unchanged. It describes
cross-product diagnostic locations such as startup, resource loading, runtime,
loader, session, policy, tool, provider, model, and agent. Harness carries this
vocabulary but does not decide which product condition should emit a record.

Session, entry, tool-call, source-path, and details fields are opaque
correlation values. Harness stores and filters them without loading a session,
tool, resource, provider, or model implementation.

## Engine Decision

`loushang.harness.diagnostics.service` owns `DiagnosticsService` and its
mechanisms:

- bounded in-memory record retention;
- stable fingerprint generation;
- duplicate occurrence aggregation;
- record and structured-query filtering;
- last-error report construction;
- diagnostic summary aggregation;
- resource-diagnostic normalization;
- exception normalization and failure capture;
- caller-supplied startup-check execution and normalization;
- runtime-record clearing.

The engine preserves existing ordering, duplicate identity, timestamp,
capacity, query precedence, summary counting, default startup-check code and
message, and JSON-safe fingerprint behavior. It does not discover or register
checks by itself.

`ResourceDiagnostic` remains owned by
`loushang.harness.resources.diagnostics`. The core engine adapts that focused
resource record into a general diagnostic record when a product supplies the
phase, source, level, and correlation values.

## Coding Adapters

The generic Coding diagnostic facade is removed. Product and extension code
imports records, query values, and `DiagnosticsService` from the canonical
owners in `loushang.harness.diagnostics`; Coding retains only
`harness.diagnostics.serialization` and an observability source-classification
resolver as its product projections. Coding's source-classification resolver
remains Product-owned.

Harness diagnostic symbols are public from the focused
`loushang.harness.diagnostics` subpackage, but are not promoted to top-level
`loushang.harness.__all__`. Coding internal consumers import the focused owner
directly.

## Coding-Owned Behavior

This migration does not move or redesign:

- `harness.diagnostics.serialization` and its existing camelCase RPC/SDK payload shape;
- Coding's observability-source classification, including its `config` to
  `model` policy;
- bootstrap, resource, provider, model, extension, session, policy, exec, or
  tool checks;
- diagnostic emission timing or product severity choices;
- remediation messages supplied by concrete checks;
- session diagnostic filtering/projection bridges;
- CLI, print, RPC, TUI, export, or status-line presentation;
- persisted diagnostic configuration or product defaults.

Products remain responsible for constructing checks, choosing source and phase
values, deciding whether a problem is recoverable, and presenting remediation.

## Dependency Direction

The target direction is:

```text
coding checks / sessions / tools / runtime -> loushang.harness.diagnostics.service
coding serializers                           -> loushang.harness.diagnostics.types
coding observability policy                  -> loushang.harness.diagnostics.observability_bridge
loushang.harness.diagnostics.observability_bridge -> loushang.observability
loushang.harness.diagnostics.service       -> loushang.harness.resources.diagnostics
```

The diagnostics core (`types` and `service`) must not import coding, method,
work, TUI, AI, agent runtime, provider, observability, or product packages.
`loushang.harness.diagnostics.observability_bridge` is an optional adapter:
it may import observability but must not import a Product. No diagnostic
symbols are added to top-level `loushang.harness.__all__`; the focused
diagnostics subpackage is the canonical public owner.

## Migration Result

Existing record fields, frozen-record behavior, callable aliases, service
method signatures, query filtering, deduplication, occurrence counts,
fingerprint payloads, summary counts, error reports, startup-check behavior,
and serialized Coding payloads remain unchanged. Only the generic ownership
path changes.

Private service helpers are implementation details. The public generic surface
is the record, callable, and `DiagnosticsService` API exported by
`loushang.harness.diagnostics`.

## Validation

The migration must prove:

- all record defaults and frozen behavior are preserved;
- record retention, ordering, deduplication, and capacity are preserved;
- direct arguments and `DiagnosticsQuery` retain their precedence behavior;
- source, phase, level, correlation, code, and limit filters are preserved;
- summary and error-report occurrence semantics are preserved;
- resource, exception, and startup-check normalization are preserved;
- Product and Coding consumers import the canonical owners;
- Coding serializers and problem bridge still project the same payloads;
- Coding internal consumers use Harness owners directly;
- Harness import boundaries and top-level export discipline still pass.
