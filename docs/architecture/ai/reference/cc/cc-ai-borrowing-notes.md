# Claude Code Borrowing Notes For Loushang-AI

## Position

`cc` is not a direct structural template for `loushang-ai`.

It is closer to an application/runtime system with substantial REPL, UI, session,
and bootstrap state concerns. `loushang-ai` should not copy its overall
organization.

What is worth borrowing is a small set of local mechanisms and design habits.

## Worth Borrowing

### 1. Abort propagation utilities

Reference:

- [/home/dev/workspace/cc/src/utils/abortController.ts](/home/dev/workspace/cc/src/utils/abortController.ts)

Why it is useful:

- It treats cancellation as a tree, not a single flat signal.
- It handles parent-to-child propagation explicitly.
- It cleans up listeners when the child is aborted.
- It raises the listener limit to avoid noisy runtime warnings.

How `loushang-ai` should borrow it:

- Borrow the internal cancellation-tree idea.
- Keep the public `loushang-ai` contract at the protocol level as `aborted`.
- Do not expose runtime-level cancellation objects as the public semantic result.

### 2. Explicit adapter boundary

Reference:

- [/home/dev/workspace/cc/src/remote/sdkMessageAdapter.ts](/home/dev/workspace/cc/src/remote/sdkMessageAdapter.ts)

Why it is useful:

- It cleanly converts external SDK/remote message shapes into internal message
  or stream-event shapes.
- It explicitly ignores unsupported or irrelevant inbound message kinds.
- It keeps translation logic out of higher-level runtime code.

How `loushang-ai` should borrow it:

- Keep `Provider Adapter Component` as a narrow translation boundary.
- Normalize provider-specific events into `raw parts`, not directly into public
  events.
- Be explicit about ignored provider events instead of letting them leak into
  assembler logic.

### 3. Tool-use and tool-result pairing discipline

Reference:

- [/home/dev/workspace/cc/src/utils/groupToolUses.ts](/home/dev/workspace/cc/src/utils/groupToolUses.ts)
- [/home/dev/workspace/cc/src/services/compact/grouping.ts](/home/dev/workspace/cc/src/services/compact/grouping.ts)
- [/home/dev/workspace/cc/src/bootstrap/state.ts#L73](/home/dev/workspace/cc/src/bootstrap/state.ts#L73)
- [/home/dev/workspace/cc/src/utils/messages.ts](/home/dev/workspace/cc/src/utils/messages.ts)

Why it is useful:

- `cc` treats `tool_use` / `tool_result` pairing as a real invariant.
- It distinguishes between:
  - strict fail-fast behavior
  - repair / synthetic placeholder behavior
- It keeps this concern explicit instead of burying it in generic message code.

How `loushang-ai` should borrow it:

- Treat tool pairing as a first-class semantic rule inside `Tool Semantic
  Component`.
- Preserve room for both:
  - strict validation mode
  - repair-oriented compatibility mode
- Keep pairing policy out of `Top-Level AI API`.

### 4. Content-array placement rules

Reference:

- [/home/dev/workspace/cc/src/utils/contentArray.ts](/home/dev/workspace/cc/src/utils/contentArray.ts)

Why it is useful:

- It encodes a small but important API-shape rule: supplementary blocks should
  be inserted relative to `tool_result` blocks, and some API payloads should
  not end with non-text content.

How `loushang-ai` should borrow it:

- Keep content normalization rules explicit and local.
- Do not rely on callers to hand-craft provider-safe content arrays.
- Likely place this kind of logic under provider payload transformation, not in
  the public API layer.

### 5. API-round grouping as a future idea

Reference:

- [/home/dev/workspace/cc/src/services/compact/grouping.ts](/home/dev/workspace/cc/src/services/compact/grouping.ts)

Why it is useful:

- It groups transcript segments by assistant `message.id`, which approximates
  one API round-trip.
- This is a useful future idea for transcript compaction, replay, or debugging.

How `loushang-ai` should borrow it:

- Keep this as a future reference only.
- Do not pull it into `v0.1` minimal implementation.

## Not Worth Borrowing Directly

### 1. Large global bootstrap state

Reference:

- [/home/dev/workspace/cc/src/bootstrap/state.ts](/home/dev/workspace/cc/src/bootstrap/state.ts)

Why not:

- It centralizes many unrelated runtime concerns.
- It is appropriate for an application/runtime shell, not for `loushang-ai` as
  a focused subsystem.

### 2. Overall runtime organization

Why not:

- `cc` is optimized around REPL/runtime/session behavior.
- `loushang-ai` is being designed as a smaller, cleaner AI abstraction
  subsystem.

### 3. Internal message model as-is

Why not:

- `cc` message structures are tightly coupled to its rendering and session
  runtime.
- `loushang-ai` already has a better-fitting internal boundary:
  `provider adapter -> raw parts -> raw assembler -> event stream`.

## Recommendation

For `loushang-ai`, treat `cc` as a source of local implementation patterns,
not as a reference architecture.

The main borrowing priorities are:

1. abort propagation utilities
2. explicit adapter translation boundaries
3. strict tool pairing policy options
4. content normalization rules around tool results

The main non-goal is copying `cc`'s app/runtime structure.
