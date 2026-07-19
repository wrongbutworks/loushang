# Runtime Event Projection And Channel Boundary

## Decision

`loushang.harness.events` owns the neutral `RuntimeEvent` envelope and the
transport-ready `RuntimeEventView` value contract. `loushang.channel` owns the
external envelope, JSON codec, and JSONL frame that can deliver an already
created view. Product code owns the conversion from a typed runtime payload to
an event type, view name, strict JSON payload, aliases, rendering, and any
product wire shape.

```text
RuntimeEvent (Harness)
  -> Product projection
  -> RuntimeEventView (Harness value contract)
  -> ChannelEnvelope / ChannelEventDelivery (Channel)
  -> client transport
```

The Work path remains independent:

```text
RuntimeEvent -> Work projection -> WorkEvent -> ChannelEnvelope
```

Neither path replaces the other. `RuntimeEvent` is a transient observation,
`RuntimeEventView` is a transient transport representation, `WorkEvent` is a
normalized work/audit semantic event, and `ConversationRecord` remains the
durable transcript fact.

## Runtime Event View Contract

`RuntimeEventView` preserves source identity:

- `event_id`, `kind`, `stream_id`, `sequence`, and timezone-aware
  `occurred_at`;
- optional `session_id`, `run_id`, `source_event_ref`, and `source_record_id`;
- Product-created `event_type`, `view`, optional `correlation_id`, and
  delivery hint;
- a copied strict-JSON object payload.

The view constructor rejects invalid source metadata, unsafe JSON, and unknown
delivery hints. The generic selector accepts only exact matches and a trailing
`*`; Product aliases such as Coding's `assistant.*` remain Product policy.

## Channel Contract

`ChannelEnvelope(kind="event")` accepts either a `WorkEvent` or a
`RuntimeEventView`. Existing Work event JSON is unchanged. Runtime views use:

```json
{
  "event_family": "runtime",
  "event_id": "...",
  "kind": "agent.message_update",
  "stream_id": "session:...",
  "sequence": 7,
  "occurred_at": "2026-07-19T12:00:00+00:00",
  "event_type": "assistant_delta",
  "view": "assistant_stream",
  "delivery_hint": "coalesce",
  "payload": {"type": "assistant_delta", "delta": "..."}
}
```

`event_family` distinguishes the runtime representation only. Unknown
additive fields remain ignored by the existing object decoder. Channel does not
attempt Product event mapping, selector expansion, render enrichment,
subscription, acknowledgement, replay, or delivery scheduling.

## Dependency Direction

```text
harness.events     -> protocol
channel             -> work
channel             -> harness.events.projection (RuntimeEventView only)
coding.event        -> harness.events
coding.mode         -> coding.event
```

Harness has no Channel import. Channel may import only the projection value
module, never `harness.session`, a bus, publisher, store, Agent, AI, Coding,
Method, or TUI. This narrow direction lets an OEM Channel implementation carry
runtime views without making its transport part of the Host runtime.

## Coding Adoption

Coding retains `AgentSessionEvent` and its Pi-compatible serialisation. Its
runtime adapter maps an incoming `RuntimeEvent` to existing Coding session
events, applies Coding's selected JSON view and tool renderer, and constructs a
`RuntimeEventView`. JSON PrintMode and RpcMode subscribe to
`subscribe_runtime_events()` when the session offers it, then retain their
existing printed JSON and RPC stream shape. The old `subscribe()` path remains
only for text display and compatibility session doubles.

## Exclusions

This wave does not add a transport loop, channel registry, capability
negotiation, cross-process replay, acknowledgement/outbox, event persistence,
or a generic Product event language. Those need separate Channel and Host
contracts.
