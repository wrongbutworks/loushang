# Loushang Coding Overflow Compaction Recovery Design (Pending Review)

**Date:** 2026-05-29

**Status:** Pending review. Do not implement directly from this note without review.

## Goal

Close the current overflow recovery gap in `loushang-coding` so oversized context does not leave the session in a permanently failing state.

The target behavior is `pi`-aligned:

- provider overflow or request-size failures must enter a stable recovery path
- recovery must compact context and continue from the existing session state
- recovery must not re-send the original user prompt
- recovery must stop after one failed compact-and-retry attempt

## Observed Failure

Current `loushang` behavior has a gap between `agent` and `coding`.

- `coding` has compaction logic before prompt and after `agent_end`
- `agent` can still fail earlier when the provider raises directly during request setup or streaming
- when that happens, no assistant error message is materialized
- without an assistant error message, `agent_end`-driven overflow handling does not run
- the oversized context stays in `agent.state.messages`
- subsequent prompts, even trivial ones, keep failing with the same token-limit error

This is most visible when a large tool result expands context during the same run and the next assistant request fails before the session-level compaction path gets control.

## Pi Mechanism To Align With

`pi` closes this loop with three connected behaviors.

### 1. Run Failure Is Converted Into Assistant Failure Output

The harness catches `runAgentLoop()` exceptions and emits a synthetic assistant failure message, then still emits:

- `message_end`
- `turn_end`
- `agent_end`

This ensures downstream recovery logic always sees a normal terminal assistant message instead of a raw exception.

Relevant references:

- [pi/packages/agent/src/harness/agent-harness.ts](/home/dev/workspace/pi/packages/agent/src/harness/agent-harness.ts:502)
- [pi/packages/agent/src/harness/agent-harness.ts](/home/dev/workspace/pi/packages/agent/src/harness/agent-harness.ts:522)

### 2. Overflow Recovery Removes The Trailing Error Message, Compacts, Then Continues

`pi-coding-agent` treats context overflow as a compaction concern, not a generic retry concern.

When the last assistant message is an overflow error:

1. remove the trailing assistant error from live agent context
2. compact session history
3. rebuild context from session state
4. call `agent.continue()`

This resumes from the compacted context instead of re-sending the user message.

Relevant references:

- [pi/packages/coding-agent/src/core/agent-session.ts](/home/dev/workspace/pi/packages/coding-agent/src/core/agent-session.ts:1795)
- [pi/packages/coding-agent/src/core/agent-session.ts](/home/dev/workspace/pi/packages/coding-agent/src/core/agent-session.ts:1865)

### 3. Pre-Prompt Check Covers Stale Overflow/Error State

Before accepting a fresh user prompt, `pi-coding-agent` checks the last assistant message and may compact first. This catches aborted or failed previous runs that left the session near or beyond context limits.

Relevant reference:

- [pi/packages/coding-agent/src/core/agent-session.ts](/home/dev/workspace/pi/packages/coding-agent/src/core/agent-session.ts:1010)

## Loushang Design Summary

Align `loushang` in two layers.

### Layer A: Agent-Level Failure Normalization

`loushang.agent` should normalize provider/request exceptions into a terminal assistant error message and emit a normal end-of-run sequence.

Required effect:

- `coding` receives a standard assistant error message with `stop_reason="error"`
- existing session/event routing remains usable
- overflow classification can happen from the resulting assistant message

This is the minimum required fix. Without it, later session-level overflow logic remains bypassable.

### Layer B: Session-Level Overflow Recovery Loop

`loushang.coding` should own overflow recovery as:

1. classify the last assistant error as context overflow
2. remove the trailing assistant error from live context
3. run compaction
4. rebuild live context from session state
5. call `continue_run()`
6. allow at most one overflow recovery attempt per failure chain

This should remain separate from transient provider retry.

## Required Behavior Changes

### 1. Agent Failure Must Still Reach `agent_end`

`loushang` must not let provider request exceptions abort the run before a terminal assistant message exists.

Expected result:

- a 400 token-limit provider failure becomes an assistant error message
- `agent_end` still fires
- session observers can react normally

### 2. Overflow Recovery Must Use Continue, Not Re-Prompt

After compaction, recovery should resume from current context with `continue_run()`.

It must not:

- inject a duplicate user message
- rebuild a synthetic user prompt
- depend on the caller to re-enter the same text

### 3. Overflow Recovery Must Be Single-Shot

If one compact-and-continue attempt still overflows, stop and emit a stable final error such as:

`Context overflow recovery failed after one compact-and-retry attempt. Try reducing context or switching to a larger-context model.`

### 4. Pre-Prompt Compaction Must Remain

The existing pre-prompt compaction hook in `PromptController` should stay, but after agent-level failure normalization it becomes reliable for previous-turn cleanup instead of being the only meaningful fallback.

## Recommended Implementation Order

### Phase 1: Minimum Recovery Closure

1. Add agent-level run-failure normalization.
2. Ensure `coding` receives assistant error messages for provider exceptions.
3. Route overflow assistant errors into compact-and-continue recovery.
4. Enforce one overflow recovery attempt.

This phase fixes the current stuck-session behavior.

### Phase 2: Turn-Boundary Hardening

Add a `pi`-style next-turn preparation hook between completed tool execution and the next assistant request.

Purpose:

- rebuild context from persisted session state
- make compaction decisions at a stable turn boundary
- reduce same-run failures caused by large tool results

### Phase 3: Request Preflight

Before sending a provider request, estimate context tokens locally and compact proactively when the threshold is already exceeded.

This is an optimization and hardening step, not the primary correctness fix.

## Non-Goals

This design note does not yet approve:

- changing compaction summary format
- broad retry-policy refactors
- tool-specific context elision redesign
- TUI-specific UX changes

## Review Focus

The review should focus on these questions:

1. Should run-failure normalization live inside `agent_loop`, `Agent`, or a higher wrapper?
2. Should `loushang.agent` grow a first-class `prepare_next_turn` hook similar to `pi`?
3. Is the current `coding` compaction controller the right owner for overflow recovery continuation, or should post-run orchestration move into a dedicated session-level state machine?
4. Do any existing retry paths conflict with the proposed overflow-specific continue flow?
