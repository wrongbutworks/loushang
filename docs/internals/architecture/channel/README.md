# Loushang Channel Architecture

## Scope

`loushang.channel` owns boundary protocol primitives for clients, hosts, SDKs,
RPC surfaces, and future WebUI/AppUI adapters.

The implementation defines endpoint and envelope types that carry
`loushang.work.WorkOperation`, `loushang.work.WorkEvent`, and a projected
`loushang.harness.events.RuntimeEventView` across a boundary, plus a
deliberately narrow JSONL framing adapter for headless clients.

## Current Package Surface

Current code package:

```text
src/loushang/channel/
  __init__.py
  json_codec.py
  json_projection.py
  rpc_jsonl.py
  types.py
```

Current public types:

- `ChannelEndpoint`
- `ChannelEnvelope`
- `ChannelEnvelopeKind`
- `ChannelPayload`

Current public codec helpers:

- `channel_envelope_to_json`
- `channel_envelope_from_json`

The `rpc_jsonl` surface provides:

- `ChannelOperationRequest` for a correlated operation submission;
- `ChannelOperationAccepted` for a minimal accepted ACK;
- `ChannelEventDelivery` for a correlated `WorkEvent` or `RuntimeEventView`
  delivery;
- `ChannelError` for transport or acceptance failure;
- strict `encode_rpc_jsonl_frame` / `decode_rpc_jsonl_frame` helpers that own
  one-frame JSONL encoding only; and
- `project_channel_value` for documented dataclass, `Path`, mapping, list, and
  tuple transport projection without arbitrary-object coercion.

`ChannelEnvelope` accepts two envelope kinds and three payload families:

- `kind="operation"` with a `WorkOperation`
- `kind="event"` with a `WorkEvent` or `RuntimeEventView`

`WorkEvent` remains the normalized work/audit event contract. A
`RuntimeEventView` is a Product-selected, transport-safe view of a transient
Host/Session fact. It preserves the source event id, stream, sequence,
timestamp, and source references, while carrying only an event type, view
name, delivery hint, correlation id, and strict JSON payload.

The two event families intentionally remain distinct. Work event JSON keeps
its current wire shape. Runtime views use `event_family: "runtime"` inside the
event payload, so decoders can reconstruct the view without interpreting it as
a Work event. This is additive to existing Work channels.

`json_codec.py` converts envelopes to and from JSON-compatible Python dicts.
`rpc_jsonl.py` maps those envelopes onto one JSONL frame at a time. It has no
stdio loop, socket, HTTP server, dispatcher, or Product command table. A host
accepts a `WorkOperation`, emits the accepted ACK, and later delivers
`WorkEvent` frames; `request_id` supplies the transport correlation while
`operation_id` and `run_id` retain Work ownership.

## Ownership

`loushang.channel` may depend on `loushang.work` because the channel boundary
carries work operations and work events. It may also depend only on
`loushang.harness.events.projection.RuntimeEventView` to transport an already
projected runtime observation.

That is a value-contract dependency, not a runtime dependency: Channel must
not import a Harness session, event bus, publisher, store, or Product adapter.
Harness must not import Channel. Products select and create runtime views; the
Channel package only frames and delivers them.

`loushang.channel` must not depend on:

- `loushang.agent`
- `loushang.ai`
- `loushang.coding`
- `loushang.method`
- `loushang.tui`

Product packages remain responsible for turning domain-specific input into
`WorkOperation` objects, projecting `RuntimeEvent` into `RuntimeEventView`, and
projecting Work events into product or UI state.

## Not In Scope

The current channel package does not implement:

- stdio, HTTP, WebSocket, or in-process transport loops
- operation dispatch or a WorkRun state machine
- capability negotiation
- replay or audit storage
- UI layout, widgets, or rendering
- direct agent loop or product session control

The next likely implementation step is channel capability negotiation and
interaction request/response contracts. Those must remain independent of the
legacy Coding RPC widget and editor payloads.
