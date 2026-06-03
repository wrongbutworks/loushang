# `rpc`

## Role

- JSONL control protocol adapter for headless coding sessions

## Owns

- RPC command parsing and validation
- request/response correlation IDs
- stable success/error response envelopes
- wire compatibility for accepted field aliases such as `sessionId` / `session_id`
- response DTO projection, including camelCase conversion and safe JSON serialization
- event projection from `AgentSessionEvent` to JSONL output
- RPC-backed extension UI request/response transport

## Depends On

- `runtime`
- `session`
- `message`
- `event`
- `diagnostics`

## Commands

- `prompt`
- `steer`
- `follow_up`
- `abort`
- `new_session`
- `switch_session`
- `fork`
- `clone`
- `get_state`
- `get_messages`
- `list_sessions`
  - filters: `cwd`, `name`, `parentSession` / `parent_session`, `text` / `query`, `hasDiagnostics` / `has_diagnostics`, `limit`
  - `allSessions` / `all_sessions`: when true, uses runtime all-session lookup instead of current session-dir lookup
  - `useIndex` / `use_index`: when true, uses runtime indexed summary facade instead of direct JSONL scan facade
  - `refreshIndex` / `refresh_index`: when true, refreshes current or all-session index before listing; implies `useIndex`
- `set_model`
- `cycle_model`
- `get_available_models`
- `set_thinking_level`
- `cycle_thinking_level`
- `set_steering_mode`
- `set_follow_up_mode`
- `compact`
- `set_auto_compaction`
- `set_auto_retry`
- `abort_retry`
- `bash`
- `abort_bash`
- `get_session_stats`
- `get_last_assistant_text`
- `get_fork_messages`
- `get_commands`
- `get_diagnostics`
  - runtime/global diagnostics query
  - filters: `sessionId` / `session_id`, `entryId` / `entry_id`, `phase`, `source`, `level` / `diagnosticType` / `diagnostic_type`, `code`, `limit`
- `get_session_diagnostics`
  - current-session scoped diagnostics query
  - filters: `entryId` / `entry_id`, `phase`, `source`, `level` / `diagnosticType` / `diagnostic_type`, `code`, `limit`
- `get_diagnostics_summary`
  - runtime/global diagnostics summary query
  - filters: same as `get_diagnostics`, with optional `limit`
- `get_session_diagnostics_summary`
  - current-session scoped diagnostics summary query
  - filters: same as `get_session_diagnostics`, with optional `limit`
- `get_extension_ui_state`
  - headless extension UI snapshot for RPC clients
  - returns notifications, statuses, widgets, title/editor state, working indicator state, autocomplete provider count, and tools expanded state
- `get_last_error_report`
- `get_packages`
  - headless package/plugin projection for RPC clients
  - returns the same package entry shape used by CLI JSON output, including local package roots, local plugin packages, catalog entries, and registered remote plugin lifecycle entries
  - optional `catalogPath` / `catalog_path` merges an offline local catalog file without performing network install/update
- `materialize_package`
  - validates a remote package/plugin source and asks runtime/session package materializer to advance lifecycle state asynchronously
  - returns a stable `record` payload with `source`, `name`, `lifecycle`, `targetPath`, `security`, `errorMessage`, `pinned`, `requestedRef`, `resolvedCommit`, `installedCommit`, `dirty`, and `lastUpdatedAt`
- `install_package` / `uninstall_package`
  - high-level package manager operations that combine materialization/removal with settings source registration/removal
- `update_package` / `update_packages` / `check_package_updates`
  - source-level update, bulk update, and update availability projection for headless clients
- `export_html`

## Long-Term Helper Policy

Keep in RPC:

- protocol parsing and field alias compatibility
- payload type validation
- stable error normalization
- response serialization and camelCase DTO projection
- defensive JSON serialization at the process boundary
- JSONL writes must flush after each response/event so subprocess clients can observe command responses without waiting for process exit or buffer fill
- event and extension UI request projection

Move to `session`:

- single-session state transitions
- model and thinking-level cycling
- message extraction semantics
- session-level slash command aggregation and command execution semantics; RPC should prefer `AgentSession.list_commands()`
- compaction execution
- bash execution
- session-local diagnostics access

Move to `runtime`:

- active session replacement
- new/switch/fork/clone lifecycle
- cross-session listing/searching
- runtime-level diagnostics access
- package/plugin listing and lifecycle state projection
- package/plugin materialization lifecycle facade

## Out Of Scope

- direct `SessionManager` or store traversal
- direct agent state mutation
- model selection policy
- thinking-level ordering policy
- lifecycle policy for clone/fork/switch
- command execution context construction
- approval UI and optional package trust hardening; explicit package signature verification is not a current pi parity requirement

## Pi Alignment

- Match pi's architectural boundary rather than its exact TypeScript implementation.
- RPC should remain a thin command adapter that calls `AgentSessionRuntime` and `AgentSession`.
- Business logic belongs in `runtime` / `session`; RPC only validates inputs and serializes outputs.
- Loushang may keep extra headless commands such as `list_sessions` and diagnostics queries, but they must follow the same thin-adapter rule.

## Current Notes

- Existing tolerant serializers are intentional and should remain at the RPC boundary.
- Legacy business fallbacks inside RPC should be removed as session/runtime facades are added.
- The preferred handler shape is `validate -> call session/runtime facade -> serialize response`.
- `get_commands` should consume session-level descriptors and project them into RPC `sourceInfo` DTOs.
