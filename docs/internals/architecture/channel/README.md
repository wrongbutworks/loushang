# Loushang Channel Architecture

## Scope

`loushang.channel` owns boundary protocol primitives for clients, hosts, SDKs,
RPC surfaces, and future WebUI/AppUI adapters.

The current implementation is intentionally small. It defines endpoint and
envelope types that can carry `loushang.work.WorkOperation` and
`loushang.work.WorkEvent` across a boundary.

## Current Package Surface

Current code package:

```text
src/loushang/channel/
  __init__.py
  types.py
```

Current public types:

- `ChannelEndpoint`
- `ChannelEnvelope`
- `ChannelEnvelopeKind`
- `ChannelPayload`

`ChannelEnvelope` accepts only two payload families:

- `kind="operation"` with a `WorkOperation`
- `kind="event"` with a `WorkEvent`

This first surface is a protocol skeleton, not a transport implementation.

## Ownership

`loushang.channel` may depend on `loushang.work` because the channel boundary
carries work operations and work events.

`loushang.channel` must not depend on:

- `loushang.agent`
- `loushang.coding`
- `loushang.method`
- `loushang.tui`

Product packages remain responsible for turning domain-specific input into
`WorkOperation` objects and for projecting `WorkEvent` objects into product or UI
state.

## Not In Scope

The current channel package does not implement:

- JSONL, HTTP, WebSocket, or in-process transport adapters
- request/response correlation
- capability negotiation
- replay or audit storage
- UI layout, widgets, or rendering
- direct agent loop or product session control

The next likely implementation step is a small `rpc_jsonl` adapter design that
maps JSONL framing onto `ChannelEnvelope` without reusing the legacy
coding-specific RPC command table.
