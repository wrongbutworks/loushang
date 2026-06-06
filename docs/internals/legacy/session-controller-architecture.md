# SessionController Architecture for Multi-Terminal / Multi-Interface Support

## Status

Legacy architecture note.

This document records an older multi-interface SessionController proposal. Use it
as background for future multi-client work only. Current coding runtime/session
boundaries are documented in the live coding architecture and component
interface docs.

## Context

The current loushang coding architecture is fundamentally single-terminal:

- `AgentSessionRuntime` manages **one** `_current_session` and has **one** `_rebind_session` callback.
- `ModeAdapter` instances (`PrintMode`, `RpcMode`) each subscribe directly to the session.
- The CLI creates **one runtime → one session → one mode adapter** per invocation.

The goal is a `SessionController` abstraction that allows **multiple terminals**
(e.g., TUI + WebSocket + RPC) and **multiple interface types** (TUI, CLI, Web, RPC,
etc.) to attach to the same session simultaneously, with centralized session
lifecycle management.

---

## Current Architecture (Simplified)

```
CLI main
  └── creates AgentSessionRuntime (singleton per process)
        └── manages single AgentSession (current_session)
              ├── PrintMode subscribes directly (one-shot)
              ├── RpcMode subscribes directly (long-running JSONL loop)
              └── _listeners: list[SessionEventListener]  (already multicast!)

AgentSessionRuntime._rebind_session: single callback
  → called on new_session / restore_session / fork_session / replace_current_session
```

**Key observation**: `AgentSession.subscribe()` already supports multiple listeners
and returns an unsubscribe callable. The gap is purely at the **runtime→UI
coordination layer**: only one callback gets notified when the session changes.

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Terminal / Interface Layer  (multiple, concurrent, heterogeneous)       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐ │
│  │  TUI Mode   │  │  RPC Client │  │ WebSocket   │  │  CLI (one-shot)│ │
│  │  (textual)  │  │  (JSONL)    │  │   Server    │  │   PrintMode    │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └───────┬────────┘ │
│         │                │                │                 │          │
│         └────────────────┴────────────────┴─────────────────┘          │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  SessionController                                               │   │
│  │  - attach(terminal_id, adapter) → bind to current session       │   │
│  │  - detach(terminal_id) → unbind                                 │   │
│  │  - set_session(session) → subscribe once, fan-out to all        │   │
│  │  - broadcast_event(event) → render_event() on all adapters      │   │
│  │  - submit_input(terminal_id, msg) → input arbiter (lock)        │   │
│  │  - active_terminals: list of attached TerminalHandle            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  AgentSessionRuntime (modified)                                  │   │
│  │  - set_session_controller(controller) replaces set_rebind_session│   │
│  │  - _run_rebind_session() → controller.set_session() or fallback │   │
│  │  - dispose() → controller.detach_all() before session cleanup   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  AgentSession (no changes needed)                                │   │
│  │  - subscribe() already multicasts                                │   │
│  │  - prompt()/steer()/follow_up() queued, safe for multi-source    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Abstractions

### 1. SessionController

**Location**: `src/loushang/coding/runtime/session_controller.py`

Responsibilities:
- Maintain a registry of attached terminals (`TerminalHandle` objects).
- Hold the **single** subscription to `AgentSession` and fan-out events to all
  terminals via `adapter.render_event()`.
- Act as **input arbiter**: serialize `prompt()` calls across terminals to
  prevent double-start races. When a prompt is already active, new input is
  automatically downgraded to `steer()` or `follow_up()`.
- On session switch, unsubscribe from old session, subscribe to new session,
  and call `adapter.rebind_session()` on all terminals.
- Provide query APIs: `active_terminal_count`, `get_terminal_ids()`,
  `get_terminal_state(terminal_id)`.
- Handle last-terminal-detached policy (configurable: keep-alive or auto-dispose).
- Route extension UI responses to the correct terminal (see
  [Extension UI Context](#extension-ui-context) below).

```python
class SessionController:
    def __init__(self, runtime: AgentSessionRuntime) -> None: ...

    def attach(self, terminal_id: str, adapter: ModeAdapter) -> None: ...
    def detach(self, terminal_id: str) -> None: ...
    def detach_all(self) -> None: ...

    def set_session(self, session: AgentSession | None) -> None: ...
    def get_session(self) -> AgentSession | None: ...

    # Input arbiter
    async def submit_input(
        self,
        terminal_id: str,
        message: str,
        *,
        images: list[object] | None = None,
        streaming_behavior: str | None = None,
    ) -> None: ...

    @property
    def active_terminal_count(self) -> int: ...
    def get_terminal_ids(self) -> tuple[str, ...]: ...
    def get_terminal_state(self, terminal_id: str) -> ModeState: ...
```

### 2. TerminalHandle

Internal wrapper around a `ModeAdapter` + terminal identity. Decouples the
adapter from direct session subscription when under controller management.

```python
@dataclass
class TerminalHandle:
    terminal_id: str
    adapter: ModeAdapter
    _session: AgentSession | None = None
    # Each terminal gets its own UI context so extensions can route
    # dialogs (select / confirm / input / editor) to the correct terminal.
    ui_context: RpcExtensionUIContext | None = None

    def bind_session(self, session: AgentSession | None) -> None:
        self._session = session
        self.adapter.rebind_session(session)

    def render_event(self, event: AgentSessionEvent) -> None:
        self.adapter.render_event(event)

    def get_state(self) -> ModeState:
        return self.adapter.get_mode_state()
```

### 3. AgentSessionRuntime Integration

**File**: `src/loushang/coding/runtime/agent_session_runtime.py`

Changes:
1. Add `_session_controller: SessionController | None = None` field.
2. Add `set_session_controller(controller)` method. When set, clears the legacy
   `_rebind_session` callback.
3. Modify `_run_rebind_session()`:
   ```python
   async def _run_rebind_session(self, session: AgentSession) -> None:
       if self._session_controller is not None:
           self._session_controller.set_session(session)
       elif self._rebind_session is not None:
           await self._rebind_session(session)
   ```
4. Modify `dispose()` to call `self._session_controller.detach_all()` if present.
5. **Backward compatibility**: If no controller is set, behavior is identical to
   today.

---

## Integration with Existing Components

### ModeAdapter Protocol

**No breaking changes.** The existing `ModeAdapter` protocol already has the
right shape:
- `rebind_session(session)` — called by controller on session switch
- `render_event(event)` — called by controller on every event
- `get_mode_state()` — queried by controller for terminal state

New optional methods (for future terminal-aware features):
- `get_terminal_capabilities()` → what views/filters this terminal supports
- `set_event_filter(filter)` → per-terminal event projection

These can be added as optional protocol methods without breaking existing
adapters.

### RpcMode

When used **under a controller**:
- The controller manages the session subscription, so `RpcMode` should NOT call
  `session.subscribe()` in `__init__`.
- Instead, `RpcMode` should rely on `render_event()` being called by the
  controller.

**Implementation strategy**: Add an optional `controller: SessionController | None
= None` parameter to `RpcMode.__init__()`. If `controller` is provided, skip
direct subscription; the controller will fan out events. If `controller` is
`None`, behave exactly as today (direct subscription).

```python
def __init__(self, ..., controller: SessionController | None = None):
    ...
    self._controller = controller
    if controller is None:
        # Legacy path: direct subscription
        self.session = self._require_current_session()
        self._unsubscribe = self.session.subscribe(self._handle_event)
    else:
        # Controller path: controller manages subscription
        self.session = self._require_current_session()
        self._unsubscribe = lambda: None
```

### PrintMode

PrintMode is **not intended as a long-lived attached terminal**. It is a one-shot
adapter that subscribes inside `run_once()` and unsubscribes immediately after.
Therefore it **does not participate in controller-managed event fan-out**.

When used under a controller:
- PrintMode runs in **legacy one-shot mode** only.
- It bypasses the controller and directly calls `session.subscribe()` /
  `session.prompt()` as it does today.
- The controller does not attach PrintMode via `attach()`.

If a one-shot terminal ever needs controller-managed events, a new adapter
(e.g. `OneShotMode`) should be created that receives events via
`render_event()` without self-subscribing.

### CLI Main

**No changes required for backward compatibility.** The existing `mode_runner`
injection point can be extended:

```python
# Current (single terminal):
return await mode_runner(config=ModeConfig(mode="rpc"), runtime=runtime, ...)

# Future (multi-terminal, e.g., server mode):
controller = SessionController(runtime)
controller.attach("rpc-1", RpcMode(...))
controller.attach("websocket-1", WebSocketMode(...))
# Server loop waits for all terminals to detach
```

The CLI can continue creating single-terminal sessions. A new entry point
(e.g., `loushang server`) would use the controller.

---

## Event Flow: Before vs After

### Before (Single Terminal)
```
AgentSession._emit_event()
  → AgentSession._dispatch_event()
    → RpcMode._handle_event()     [direct listener]
    → ExtensionRunner.emit_event() [extensions]

AgentSessionRuntime._replace_with_manager()
  → _run_rebind_session()
    → single callback (e.g., TUI rebind)
```

### After (Multi-Terminal with Controller)
```
AgentSession._emit_event()
  → AgentSession._dispatch_event()
    → SessionController._on_event()  [single listener]
      → RpcMode.render_event()
      → WebSocketMode.render_event()
      → TUI.render_event()
    → ExtensionRunner.emit_event()    [extensions unchanged]

Terminal A.submit_input("hello")
  → SessionController.submit_input("A", "hello")
    → acquire _prompt_lock
    → session.prompt("hello")

Terminal B.submit_input("world")   [while A's prompt is active]
  → SessionController.submit_input("B", "world")
    → lock is held → session.steer("world")

AgentSessionRuntime._replace_with_manager()
  → _run_rebind_session()
    → SessionController.set_session(new_session)
      → unsubscribe from old session
      → subscribe to new session
      → RpcMode.rebind_session(new_session)
      → WebSocketMode.rebind_session(new_session)
      → TUI.rebind_session(new_session)
```

---

## Files to Create / Modify

| File | Action | Description |
|------|--------|-------------|
| `src/loushang/coding/runtime/session_controller.py` | **Create** | `SessionController`, `TerminalHandle` |
| `src/loushang/coding/runtime/__init__.py` | **Modify** | Export `SessionController` |
| `src/loushang/coding/runtime/agent_session_runtime.py` | **Modify** | Integrate controller, backward compat |
| `src/loushang/coding/mode/base.py` | **Modify** | Optional protocol extensions |
| `src/loushang/coding/mode/rpc_mode.py` | **Modify** | Optional controller-aware init |
| `src/loushang/coding/mode/print_mode.py` | **Modify** | Optional controller-aware init |
| `tests/coding/runtime/test_session_controller.py` | **Create** | Unit tests |
| `examples/coding/session_controller_01.py` | **Create** | Demo: two RPC terminals on one session |

---

## Key Design Decisions

1. **Controller owns the single session subscription** — not individual terminals.
   This prevents N subscriptions for N terminals and gives the controller
   visibility into all event traffic.

2. **Backward compatibility is mandatory** — existing CLI, tests, and embedders
   must work without changes. The controller is opt-in via
   `runtime.set_session_controller()`.

3. **Controller is the input arbiter** — terminals MUST route input through
   `controller.submit_input()` rather than calling `session.prompt()` directly.
   The controller holds an `asyncio.Lock` to ensure only one `prompt()` is
   active at a time. When a prompt is already running, new input is
   automatically downgraded to `steer()` or `follow_up()`. This prevents
   double-start races that `agent.is_streaming` alone cannot guard against.

4. **Session lifecycle stays in AgentSessionRuntime** — the controller does not
   create, fork, or dispose sessions. It only manages the broadcast layer. This
   preserves the existing runtime as the single source of truth for session
   state.

5. **Terminal identity is a string ID** — simple and serializable. Future
   enhancements can add metadata (capabilities, event filters) per terminal.

6. **ModeAdapter protocol is preserved** — no breaking changes. New optional
   methods for advanced features.

---

## Extension UI Context (MVP Requirement)

`AgentSession` currently holds a single `_extension_ui_context`. When multiple
RPC terminals share one session, the last terminal to `rebind_session()`
overwrites the context, causing extension dialogs (select / confirm / input /
editor) to route responses to the wrong terminal.

**MVP solution**: The controller maintains the UI context mapping.

1. Each `TerminalHandle` carries its own `RpcExtensionUIContext`.
2. The controller provides a multiplexed UI context to the session:
   ```python
   class _MultiplexedUIContext:
       def __init__(self, controller: SessionController):
           self._controller = controller
       async def select(self, title, options, *, timeout=None):
           # Route to the terminal that triggered the extension
           terminal = self._controller._active_terminal_for_extension()
           return await terminal.ui_context.select(title, options, timeout=timeout)
       # ... same for confirm, input, editor, notify, etc.
   ```
3. The controller intercepts `extension_ui_response` messages and dispatches
   them to the correct terminal by ID.

This keeps `AgentSession` unchanged while making extension UI terminal-aware.

---

## Future Extensions (Out of Scope for MVP)

- **Per-terminal event filtering**:
  `SessionController.attach(terminal_id, adapter, event_filter=...)`
- **Terminal capabilities negotiation**: `ModeAdapter.get_terminal_capabilities()`
- **Server/daemon entry point**: `loushang server --port 8080` with WebSocket +
  RPC
- **Session pinning**: Allow different terminals to view different sessions
  (multi-session controller)

---

## Verification Plan

1. **Unit test**: Attach 3 mock terminals to a controller, switch session,
   verify all 3 receive `rebind_session()` and subsequent events.
2. **Backward compat**: Run existing CLI tests with NO controller set —
   behavior unchanged.
3. **RpcMode standalone**: Run RpcMode without controller — direct subscription
   still works.
4. **RpcMode with controller**: Run RpcMode with controller — events come
   through controller fan-out.
5. **Example**: `session_controller_01.py` demonstrates two mock terminals
   sharing one session.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Double-start race on concurrent `prompt()` calls | Controller `submit_input()` holds an `asyncio.Lock`; concurrent prompts are serialized. New input during an active prompt is downgraded to `steer()` / `follow_up()`. |
| Extension UI context overwritten by last rebinding terminal | Controller provides a `_MultiplexedUIContext` to the session. Each terminal keeps its own `RpcExtensionUIContext`; the controller routes dialog requests/responses by terminal ID. |
| Event ordering across terminals | Controller dispatches sequentially; order is deterministic |
| Performance with many terminals | Controller holds single subscription; fan-out is O(N) per event. Acceptable for N < 100. |
| Memory leak on terminal detach | `detach()` drops the `TerminalHandle` reference. Add weakref fallback if needed. |
| Recursive dispose on `runtime.dispose()` | `controller.detach_all()` **only** unbinds terminals and cancels the session subscription. It **never** calls `adapter.dispose()`. Adapter lifecycle is managed by the terminal/server layer. |
