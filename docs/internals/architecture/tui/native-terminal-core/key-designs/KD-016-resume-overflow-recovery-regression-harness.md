# KD-016: Resume Overflow Recovery Regression Harness

Status: Accepted. Partially implemented.

Implemented:

- deterministic resumed-session fixture for the `963306bf` silent-overflow shape
- overflow classification tests for empty/near-limit assistant stop responses
- session compaction/recovery tests for overflow handling
- native TUI resume / long transcript playback regressions

Still future/deferred:

- live-provider integration tests for the original session sample
- broad golden-snapshot approval of resumed transcript rendering

## Purpose

Define a repeatable, non-interactive regression harness for resumed coding
sessions that have already entered a bad provider-response state, so overflow
recovery fixes can be verified without manual TUI interaction.

## Problem

The `963306bf` session exposed a failure mode where a resumed coding session
accepted user prompts, returned to `idle`, and persisted new assistant messages,
but those assistant messages were empty `stop` responses instead of real
assistant output or explicit errors.

This is a poor fit for purely visual TUI testing:

- the primary failure is not layout corruption; it is a bad session/runtime
  state transition
- the relevant evidence already exists in persisted session history and agent
  events
- manual `--resume` verification is slow, hard to repeat, and easy to misread

The project needs a regression harness that can load a bad resumed session,
trigger one new prompt turn, and prove that recovery logic now engages instead
of silently appending more empty assistant messages.

## Scope

This design covers:

- persisted-session fixtures used to reproduce bad resumed-session states
- session-layer recovery tests that validate overflow detection and compaction
- a thin TUI playback smoke test that proves the resumed prompt path no longer
  degrades into silent `idle`

This design does not redefine:

- the overflow classification rules themselves
- compaction policy thresholds
- long-transcript render performance policy
- interactive end-to-end terminal automation against a real provider

Those remain covered by their own designs and tests.

## Design

The regression harness must be split into two layers:

- session recovery regression tests: the primary source of truth
- TUI playback smoke tests: a minimal behavioral confirmation layer

The session recovery layer must prove the recovery semantics. The TUI playback
layer must only prove that the resumed interactive path reflects those
semantics instead of silently ending in `idle`.

## Fixture Strategy

The harness must not depend on a user-home session path at test runtime.
Instead, it must use repo-owned test fixtures.

Two fixture shapes are allowed:

- full resumed-session fixture: a scrubbed copy of the real session jsonl
- minimized resumed-session fixture: only the tail region required to reproduce
  the bad-state behavior

The default should be the minimized fixture. The fixture must preserve only the
history required to reproduce these conditions:

- at least one existing compaction entry is already present
- the recovered branch/session context can be rebuilt from persisted entries
- the last assistant message is a `stop` response with empty content and near-
  or over-limit usage
- a subsequent prompt is expected to trigger overflow recovery instead of
  silently appending another empty assistant message

The fixture may be derived from a real session, but once checked into the repo
it becomes a deterministic regression sample rather than an external runtime
dependency.

## Primary Recovery Test Layer

The main regression test must execute at the coding session / controller layer,
not at the terminal-surface layer.

The primary test must:

- load the persisted resumed-session fixture into a `SessionManager`
- rebuild the session context exactly as a resumed coding session would
- identify the last assistant message from the restored session state
- execute the same pre-prompt or post-turn recovery path used by production
- assert that overflow recovery becomes eligible for the restored bad-state
  assistant message

The primary assertions are behavioral, not visual:

- the restored bad-state assistant is recognized as overflow or silent overflow
- auto-compaction is not incorrectly short-circuited by stale ordering logic
- the compaction controller emits `compaction_start`
- the compaction controller emits `compaction_end` with an overflow-oriented
  recovery reason
- the recovery path schedules or permits continuation rather than terminating
  silently

This layer is the authoritative regression proof. If this layer fails, the TUI
smoke layer is not sufficient to claim the bug is fixed.

## Thin TUI Smoke Layer

The TUI layer must remain intentionally thin.

It must not assert full-screen snapshots for the entire resumed interaction.
Instead, it should only verify that a resumed prompt path no longer reduces to
this silent-failure pattern:

- user prompt appended
- worked divider shown
- final footer returns to `idle`
- no assistant content, no recovery event, and no error/compaction trace

The smoke layer may use the playback harness or a fake prompt driver, but its
assertions must be limited to:

- resumed transcript loads successfully
- one resumed prompt can be injected
- the resulting session/TUI event stream includes recovery evidence or real
  assistant output
- the resulting transcript does not append another silent empty-assistant
  terminal state without any recovery trace

The TUI smoke layer exists to protect the user-visible path without making the
test suite brittle to unrelated layout or copy changes.

## Assertion Strategy

Assertions must be phrased in terms of stable behavior, not incidental text.

Preferred assertions:

- assistant message content emptiness versus non-emptiness
- stop reason and overflow classification
- compaction and retry/recovery events
- session-entry type transitions
- existence of real assistant output after recovery

Avoid relying on:

- exact footer strings
- full-screen terminal snapshots for the entire interaction
- precise line numbers in rendered transcript output
- unrelated transient timing text such as `Worked for ...`

The only permitted UI-level text assertions are small sentinel strings that are
already part of stable playback contracts, and even those should be used
sparingly.

## File Placement

The default implementation shape is:

- persisted fixture under `tests/fixtures/sessions/`
- session/controller regression test under `tests/coding/`
- optional thin playback smoke case in
  `tests/coding/test_native_coding_tui_playback.py`

The exact filenames are implementation details, but the fixture must live
inside the repo and the primary regression test must live in the coding-session
test layer rather than under TUI-only helpers.

## Failure Classification

The regression harness must be able to distinguish:

- fixed: recovery triggers and the resumed path no longer silently appends empty
  assistant stop messages
- still broken: resumed path continues to append empty assistant stop messages
  without recovery
- degraded in a different way: resumed path now surfaces a distinct explicit
  provider/runtime error

The last case is not necessarily a regression failure if the system now
correctly surfaces an explicit error instead of silently pretending the turn
succeeded. Tests should encode the intended behavior for the chosen recovery
policy, but the classification model must keep silent failure distinct from
explicit failure.

## Relationship To Existing Designs

- KD-001 remains responsible for render-loop behavior. KD-016 only adds a thin
  smoke layer around resumed prompt behavior.
- KD-006 remains responsible for committed transcript records, streaming drafts,
  and resumed display-record interpretation. KD-016 depends on those records as
  fixture input.
- KD-010 remains responsible for the playback harness itself. KD-016 constrains
  how playback should be used for resumed overflow recovery tests.
- KD-015 addresses long-transcript render planning. KD-016 addresses bad-state
  resumed-session recovery verification. They are related because the original
  reproduction came from a long transcript, but they solve different problems.

## Non-Goals

This design does not require:

- live-provider integration tests for the exact `963306bf` sample
- committing a full terminal video or screen capture of the failure
- reproducing the issue through a human-operated TUI session for routine CI
- broad golden-snapshot approval of resumed transcript rendering

## Test Obligations

- the repo contains a deterministic resumed-session fixture representing the bad
  silent-overflow state
- the primary coding-session regression test proves that resumed recovery logic
  engages for that fixture
- the regression test proves the system does not silently append another empty
  assistant `stop` response as the only outcome of the next prompt
- a thin playback smoke test proves the visible resumed prompt path reflects the
  recovery behavior without depending on full-screen snapshots
- the harness remains stable when unrelated footer copy or transcript styling
  changes
