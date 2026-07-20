# Session RPC Operations Boundary

## Decision

`loushang.harness.session.operations` owns typed, reusable operations over an
already-bound `SessionControlPort`. It is a capability runtime, not an RPC
protocol. A Product decides which capability groups to bind and maps its own
transport requests, response schema, error wording, and task lifecycle to the
runtime.

The standard groups are:

- input: prompt, steer, and follow-up submission;
- queue: pending message reads and queue clearing;
- lifecycle: continue, abort, and idle waiting;
- identity: session id/name reads and display-name update;
- retry: retry inspection, abort, and waiting;
- maintenance: auto-retry/compaction settings and compaction control.

`SessionPromptRequest` is a typed application request. It does not contain a
JSON command name, a correlation id, Pi aliases, or a response envelope.
`SessionOperationAvailability` is explicit: an unbound group fails with
`SessionOperationUnavailableError`, rather than relying on an optional method
or an implementation-specific `getattr` check.

## Ownership

Harness owns operation grouping, typed input values, dispatch through
`SessionControlPort`, and capability admission. It does not own:

- JSONL parsing or response/error framing;
- host background-task tracking or request correlation;
- model/auth selection, bash execution, package lifecycle, extension UI, or
  Product command catalogs;
- product state, event, diagnostic, or HTML projection.

Channel remains transport-neutral and accepts injected Product operation ports;
it must not import Harness. Coding maps its established RPC commands onto this
runtime and preserves its public JSON field names, event views, model
compatibility payloads, and coding-specific operations.

## Verification

- Harness tests use an independent `SessionControlPort` fake to exercise each
  standard group and unavailable-capability behavior.
- Channel tests remain free of Harness imports.
- Coding RPC regressions preserve existing wire responses after its adapter
  begins using the operation runtime.
