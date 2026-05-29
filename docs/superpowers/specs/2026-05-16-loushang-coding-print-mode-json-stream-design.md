# Loushang Coding Print Mode JSON Stream Design

## Goal

Extend the existing single-shot `PrintMode` so it supports both:

- `text` output for human-readable terminal use
- `json` output for JSON event stream integration

This feature does not introduce a separate `JsonMode` object. Instead, it keeps one single-shot mode adapter and adds a second output projection:

```text
AgentSessionRuntime -> AgentSession -> AgentSessionEvent -> PrintMode(text|json)
```

That keeps the runtime spine unchanged and stays aligned with `pi`, where JSON output is a variant of print mode rather than a separate runtime core.

## Scope

### In Scope

- extend `PrintMode` to accept an output mode of `text` or `json`
- keep `run_once(user_input) -> int` as the primary entrypoint
- keep `run_print_mode(...) -> int` as the thin wrapper
- in `json` mode:
  - write the session header as the first JSON line
  - write every supported `AgentSessionEvent` as one JSON line
- keep `stdout` as pure JSON Lines in `json` mode
- print failures to `stderr` and return non-zero
- add focused tests for header emission, event stream output, and failure behavior

### Out Of Scope

- a separate `JsonMode` class
- CLI binding
- REPL / interactive loop
- RPC mode
- event envelopes or custom JSON error records
- shared mode base across `print/json/rpc/interactive`
- richer final summary objects

## Recommended Approach

Use the existing `PrintMode` as the single-shot adapter and add a mode selector:

```python
output_mode: Literal["text", "json"]
```

This is preferable to adding a dedicated `JsonMode` because:

- the run flow is the same in both cases
- only the output projection changes
- it matches `pi`'s user-facing and implementation model
- it avoids building two nearly identical adapters too early

If a future `interactive` or `rpc` mode needs different control flow, that is the right time to introduce a shared base or split adapters further.

## Alignment With Pi

`pi` documents this feature as JSON Event Stream Mode:

- first line is the session header
- later lines are session events as JSON objects
- output is useful for integration with tools and custom UIs

Relevant references:

- [json.md](/home/dev/workspace/pi-mono/packages/coding-agent/docs/json.md)
- [print-mode.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/modes/print-mode.ts:17)

The important alignment points are:

1. `json` is an output projection over the same session runtime
2. `stdout` is reserved for structured JSON lines
3. the first line is the session header
4. later lines are session events in occurrence order

The main intentional difference is structural:

- `pi` implements JSON as a branch inside `runPrintMode(...)`
- `loushang` may keep the Python code slightly more explicit internally, but should preserve the same protocol semantics

## Architecture

### Position In The System

`PrintMode` remains an adapter only. It must not call `Agent` directly.

It should:

1. read the current session header from the active session manager
2. subscribe to `AgentSessionEvent`
3. call `session.prompt(...)`
4. call `session.wait_for_idle()`
5. project either text or JSON output
6. return a process-style exit code

Ownership stays unchanged:

- `runtime` owns session lifecycle
- `session` owns orchestration and event production
- `event` and `message` own JSON-ready payload projection
- `PrintMode` owns writing projected output to streams

### Adapter Shape

Recommended API:

```python
class PrintMode:
    def __init__(
        self,
        *,
        runtime: AgentSessionRuntime,
        session: AgentSession,
        stdout: TextIO,
        stderr: TextIO | None = None,
        output_mode: Literal["text", "json"] = "text",
    ) -> None: ...

    async def run_once(self, user_input: str) -> int: ...
```

Wrapper:

```python
async def run_print_mode(
    *,
    runtime: AgentSessionRuntime,
    session: AgentSession,
    user_input: str,
    stdout: TextIO,
    stderr: TextIO | None = None,
    output_mode: Literal["text", "json"] = "text",
) -> int: ...
```

## Output Rules

### Text Mode

`text` mode keeps the current P0 behavior:

- print assistant text in reading order
- print brief tool start/end lines
- print short failure lines to `stderr`

This spec does not redefine the text projection protocol.

### JSON Mode

`json` mode is a JSON event stream.

#### Header Line

Before sending the prompt, write one JSON line for the current `SessionHeader`.

Expected shape:

```json
{"type":"session","version":3,"id":"uuid","timestamp":"...","cwd":"/path","parentSession":"..."}
```

`parentSession` should be omitted or null exactly according to the chosen serializer contract, but the output must stay compatible with the existing session-file field naming.

#### Event Lines

After the header, every supported session event should be written as one JSON line using the existing serializer surface.

Coverage target is the full current `serialize_session_event(...)` support set:

- `agent_start`
- `agent_end`
- `turn_start`
- `turn_end`
- `message_start`
- `message_update`
- `message_end`
- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`
- `queue_update`
- `compaction_start`
- `compaction_end`
- `auto_retry_start`
- `auto_retry_end`

No event filtering should happen in P0 beyond "only events that already have a supported serializer".

### Error Behavior

In `json` mode:

- `stdout` must remain pure JSON Lines
- exceptions should print `Error: <message>` to `stderr`
- exit code should be non-zero

P0 should not introduce a JSON error envelope or terminal summary object.

## Serialization Boundary

`serialize_session_event(...)` already exists and should remain the event projection entrypoint.

The missing piece is a public session-header serializer. Today, header projection exists only as store-internal logic in [file_codec.py](/home/dev/workspace/loushang/src/loushang/coding/store/file_codec.py).

Recommended change:

- add a public `serialize_session_header(...)` helper in a reusable JSON projection module
- update store file writing to reuse it
- have `PrintMode` call that helper when `output_mode == "json"`

For P0, the simplest acceptable location is:

- [json_codec.py](/home/dev/workspace/loushang/src/loushang/coding/message/json_codec.py)

even though it currently focuses on messages. The key requirement is that `PrintMode` must not depend on store-private `_serialize_header(...)`.

## Run Flow

Expected `run_once(...)` sequence in `json` mode:

1. read the current session header
2. write the serialized header to `stdout`
3. subscribe to the session
4. on each event, serialize it and write one JSON line
5. call `await session.prompt(user_input)`
6. call `await session.wait_for_idle()`
7. unsubscribe in `finally`
8. return `0` on success

If an exception occurs:

1. print `Error: <message>` to `stderr`
2. still unsubscribe in `finally`
3. return non-zero

## Testing Strategy

This should be developed with focused adapter tests, not a CLI-first test shape.

### Core Tests

1. `text` mode still prompts the session and waits for idle
2. `json` mode writes the session header before event lines
3. `json` mode writes one JSON line per serialized event
4. `json` mode covers the full currently supported event family
5. failures in `json` mode write to `stderr` and return non-zero
6. `run_print_mode(...)` remains a thin wrapper
7. top-level exports still expose the print mode surface

### Test Style

Prefer fake session/runtime doubles and `StringIO` streams.

The most important verification points are:

- line order
- JSON parseability
- serializer reuse
- clean separation of `stdout` and `stderr`

## Acceptance Criteria

This design is satisfied when:

- `PrintMode` supports `output_mode="text"` and `output_mode="json"`
- `json` mode writes the session header first
- `json` mode writes event JSON lines in occurrence order
- `serialize_session_event(...)` is reused rather than bypassed
- `PrintMode` does not call store-private header helpers
- `stdout` remains pure JSON Lines in `json` mode
- failures return non-zero and write human-readable errors to `stderr`
- focused print-mode tests pass without requiring a CLI layer
