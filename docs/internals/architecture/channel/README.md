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
  host.py
  json_codec.py
  jsonl_command_host.py
  json_projection.py
  product_host.py
  remote_ui.py
  rpc_jsonl.py
  stdout_guard.py
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

`product_host.py` provides reusable Product-host lifecycle mechanics without a
wire schema: `ProductHostAction` / `ProductHostAdapter`, line-input
`ProductHostRuntime`, and `ProductHostTaskTracker`. Standard Channel JSONL and
Product-specific compatibility hosts may share those mechanics while retaining
their separate protocols.

`stdout_guard.py` preserves a raw protocol stdout stream while routing incidental
process output to stderr. It is available to any Product whose JSON or JSONL
transport requires a clean stdout contract.

The Product-owned JSONL command-host surface provides:

- `JsonlCommand` and `JsonlCommandHostError` as strict input observations;
- `JsonlCommandHost` and its injected `JsonlCommandPort`; and
- `RemoteUiContext` for request correlation, dialog timeout, and headless UI
  state without a standardized widget wire schema.

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
socket, HTTP server, or Product command table. `host.py` supplies the standard
stdio JSONL loop over an injected `ChannelHostPort`: a Product port accepts a
`WorkOperation`, emits the accepted ACK, and later delivers `WorkEvent` or
`RuntimeEventView` frames. `request_id` supplies transport correlation while
`operation_id` and `run_id` retain Work ownership. See
[Channel Host Boundary](channel-host-boundary.md).

[Product Host Runtime Boundary](product-host-runtime-boundary.md) records the
separate lower-level host lifecycle shared by standard Channel and
Product-specific host adapters.

`jsonl_command_host.py` supplies a separate, injected strict-JSON input loop
for Product-owned JSONL command schemas. It does not define a second standard
Channel frame grammar or response envelope. `remote_ui.py` supplies request
correlation, dialog timeout, and snapshot mechanics through a Product-injected
emitter; it does not standardize widget or extension payloads. See
[JSONL Command Host Boundary](jsonl-command-host-boundary.md).

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

- HTTP, WebSocket, or in-process transport loops
- operation dispatch or a WorkRun state machine
- capability negotiation
- replay or audit storage
- UI layout, widgets, rendering, or a universal UI wire protocol
- direct agent loop or product session control
- a universal Product RPC command schema

Capability negotiation and interaction request/response contracts remain
future work. They must remain independent of legacy Coding RPC widget and
editor payloads.
