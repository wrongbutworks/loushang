# Harness Host Runtime Boundary

## Status

Status: implementation complete for integration into `lane/harness`.

This document defines the product-neutral host lifecycle, input-queue ledger,
and ordered event-dispatch mechanisms owned by `loushang.harness.host`.
Coding remains responsible for product input semantics, session persistence,
controllers, commands, resources, extensions, and presentation.

## Control Boundary

The runtime control stack is:

```text
product adapter
  -> loushang.harness.host       # host state, scheduling boundary, feedback
  -> loushang.harness.run_agent  # prepared run facade
  -> loushang.agent              # agent task, cancellation, LLM/tool loop
```

`loushang.agent` continues to own the active agent task, cancellation signal,
message state, steering/follow-up delivery, and the LLM/tool feedback loop.
Harness must not implement a second agent loop or require Agent to import
Harness.

The Host Runtime coordinates an injected driver. It observes and controls the
driver through callbacks for running an operation, aborting, waiting for idle,
and optional disposal. A product adapter may use the stateful `Agent` facade or
the prepared-run facade behind those callbacks.

## Harness-Owned Types

`loushang.harness.host.types` owns:

- `HostStatus` for idle, running, aborting, disposing, and disposed states;
- `HostSnapshot` for the current status and active run identity;
- `RunState`, the accepted idle/running compatibility projection;
- `QueueKind` and `QueueMode`;
- `QueuedMessageSnapshot` and `QueueSnapshot`;
- neutral host lifecycle event records.

The broader Host status is not projected directly into Coding UI state.
Coding maps running, aborting, and disposing to its accepted running view when
needed.

## Host Runtime

`loushang.harness.host.runtime.HostRuntime` owns:

- legal host state transitions;
- one-active-run enforcement;
- run identity tracking;
- delegation to an injected async operation;
- abort requests and wait-for-idle coordination;
- idempotent disposal;
- ordered lifecycle event publication;
- rejection of new work after disposal.

The injected driver still owns the actual task and cancellation mechanics.
Host Runtime does not inspect prompts, messages, models, tools, diagnostics,
work plans, artifacts, or session storage.

Operation exceptions continue to propagate to the product caller after Host
Runtime records a neutral failure event and returns to idle. An abort request
does not invent a new error contract: it delegates cancellation to the driver
and records the run as aborted when the delegated operation completes.

## Input Queue Ledger

`loushang.harness.host.queue.HostInputQueue` owns:

- stable queue ids;
- steering and follow-up ordering;
- queue snapshots;
- one-at-a-time and all-at-once ledger consumption;
- identity-first consumption with an optional visible-text fallback;
- next-turn payload buffering.

The queue is generic over its payload. It does not construct AI messages,
parse commands, run preflight policy, select visible text, or deliver messages
to Agent. Coding's queue controller remains the adapter that performs those
actions and mirrors Agent delivery in the Harness ledger.

## Ordered Events

`loushang.harness.host.events.OrderedEventBus` owns:

- subscription and unsubscription;
- sync or async listeners;
- serialized scheduled dispatch;
- direct dispatch and drain behavior;
- synchronous dispatch when no event loop is available.

The bus is generic over its event payload. Coding continues to own
`AgentSessionEvent`, event projection, UI interpretation, and extension event
mapping.

## Coding Adapter

Coding adopts the Host Runtime core as follows:

- `coding.session.types.RunState` re-exports the Harness-owned record;
- `coding.session.queue_controller.QueueController` delegates ledger state and
  snapshots to `HostInputQueue` while keeping preflight, AI message creation,
  Agent delivery, logs, and queue-update events;
- `coding.session.session_event_bus.SessionEventBus` specializes
  `OrderedEventBus` while preserving its accepted no-loop error text;
- `AgentSession` delegates prompt/continue lifecycle, abort, idle waiting, and
  disposal state to `HostRuntime`;
- Coding controllers receive product callbacks rather than importing Host
  policy into their input handling.

Accepted Coding imports and public behavior remain available. Harness-owned
records keep their Harness `__module__`; compatibility paths preserve the
import path, not Coding-owned identity.

## Product-Owned Behavior

This migration does not move or redesign:

- input text/image conversion, preflight, slash parsing, or command handlers;
- `AgentSessionEvent` or product event projection;
- prompts, skills, tools, active-tool policy, or product defaults;
- retry classification, compaction, summarization, or context salience;
- session JSONL, message entries, and concrete tree/fork/clone/resume/import/export
  decisions; generic current-session transition mechanics are defined by the
  [Product Runtime Core Boundary](product-runtime-core-boundary.md);
- resource and extension discovery, activation, runtime hooks, or permissions;
- UI state, status text, diagnostics presentation, or artifact semantics;
- work, method, channel, model, provider, or auth behavior.

## Neutrality Evidence

The implementation must satisfy the
[Neutrality Evidence Gate](refactoring-principles.md#neutrality-evidence-gate)
without waiting for another production product:

- Coding exercises the compatibility adapter end to end;
- a product-neutral reference driver exercises Host Runtime without importing
  Coding runtime objects or vocabulary;
- generic queue payload tests use non-Coding objects;
- generic event tests use neutral event records;
- architecture tests forbid product imports from `loushang.harness.host`;
- no host symbols are added to top-level `loushang.harness.__all__`.

## Validation

The migration must prove:

- legal transitions, concurrent-run rejection, abort, wait, failure recovery,
  idempotent disposal, and post-disposal rejection;
- queue ordering, ids, modes, duplicate identity, visible-text fallback,
  snapshots, clear, and next-turn buffering;
- ordered sync/async event delivery and no-loop behavior;
- Coding class identity and accepted queue/session behavior;
- AgentSession prompt, extension message, retry, abort, idle, and disposal
  behavior remains intact;
- Harness dependency direction and documentation guards pass.
