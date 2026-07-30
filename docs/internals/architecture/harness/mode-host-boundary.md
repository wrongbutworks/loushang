# Mode Host Boundary

## Status

Implemented on `lane/harness` by the mode host collapse wave.

## Ownership

`coding.mode` is a Product entrypoint, not a second runtime. The shared
implementation is split by responsibility:

| Capability | Canonical owner | Product binding |
| --- | --- | --- |
| mode lifecycle actions and state-reader contract | `harness.host.mode` | Product host factory |
| JSONL input validation, routing, task draining and response lifecycle | `harness.host.rpc` + `harness.host.jsonl_command_host` | RPC event/diagnostic projection |
| plain and JSON output loop, session state observation and tool-line rendering | `harnesstui.conversation.plain_mode` | Work execution binding and event projection |
| operation grammar, prompt/queue/lifecycle/model/diagnostic handlers | `harness.session` and `harness.host.rpc` | Product ports and protocol profile |
| Channel framing, correlation, cancellation and delivery | `loushang.channel` | Product operation port |
| Work operation facts and Coding domain mapping | `loushang.work` / `loushang.coding` | Coding domain binding |

The shared RPC host receives `RpcEventProjection` and
`RpcDiagnosticsProjection` ports. It does not import Coding or decide a
Product's event names, diagnostic wire fields, or Work domain. The shared
plain host receives equivalent event and Work ports.

## Coding surface after cutover

Coding keeps only:

- `CodingChannelOperationPort` for `domain="coding"` Work operations;
- the Coding event view and diagnostics JSON projection;
- `CodingWorkShell`/`CodingWorkRuntime` binding for planned and ordinary turns;
- Product CLI factories and public import entrypoints.

`RpcMode` and `PrintMode` remain importable as thin Product adapters while
callers migrate to the shared host modules. They contain no JSONL loop,
session-operation dispatch, state serializer, task tracker, or plain output
orchestration.

## Protocol rule

The shared contracts use the current snake_case session/runtime API. No Pi SDK
aliases or Pi-specific command projection are part of this boundary. A
Product may expose a separate versioned wire profile, but that profile must
remain outside the shared host implementation.

## Verification

The existing Coding RPC, print, Channel, and JSON projection behavior tests
remain the regression suite. Architecture tests verify that HarnessTUI does
not import Coding, and that the moved RPC implementation is neutral.
