# Session RPC Operation Cutover Boundary

## Status

Status: implementation in progress. The Channel command-routing slice is
complete; standard-operation response projection remains in Coding until the
following adapter slice removes duplicated glue without changing the public
RPC contract.

## Problem

`coding.mode.rpc_mode.RpcMode` is the legacy Coding JSONL protocol adapter.
It still combines four different responsibilities:

1. strict JSONL input dispatch and unsupported-command handling;
2. scheduling and draining background prompt and bash tasks;
3. invocation of standard session controls such as prompt, steer, abort,
   session naming, retry, and compaction; and
4. Coding-specific RPC request aliases, camelCase responses, model/auth,
   package, bash, extension UI, event views, and session-state projection.

The third responsibility already has one canonical owner:
`harness.session.SessionOperationRuntime`. This wave must not create a second
RPC-shaped session executor merely to move code out of Coding.

## Ownership

| Concern | Canonical owner | Product responsibility |
| --- | --- | --- |
| Strict JSON line parsing and one-command dispatch | `channel.JsonlCommandHost` | Bind an RPC schema and response projection. |
| Explicit command route registration and unknown-command fallback | `channel` | Register Product handlers and preserve Product error text. |
| Background task tracking and host lifecycle | `channel.ProductHostTaskTracker` / `ProductHostRuntime` | Choose which Product operations run in the background. |
| Typed prompt, input, queue, lifecycle, identity, retry, and maintenance operations | `harness.session.SessionOperationRuntime` | Bind a session control port and choose capability availability. |
| Coding JSON field aliases and camelCase success/error frames | `coding.mode.rpc_mode` | Preserve the public Coding RPC contract. |
| Model/auth, package, bash, extension UI, event rendering, and state projection | `coding` | Retain domain policy and presentation. |

`channel` may depend on `protocol`, but it must not import Harness or Coding.
`harness.session` may depend on stable Agent/AI value contracts where required,
but it must not import `channel` or a Product protocol schema.

## Target Composition

```text
JsonlCommandHost
  -> Channel command router
     -> Coding RPC request parser and response projector
        -> SessionOperationRuntime
           -> bound Product session_control

     -> Coding-only model/auth/package/bash/extension handlers
```

The router is intentionally only a command-to-handler registry. It does not
define request fields, output frames, error wording, a session state schema, or
the lifecycle of an Agent session.

## Admitted Standard Operations

The first cutover group is limited to operations already represented by
`SessionOperationRuntime`:

```text
prompt
steer
follow_up
abort
set_session_name
compact
set_auto_retry
abort_retry
set_auto_compaction
```

`prompt` continues to acknowledge after Product preflight and run in the
background. The Channel task tracker owns task lifetime; Coding supplies the
legacy acknowledgement/error projection. The remaining operations continue to
use the existing synchronous or asynchronous Harness session-control methods.

The following remain Coding-owned in this wave:

- `set_model`, model discovery/cycling, and thinking policy;
- package source lifecycle and Coding package records;
- bash execution and Coding shell output;
- extension UI, legacy event aliases, tool rendering, and session-state JSON;
- session listing/index queries and Coding transcript presentation;
- Coding RPC command names, snake/camel input aliases, and response text.

## Delivery Slices

1. **Channel routing contract**
   - Add an immutable explicit JSONL command router under `channel`. Complete.
   - It receives `JsonlCommand`, dispatches only registered handlers, and
     delegates unsupported-command output to an injected Product callback.
   - `RpcMode` binds every current command through an explicit route table;
     reflection is no longer part of its dispatch path.
   - Add a fake Product test with no Coding or Harness import.

2. **Standard session-operation adapter**
   - Bind the admitted operation group through the existing
     `SessionOperationRuntime` and Channel task tracker.
   - Keep request parsing and response projection injected so the adapter has
     no Coding wire fields.
   - Lock prompt acknowledgement timing, task draining, capability-unavailable
     behavior, and command routing precedence.

3. **Coding cutover and deletion**
   - Replace `RpcMode` reflection dispatch and admitted handler glue with the
     Channel router and session-operation adapter.
   - Delete duplicated background-task and standard-operation orchestration.
   - Retain the Coding-only handlers listed above and add an import boundary
     proving Channel and Harness do not import Coding.

## Non-Goals

This wave does not:

- replace the existing Coding JSONL RPC protocol with the separate standard
  Channel operation-frame protocol;
- define a universal RPC payload union or make JSON a Harness session API;
- move model/auth, package, bash, extension UI, or Coding event contracts;
- change prompt preflight acknowledgement timing, session replacement behavior,
  or the supported Coding RPC method names.

## Completion Gate

- Channel routing tests cover duplicate route rejection, unknown-command
  fallback, synchronous and asynchronous handlers, and no Product imports.
- A fake session-control port executes every admitted operation without Coding
  types or JSON fields.
- Existing Coding RPC tests preserve prompt acknowledgement timing, steer and
  follow-up images, abort, naming, retry, and compaction results.
- `channel` has no Harness/Coding import; `harness.session` has no Channel or
  Coding import.
- `RpcMode` no longer uses reflection dispatch for registered routes, and its
  remaining handlers are explicitly Product-owned.
