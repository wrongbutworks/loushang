# Channel RPC JSONL Boundary

## Decision

`loushang.channel.rpc_jsonl` is the first reusable headless Channel adapter.
It maps one JSONL frame to one Work-boundary message. It does not reuse or
wrap `loushang.coding.mode.RpcMode`.

The protocol has four frame kinds:

| Frame | Direction | Meaning |
| --- | --- | --- |
| `operation_request` | client to host | One `ChannelEnvelope(kind="operation")` and a client `request_id`. |
| `operation_accepted` | host to client | The host accepted the request. It contains the request, operation, and optional run id. |
| `event` | host to client | One `ChannelEnvelope(kind="event")`, optionally correlated to the source request. |
| `error` | either direction | A transport or acceptance failure, never a replacement for a `WorkEvent`. |

`operation_accepted` is deliberately only an ACK. Completion, cancellation,
failure, progress, and artifact facts remain `WorkEvent` messages.

## Ownership

Channel owns:

- JSONL frame encoding and exactly-one-frame decoding;
- request/event/error envelope validation;
- request correlation fields; and
- strict JSON transport projection for documented transport values.

Work owns operation, run, event, delivery-hint, and domain semantics. Products
own the conversion from their input into a `WorkOperation`, operation dispatch,
event projection, host policy, and rendering. Coding keeps its legacy RPC
command table, Coding event schema, and extension UI widget vocabulary.

The adapter may depend on `loushang.work` and `loushang.protocol` only. It must
not import AI, Agent, Harness, Coding, Method, or TUI runtime packages.

## Evolution

Frame decoders tolerate unknown additive fields. New frame kinds are rejected
until this adapter explicitly supports them. This preserves the existing Channel
rule: unknown Work kinds and payload fields may pass through, but the transport
frame grammar remains explicit.

No cross-process exactly-once delivery, replay, subscription persistence,
capability negotiation, or interaction/UI protocol is claimed by this batch.
