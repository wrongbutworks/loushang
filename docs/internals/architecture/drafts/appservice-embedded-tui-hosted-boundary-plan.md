# AppService Hosted Boundary With An Embedded TUI

[Architecture](../README.md) · [Drafts](README.md) ·
[Future Architecture v3](future-loushang-architecture-v3.md) ·
[Application Service Refactor](application-service-refactor.md)

## Status

Status: proposed delivery plan.

This plan clarifies one deployment choice in the v3 target architecture:

- the default native TUI remains an embedded, in-process Product surface and
  does not use `AppClient`;
- hosted and reconnectable surfaces use the versioned App Contract through
  `AppClient` and `AppService`; and
- both paths reuse Product-owned semantics and Harness contracts without
  making AppService part of the Harness Capability or Plugin runtime.

This document does not authorize implementation ahead of an accepted daemon,
external-client, or background-Session delivery requirement. It also does not
change the accepted Harness Capability graph, Plugin lifecycle, or provider
composition work currently being built in the Harness lane.

## Decision Summary

Loushang keeps two first-class process profiles:

```text
default local TUI
  Harnesstui
    -> Product conversation UI binding
    -> embedded Product runtime
    -> per-Session Harness runtime

hosted clients
  WebUI / IDE / mobile / remote TUI
    -> AppClient
    -> versioned App Contract
    -> AppServer endpoint
    -> AppService
    -> resolved Product Session or Work port
    -> per-Session Harness runtime or Work runtime
```

The default TUI does not serialize commands through the App Contract and does
not depend on `AppClient`, `AppService`, or a daemon. A future remote TUI mode
may use `AppClient`, but that is a separate hosted composition selected at
startup rather than a replacement for the embedded fast path.

AppService is the hosted application coordinator. It is not a universal UI
backend, a Capability provider, a Plugin manager, or a second Harness runtime.

## Why This Split

The embedded TUI needs low-latency access to terminal input, rendering,
playback, completion, interrupt, and Product-local interaction behavior. Making
every local action traverse a client protocol would add a second projection
boundary without providing process survival or reconnect semantics.

Hosted clients have a different problem. They need stable identifiers,
admission acknowledgements, ordered events, interaction correlation,
attachment and controller state, bounded delivery, snapshots, reconnect, and
version negotiation. These are AppService responsibilities and should not be
added to Harnesstui or the Harness Session facade merely to support a remote
surface.

The split therefore shares execution semantics but not presentation plumbing:

- Product and Harness remain authoritative for Session, turn, transcript,
  Approval, tool, and Work behavior;
- embedded Harnesstui binds those semantics directly through existing
  Product-owned adapters;
- AppService projects the same authoritative facts into a client-safe hosted
  state model; and
- no mutable embedded Session is transferred into a daemon.

## Boundary Vocabulary

| Name | Meaning | Explicit exclusion |
| --- | --- | --- |
| App Contract | Versioned, client-safe request, response, event, snapshot, and interaction values | Not serialized Harness, Product, Plugin, or widget objects |
| AppClient | Transport-neutral client contract for hosted surfaces | Not required by the default embedded TUI |
| AppService | In-process hosted application coordinator | Not a transport, Product runtime, Harness Capability, or Plugin manager |
| AppServer | Process host containing AppService, endpoint adapters, admission, and transport lifecycle | Not the owner of Product or Work semantics |
| Product Session port | Narrow Product-provided Session operations consumed by AppService | Not a universal Product interface or service locator |
| Product Work port | Narrow Product-provided durable Work submission and observation operations | Not a synonym for every turn |
| Harnesstui Product binding | Embedded adapter from Product-neutral TUI ports to one Product runtime | Not an App Contract adapter |

The exact Product Session and Work port names remain deferred until the first
hosted vertical slice proves the minimum methods. The implementation must not
create a speculative universal application port merely to make the two process
profiles look structurally identical.

## Ownership And Dependency Direction

The required source direction is:

```text
Product composition root
  -> Harnesstui public ports                    # embedded profile
  -> Product runtime and Harness public ports

AppServer composition root
  -> AppService
  -> explicit ProductResolver and Product ports # hosted profile
  -> Harness public projections only through Product adapters

Harness -X-> AppService / AppClient / App Contract / Harnesstui / Product
AppService -X-> concrete Product package / Harnesstui / Plugin internals
```

AppService may define the structural ports it consumes. Concrete Product
adapters implement those ports and may call Product and public Harness APIs.
This preserves dependency inversion: AppService never imports `loushang.coding`
or derives a Product implementation from an import path.

The embedded and hosted factories may share immutable Product definitions and
configuration, but each invocation constructs independent mutable runtime
state. Sharing a factory does not permit sharing a live Session object across
processes.

## Plugin And Capability Non-Interference Contract

The Harness Capability and Plugin workstream owns discovery, admission,
provider resolution, Capability planning, Binding, Mount lifecycle, refresh,
and disposal. AppService consumes only the final Product-facing result of that
composition.

The following rules are mandatory:

1. AppService is not represented as a Capability ID, Capability Bundle,
   Mounted Capability, Plugin, Extension, provider candidate, or graph node.
2. AppService never imports Harness capability planner, provider registry,
   Plugin manager, Mount runtime, or private binding modules.
3. AppService never discovers Plugins, selects providers, interprets discovery
   priority, refreshes a Capability graph, or disposes an individual provider.
4. `ProductResolver` is supplied by the outer composition root. Resolving a
   Product returns an immutable definition and scoped factories, not a global
   mutable registry or service locator.
5. Product runtime activation may cause the owning Product/Host composition to
   bind a Capability graph. AppService sees only the resulting narrow Session,
   Work, event-projection, and interaction ports.
6. Capability and Plugin lifecycle remains owned by the runtime scope that
   bound it. AppService closes its hosted Session binding; it does not reach
   inside that binding to tear down Mounts or Extensions.
7. Plugin identity and provider provenance may appear only in an explicitly
   redacted, read-only Product diagnostic projection. They are not App routing
   keys or client-controlled selection values.
8. A Plugin cannot replace AppService admission, authorization, attachment,
   controller lease, idempotency, or delivery-buffer invariants through the
   ordinary Harness variation mechanism.

If the AppService workstream discovers a missing Harness contract, it must not
patch capability internals from the AppService branch. The missing contract is
proposed and landed through the Harness lane first, then consumed from `main`
after its public boundary and architecture gates are accepted.

## Embedded TUI Contract

The default embedded TUI preserves the current ownership shape:

- Harnesstui owns terminal input, layout, rendering, local dialogs, local
  completion, playback, and presentation state;
- the Product UI binding translates TUI intents into Product/Session
  operations and Product-specific projections;
- Harness owns Product-neutral Session, transcript, interaction, tool,
  cancellation, and execution mechanisms; and
- Product composition owns prompts, tools, policy choices, domain events, and
  final presentation semantics.

The embedded path must not acquire hosted-only concerns:

- App protocol version negotiation;
- attachment, device, or controller-lease records;
- remote idempotency keys;
- delivery cursors or reconnect buffers;
- client-safe wire DTOs; or
- daemon lifecycle.

An embedded Session is local-only and ends with its owning foreground process
unless the Product already has a separately accepted persistence contract.
Attach does not migrate it into AppService. A Product that needs background
continuity creates the Session in AppService from the beginning and uses a
hosted client composition.

The supported command shape may eventually be:

```text
loushang tui                 # embedded default; no AppClient
loushang daemon              # owns hosted Sessions and AppService
loushang tui --connect URL   # optional hosted/remote TUI; uses AppClient
```

The third command is deferred until a remote-TUI requirement is accepted.

## Hosted App Contract V1

The first contract should be small, typed, and explicitly asynchronous. It
borrows the useful mechanics of Codex app-server without copying its
Thread/Turn/Item domain model.

### Connection

- `initialize`: negotiate one protocol major version, client identity summary,
  requested experimental capabilities, and Product capability summary.
- `initialized`: one-way acknowledgement after successful initialization.
- Authentication principal and authorization scopes come from the admitted
  transport context, never from an untrusted client payload.

### Session

- `session/open`
- `session/attach`
- `session/detach`
- `session/snapshot`
- `session/close`

The live Session routing table is distinct from a persisted conversation
catalog. Listing stored conversations, reading one, and resuming one are
separate future operations; a filesystem directory is never the live registry.

### Turn

- `turn/start`
- `turn/steer`
- `turn/followUp`
- `turn/interrupt`

`turn/start` acknowledges admission immediately with a stable `turnId` and an
`inProgress` status. Execution continues in a service-owned background task and
completes through ordered events. It does not wait for the Session to become
idle before responding.

The existing settled `SessionOperationRuntime.prompt()` contract remains
unchanged. The first AppService slice may adapt it with a host-owned turn task
and its existing admission/preflight signal. A later dedicated start-turn port
is justified only if at least two hosts need the same admission handle or the
adapter cannot preserve cancellation and failure convergence.

### Durable Work

- `work/submit`
- `work/read`
- `work/observe`

Work remains separate from a Session turn. `work/submit` means an accepted,
queryable business commitment; it is not used for every prompt merely because
the request arrived through AppService.

Work may be omitted from the first conversation-only protocol slice, but its
identifiers and event family must not later be overloaded onto `turnId`.

### Interaction

- server request: `interaction/request`
- client response: `interaction/respond`

The envelope carries an `interactionId`, Session identity, controller
generation, deadline/fallback summary, and one typed payload. AppService
validates routing, controller authority, generation, and idempotency, then
forwards the answer to the existing interaction owner.

AppService never creates an Approval shadow future, timeout, fallback, or
replacement interaction ID. Approval lifecycle remains owned by the Harness
Approval resolver/broker.

### Events And Snapshots

The base event envelope contains:

```text
eventId
streamId
sequence
sessionId
turnId? / workRunId?
eventType
payload
```

Core event families are typed: Session lifecycle, turn lifecycle, assistant
message deltas, tool lifecycle, interaction lifecycle, and Work lifecycle.
Product-specific event payloads use a Product-owned, namespaced extension
family rather than a generic command dictionary.

Reconnect converges through:

```text
snapshot(revision = N) + ordered events after N
```

Snapshot revision, attachment delivery cursor, transcript revision, Work event
position, and transient runtime-event sequence remain distinct identifiers.
None is silently reused as another merely because their first implementation
is an integer.

## Concurrency, Ordering, And Backpressure

AppService uses separate coordination lanes per hosted Session:

1. Session mutation and turn admission are serialized.
2. In-flight control operations such as steer, interrupt, and interaction
   response can enter while a turn is running; they must not wait behind a lock
   held for the complete model/tool run.
3. Safe reads such as snapshot and inspection may execute concurrently against
   immutable or revisioned projections.

Independent Sessions run concurrently. Session close prevents new admission,
settles or rejects queued requests deterministically, and delegates runtime
disposal to the owner of the resolved Product binding.

Each attachment has bounded outbound delivery. Ephemeral deltas may be
coalesced. The service must never silently discard interaction requests,
controller-lease changes, or terminal Turn and Work events. If a client falls
behind beyond the retained cursor, AppService returns `SnapshotRequired` and
requires convergence from a fresh snapshot.

One ordered server-output writer per attachment prevents responses, events,
and server-initiated interactions from racing on the transport. Request IDs,
interaction IDs, event sequences, turn IDs, operation IDs, and revisions are
different domains and cannot be overloaded.

## Suggested Package Boundary

The first accepted implementation may use:

```text
src/loushang/appserver/
  protocol/          # typed values, codec, version, schema fixtures
  ports.py           # narrow structural Product/host ports consumed by service
  service.py         # hosted coordination only
  connection.py      # attachment, correlation, ordered output, close semantics
  transports/
    jsonl.py         # first external transport when daemon is accepted
```

`client.py` belongs here only when a real hosted client or contract-test driver
needs it. An in-process client may be useful for service contract tests, but it
is not the default Harnesstui backend and does not justify migrating the local
TUI.

The package must not import concrete Product, Harnesstui, Plugin-manager, or
private Harness capability modules. Product-specific adapters live in the
Product package or its outer composition root.

## Delivery Slices And Gates

### Slice 0 — Accept The Boundary

Deliverables:

- accept or revise this decision;
- name the first hosted client and process-survival requirement;
- confirm that embedded-to-hosted migration is out of scope; and
- reserve `loushang.appserver` without adding runtime code.

Gate: no implementation starts merely because the target architecture contains
an AppService box.

### Slice 1 — Protocol Kernel

Deliverables:

- typed initialize, Session, turn, event, and interaction values;
- codec round-trip, unknown-field, unknown-method, and version tests;
- generated or golden JSON schema fixtures; and
- no generic `dict[str, Any]` escape hatch for unmodeled operations.

Isolation gate:

- no changes under `src/loushang/harness/capabilities`,
  `src/loushang/harness/resources/plugins`, or Harnesstui;
- no imports from concrete Product packages; and
- no daemon or network transport.

### Slice 2 — AppService Core

Deliverables:

- injected fake Product resolver and Session binding;
- Session registry, attachment/controller state, idempotency admission, turn
  task ownership, interaction forwarding, and ordered output;
- immediate `turn/start` acknowledgement followed by events; and
- bounded connection queues and deterministic close.

Gate: contract tests prove steer/interrupt during an active turn, stale and
duplicate interaction rejection, independent Session concurrency, and no
shadow Approval future.

### Slice 3 — One Real Product Adapter

Deliverables:

- one Coding-owned adapter at the composition root;
- one hosted conversation flow using public Product/Harness contracts;
- Product-specific event projection; and
- parity tests for shared turn, interrupt, queue, and Approval semantics.

Gate: the adapter does not cause AppService to import Coding and does not add an
AppService dependency to Harness. Default embedded TUI behavior remains
unchanged.

### Slice 4 — Daemon And Local Transport

Deliverables:

- AppServer process lifecycle;
- one local transport, preferably JSONL stdio or an accepted local IPC
  endpoint;
- attach/detach and snapshot convergence; and
- process-level authentication and resource admission appropriate to the
  transport.

Gate: a hosted Session survives client disconnect and reconnect without
claiming embedded Session migration.

### Slice 5 — External Surfaces

Add WebUI, IDE, mobile, WebSocket, remote TUI, or cloud tenancy only after a
named Product and delivery requirement accepts each surface. Security,
authorization, quotas, credentials, and reconnect guarantees are part of the
surface gate, not follow-up polish.

## Workstream And Branch Isolation

The planning work starts from `main` on a dedicated docs branch. Future
AppService implementation branches also start from current `main`, not from an
unfinished Harness capability/plugin task branch.

Recommended branch sequence:

```text
docs/appservice-embedded-hosted-boundary
appserver/protocol-v1
appserver/service-core
appserver/coding-hosted-adapter
appserver/daemon-local-ipc
```

Each branch has a disjoint primary ownership budget. Protocol and service
branches do not edit Harness capability or Plugin implementation files. The
Product adapter branch may consume only public Harness contracts already
landed on `main`.

If integration depends on ongoing Harness work:

1. record the missing public contract without copying unfinished implementation;
2. let the Harness work land through `lane/harness` and its normal gates;
3. merge the resulting `main` into the AppService task branch; and
4. add only the outer adapter and AppService consumption after the dependency
   is public and stable.

This sequencing prevents AppService deadlines from selecting Plugin providers
or freezing private capability-planner types into the App Contract.

## Verification Matrix

| Invariant | Required evidence |
| --- | --- |
| Embedded TUI does not depend on AppClient | import-boundary test and unchanged embedded startup smoke |
| Harness does not depend on AppService | architecture import test |
| AppService is Product-neutral | fake-Product contract tests and concrete-Product import denylist |
| AppService does not manage Plugins or Mounts | package import denylist and lifecycle tests at Product binding boundary |
| Turn start is asynchronous | admission response precedes terminal event |
| In-flight control remains live | steer and interrupt succeed while a turn runs |
| One interaction lifecycle owner | disconnect, stale controller, duplicate, late response, and timeout scenarios |
| Reconnect converges | snapshot plus retained events, and `SnapshotRequired` after cursor loss |
| Slow clients cannot exhaust the host | bounded queue and critical-event delivery tests |
| Sessions isolate execution | same-Session serialization and cross-Session concurrency tests |
| Protocol remains explicit | schema fixtures, version tests, and no generic command escape hatch |

## Non-Goals

This plan does not include:

- migrating the default TUI to AppClient;
- making App Contract a universal in-process command bus;
- moving terminal rendering or Product presentation into AppService;
- making AppService a Harness Capability or Plugin replacement surface;
- exposing capability-planner, provider, Mount, or Plugin internals to clients;
- changing the settled Session operation contract before a second host proves
  the need for a shared admission handle;
- routing every turn through Work or Method;
- automatic embedded-to-daemon Session or transcript transfer;
- durable replay storage in the first AppService slice; or
- WebSocket, P2P, relay, multi-tenant cloud, or mobile guarantees before their
  delivery gates are accepted.

## Acceptance Checklist

Before implementation begins, reviewers should be able to answer yes to all of
the following:

- Is there a named hosted client or background-Session requirement?
- Does the default local TUI remain embedded and independent of AppClient?
- Are Product Session and Work semantics still distinct?
- Is AppService outside Harness Capability and Plugin composition?
- Does AppService consume only explicitly injected Product ports?
- Is the first protocol slice typed, asynchronous, and smaller than the full
  future Product surface?
- Are Approval lifecycle and pending futures still owned by the existing
  Harness interaction owner?
- Can steer, interrupt, and interaction responses enter during a running turn?
- Are snapshot revision, event sequence, transcript revision, and delivery
  cursor kept distinct?
- Can the work land without editing the ongoing Harness capability/plugin
  implementation branch?
