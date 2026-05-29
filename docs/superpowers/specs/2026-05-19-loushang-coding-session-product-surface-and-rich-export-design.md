# Loushang Coding Session Product Surface And Rich Export Design

## Goal

Promote `loushang-coding`'s `session` from a deep internal orchestration center into a stable product-facing surface.

This design should:

- expose richer session queries similar to `pi`
- add a stable `ContextUsage` and `SessionStats` surface
- make export a first-class session capability
- define a rich `HTML` export target from the start
- still allow implementation to land in phases

## Scope

### In Scope

- formalize `AgentSession`'s product-facing query surface
- add `get_context_usage()`
- add `get_stats()`
- add `export_to_jsonl(...)`
- add `export_to_html(...)`
- define an internal split between:
  - session API surface
  - introspection/stat helpers
  - export helpers
- define a rich HTML export target that is closer to `pi`

### Out Of Scope

- new mode work
- new session actions beyond product queries/exports
- store protocol redesign
- plugin work
- UI runtime integration
- trying to make Phase 1 visually identical to `pi`

## Why This Comes Next

`loushang-coding` now already has most of the deep session behaviors that matter:

- `compaction`
- `branch summary`
- `retry`
- diagnostics snapshots
- richer built-in tools

The gap has shifted.

The remaining problem is not primarily "missing deep behavior." The problem is that the session still does not expose enough of that behavior as a stable product surface.

Compared with `pi`, the current `AgentSession` is still missing:

- a richer `ContextUsage` query
- a richer `SessionStats` query
- first-class JSONL export
- first-class HTML export

This design closes that gap without turning `AgentSession` into a dump of rendering code.

## Pi Alignment

Relevant `pi` references:

- [agent-session.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/agent-session.ts:1)
- [export-html/index.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/export-html/index.ts:1)
- [export-html/tool-renderer.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/export-html/tool-renderer.ts:1)

The alignment target is:

- `AgentSession` exposes richer product queries
- `ContextUsage` and `SessionStats` are session-level concepts
- export is a session capability, not an external utility
- rich HTML export is a first-class target, even if implementation lands in phases

This is semantic alignment, not a line-by-line port.

## Architecture

### Session API Surface

`AgentSession` should formally expose:

- `get_state()`
- `get_session_context()`
- `get_session_record()`
- `get_model_selection()`
- `get_active_tool_names()`
- `get_all_tools()`
- `get_last_diagnostics()`
- `get_last_error_report()`
- `get_context_usage()`
- `get_stats()`
- `export_to_jsonl(output_path: str | None = None)`
- `export_to_html(output_path: str | None = None)`

It should also continue to expose stable direct properties:

- `is_retrying`
- `is_compacting`
- `session_id`
- `session_name`
- `session_file`
- `messages`

### Internal Split

The implementation should not dump all of this logic directly into `agent_session.py`.

Recommended split:

```text
src/loushang/coding/session/
  agent_session.py
  types.py
  introspection.py
  export_jsonl.py
  export_html/
    __init__.py
    index.py
    template.html
    template.css
    template.js
    tool_renderer.py
```

Boundary rules:

- `AgentSession` owns the public API and orchestration
- `introspection.py` owns usage/stats aggregation
- `export_jsonl.py` owns transcript/session JSONL export logic
- `export_html/` owns rich HTML export rendering

This mirrors the design pattern already used for:

- `compaction`
- `retry`
- `diagnostics`

## Context Usage

### Goal

`ContextUsage` should be a richer product-facing view, not just a single token estimate.

It should align with `pi`'s spirit even if some fields are best-effort in Phase 1.

### Target Shape

Recommended `ContextUsage` fields:

- `message_count`
- `assistant_message_count`
- `user_message_count`
- `tool_call_count`
- `tool_result_count`
- `custom_message_count`
- `estimated_context_tokens`
- `has_compaction`
- `branch_depth`
- `leaf_entry_id`

### Source Strategy

This design explicitly allows best-effort aggregation in early phases.

The important rule is:

- the structure should be stable now
- precision may improve later

That means:

- message counts can be derived from `SessionContext`
- token usage can initially use existing `compaction` estimation helpers
- branch depth can come from current session/store state

Provider-perfect accounting is not required in Phase 1.

## Session Stats

### Goal

`SessionStats` should summarize the session as a product object, not just as raw transcript state.

### Target Shape

Recommended `SessionStats` fields:

- `session_id`
- `session_name`
- `entry_count`
- `message_count`
- `custom_message_count`
- `active_tool_count`
- `is_retrying`
- `is_compacting`
- `has_diagnostics`
- `branch_count`
- `last_model_selection`
- `context_usage`

### Boundary Rule

`SessionStats` should aggregate existing session/store/runtime state.

It should not become a second mutable session state object.

## Export Surface

### Product-Level Contract

Export should be a first-class `AgentSession` capability.

This design formalizes:

- `export_to_jsonl(output_path: str | None = None)`
- `export_to_html(output_path: str | None = None)`

### JSONL Export

`export_to_jsonl(...)` should:

- export a stable transcript/session artifact
- reuse current session/store data rather than inventing a second transcript format
- be suitable for archival, debugging, and reproducible replay inspection

If `output_path` is omitted, the API may return a generated path or serialized output according to the final implementation choice, but the contract must be stable and documented in the plan.

### Rich HTML Export

The target HTML export should be richer than a transcript dump.

The product target includes:

- session metadata header
- stats/context usage summary
- transcript timeline
- user / assistant / custom messages
- tool call / tool result rendering
- compaction / branch summary / retry markers
- markdown rendering
- code block highlighting
- template-based stylesheet and assets

This target is intentionally closer to `pi`'s HTML export experience.

## Rich HTML Export Design

### Rendering Structure

The HTML exporter should be template-based.

Recommended structure:

- `template.html`
- `template.css`
- `template.js`
- `tool_renderer.py`

This allows:

- stable page structure
- reusable styling
- better tool output rendering
- future refinement without changing the session API

### Rendering Responsibilities

The exporter should distinguish between:

- message rendering
- tool rendering
- metadata/stats rendering

`tool_renderer.py` should own the rendering rules for:

- tool calls
- tool results
- error vs success presentation
- structured detail blocks

### Markdown And Code

The target HTML export should support:

- markdown rendering for message text
- code block highlighting

Phase 1 may implement a simpler version, but the product contract should already assume richer rendering support.

## Phase Strategy

This design explicitly allows full target shape first and phased implementation second.

### Phase 1

Ship:

- `get_context_usage()`
- `get_stats()`
- `export_to_jsonl(...)`
- rich HTML export, first version
  - template-based
  - timeline rendering
  - metadata/stats section
  - basic tool rendering

Phase 1 may use best-effort usage accounting and simpler HTML internals, as long as the public contract is stable.

### Phase 2

Refine:

- richer tool rendering
- better markdown rendering
- better code highlighting
- stronger visual grouping and polish
- any deeper usage accounting improvements

This phase refines the same public API. It does not redefine it.

## Query And Export Semantics

### Query Stability

`get_context_usage()` and `get_stats()` should be safe read-only queries.

They must not:

- mutate session state
- require session idleness
- trigger compaction/retry/navigation side effects

### Export Stability

Exports should operate against the current session/store state and produce deterministic artifacts for that snapshot of the session.

They may:

- rebuild session context
- read entries and diagnostics

They must not:

- mutate the session transcript
- alter branch state
- consume queued steering/follow-up messages

## Expected Outcome

After this work:

- `AgentSession` will feel more like a product surface and less like an internal façade
- `ContextUsage` and `SessionStats` will be stable concepts
- JSONL export will become a first-class session capability
- HTML export will have a richer long-term target from day one
- implementation can still land in phases without changing the public session surface

That is the intended gain: the deep session behaviors already exist; this design makes them visible and consumable as product features.
