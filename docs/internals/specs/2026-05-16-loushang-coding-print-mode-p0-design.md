# Loushang Coding Print Mode P0 Design

## Goal

Build the first minimal `print mode` for `loushang-coding` as a thin output adapter over the existing runtime spine:

```text
AgentSessionRuntime -> AgentSession -> AgentSessionEvent -> print mode text projection
```

This P0 is intentionally single-shot:

- accept one user input
- run one session turn
- print readable text output
- exit with a process-style integer status

It is not a REPL, not a TUI, and not a second runtime core.

## Scope

### In Scope

- a `PrintMode` adapter object
- a `run_once(user_input) -> int` primary entrypoint
- a thin `run_print_mode(...) -> int` wrapper
- subscription to `AgentSessionEvent`
- readable text projection for:
  - assistant text
  - tool execution start/end
  - terminal completion / failure
- tests that prove the mode drives `AgentSession`, prints projected output, and returns expected exit codes

### Out Of Scope

- interactive loop / REPL
- multiline stdin orchestration
- rich terminal UI, colors, spinners, progress bars
- `stderr` split, shell formatting polish, or transcript pretty-printing
- `json mode`, `rpc mode`, or shared mode base
- compaction / retry / extension-specific display

## Recommended Approach

Use a small class-first adapter:

- `PrintMode(...).run_once(user_input) -> int`
- `run_print_mode(...) -> int` as a thin convenience wrapper

This keeps the single-shot P0 simple, while leaving a clean place to hold:

- the bound `runtime`
- the active `session`
- output stream handles
- event projection helpers

This is preferable to a single large function because future batch or REPL work will naturally need mode-local state.

## Architecture

### Position In The System

`print mode` remains an adapter layer. It must not call `Agent` directly.

It should only:

1. subscribe to `AgentSessionEvent`
2. call `session.prompt(...)`
3. wait for `session.wait_for_idle()`
4. project emitted events to text
5. return an integer exit code

That keeps the existing ownership model intact:

- `runtime` manages session lifecycle
- `session` remains the business orchestrator
- `print mode` handles I/O projection only

### Minimal Components

Recommended files:

- `src/loushang/coding/mode/__init__.py`
- `src/loushang/coding/mode/print_mode.py`
- `tests/coding/test_print_mode.py`

P0 should keep text projection in `print_mode.py` unless that file becomes noisy. There is no need to introduce a shared renderer layer yet.

## API Shape

### Primary Object

```python
class PrintMode:
    def __init__(
        self,
        *,
        runtime: AgentSessionRuntime,
        session: AgentSession,
        stdout: TextIO,
        stderr: TextIO | None = None,
    ) -> None: ...

    async def run_once(self, user_input: str) -> int: ...
```

### Thin Wrapper

```python
async def run_print_mode(
    *,
    runtime: AgentSessionRuntime,
    session: AgentSession,
    user_input: str,
    stdout: TextIO,
    stderr: TextIO | None = None,
) -> int: ...
```

The wrapper should do little more than instantiate `PrintMode` and delegate to `run_once(...)`.

## Event Projection Rules

P0 should optimize for readable terminal output, not complete event fidelity.

### Assistant Message

When the turn produces assistant text, print the text body in reading order.

Example shape:

```text
Done. I checked the repository and found ...
```

### Tool Execution

Tool events should be short, one-line summaries.

Suggested shape:

```text
[tool:bash] start
[tool:bash] end
```

P0 should not yet dump full structured args or full tool results by default. The point is to make progress visible without locking in a verbose textual protocol too early.

### Failures

If `session.prompt(...)` or `session.wait_for_idle()` raises, print a short error line and return non-zero.

Suggested shape:

```text
Error: <message>
```

### Ignored Events

P0 may ignore or silently coalesce:

- queue updates
- compaction placeholders
- auto-retry placeholders
- partial assistant streaming details beyond the final readable text

The adapter should stay intentionally narrow until `print mode` usage proves where more detail is needed.

## Run Flow

Expected `run_once(...)` sequence:

1. subscribe to the session
2. project relevant events as they arrive
3. call `await session.prompt(user_input)`
4. call `await session.wait_for_idle()`
5. unsubscribe
6. return `0` on success

If an exception occurs:

1. print the short error line
2. unsubscribe in `finally`
3. return a non-zero exit code

## Testing Strategy

P0 should be test-driven and avoid depending on a real CLI.

### Core Tests

1. `run_once()` calls `session.prompt(...)` with the provided input
2. assistant message events are projected to `stdout`
3. tool execution start/end events are projected to `stdout`
4. exceptions from the session produce non-zero exit code and error output
5. `run_print_mode(...)` behaves as a thin wrapper over `PrintMode`

### Test Style

Prefer fake session/runtime doubles over full integration setup for the mode tests. The mode contract is small and should be tested at the adapter boundary.

One additional integration-style test is useful if needed, but not required for P0.

## Follow-Up Path

If P0 works, the natural next increments are:

1. batch multi-input execution
2. richer tool result text
3. shared helpers between `print mode` and `json mode`
4. minimal CLI binding

Those are explicit follow-ups, not part of this slice.

## Acceptance Criteria

This design is satisfied when:

- there is a concrete `PrintMode` adapter in `src/loushang/coding/mode/`
- one input can be executed through `run_once(...)`
- assistant text is printed in a user-readable way
- tool start/end visibility exists
- success returns `0`
- failures return non-zero
- `tests/coding/test_print_mode.py` passes without requiring a full CLI stack
