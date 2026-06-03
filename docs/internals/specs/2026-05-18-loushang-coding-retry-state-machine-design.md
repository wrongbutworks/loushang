# Loushang Coding Retry State Machine Design

**Date:** 2026-05-18

## Goal

Add a `pi`-aligned retry state machine to `AgentSession` so transient provider, server, and network failures can be retried with exponential backoff, while context overflow continues to route through compaction instead of retry.

## Design Summary

`retry` is a `session`-owned orchestration concern.

- `session` owns retry state, lifecycle, public retry APIs, and event emission.
- `control` owns retry policy through `RetrySettings`.
- `compaction` remains the overflow recovery path.
- `agent` continues to own the actual run and `continue_run()` execution.

This keeps retry as part of session deep behavior without turning `AgentSession` into a generic error-policy dumping ground.

## Public Session Surface

`AgentSession` will expose:

- `abort_retry() -> None`
- `wait_for_retry() -> None`
- `is_retrying: bool`
- `auto_retry_enabled: bool`
- `set_auto_retry_enabled(enabled: bool) -> None`

This matches the `pi` session surface closely enough for mode, CLI, and future UI callers to observe and control retry behavior.

## Retry Semantics

### Retryable Error Classification

`AgentSession` adds `_is_retryable_error(message: AssistantMessage) -> bool`.

Rules:

1. The message must be an assistant error message.
2. Context overflow is explicitly excluded and continues to route to compaction.
3. Remaining retryable failures are matched by transient-error text patterns:
   - overload / overloaded
   - rate limit / too many requests / `429`
   - `500`, `502`, `503`, `504`
   - service unavailable / server error / internal error
   - network / connection / fetch failed / socket hang up
   - timeout / timed out / terminated

The first version uses a conservative text classifier instead of provider-specific error taxonomy.

### State Machine

Retry has three internal states:

- `idle`
- `waiting_backoff`
- `retrying`

`is_retrying` is true whenever a retry future is active.

Flow:

1. `agent_end` arrives.
2. The last assistant message is inspected.
3. If the message is a retryable error:
   - check `RetrySettings`
   - increment attempt count
   - emit `auto_retry_start`
   - remove the trailing assistant error from `agent.state.messages`
   - wait with abortable exponential backoff
   - trigger `continue_run()`
4. A later successful assistant response emits `auto_retry_end(success=True, attempt=...)`.
5. Max retries exceeded or cancellation emits `auto_retry_end(success=False, final_error=...)`.

### Exponential Backoff

Backoff formula:

`delay_ms = base_delay_ms * 2 ** (attempt - 1)`

The wait must be abortable through `abort_retry()`.

## Compaction Boundary

Overflow remains a compaction concern.

- Retryable transient failures go through retry.
- Context overflow continues to go through `_compact_internal(reason="overflow", will_retry=True, ...)`.

This mirrors the `pi` split between overflow recovery and provider retry.

## Event Model

Existing event types remain unchanged:

- `auto_retry_start`
- `auto_retry_end`

`auto_retry_start` payload:

- `attempt`
- `max_attempts`
- `delay_ms`
- `error_message`

`auto_retry_end` payload:

- `success`
- `attempt`
- `final_error?`

## Testing Scope

The first implementation must cover:

1. retryable error classification
2. retry start and success end events
3. retry cancellation
4. max retry exhaustion
5. assistant error removal from `agent.state.messages`
6. overflow routing to compaction instead of retry

Out of scope for this iteration:

- provider-specific retry taxonomy
- richer retry diagnostics objects
- mode/UI retry interaction
- retry interaction with branch summary
