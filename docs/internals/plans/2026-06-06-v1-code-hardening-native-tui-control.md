# V1 Code Hardening, Native TUI, And Method Runtime Control Plan

## Goal

Use the control lane to coordinate a short, high-intensity push on:

```text
V1 code hardening + Native TUI productization + Method runtime
```

This plan is a coordination artifact. It is not a detailed implementation plan
for any implementation lane.

## Lane Model

| Lane | Path | Branch rule | Responsibility |
| --- | --- | --- | --- |
| control | `/home/dev/workspace/loushang` | normally `main` | Progress control, direction, final verification, integration, merge/push |
| tui | `.worktrees/tui` | `feature/tui-*` or `lane/tui/*` | Native TUI productization, terminal rendering, playback, transcript reader, surfaces |
| code | `.worktrees/code` | `feature/code-*` or `lane/code/*` | V1 code hardening, CLI/runtime/session/tool/policy/diagnostics |
| method | `.worktrees/method` | `feature/method-*` or `lane/method/*` | Method/work runtime, method execution semantics, MethodPlan/WorkEvent projection |
| ai | `.worktrees/ai` | `feature/ai-*` or `lane/ai/*` | AI/provider/model/usage/auth work when active |
| agent | `.worktrees/agent` | `feature/agent-*` or `lane/agent/*` | Agent loop/session orchestration/queue/tool-call semantics when active |

Only the control lane normally checks out `main`. All other lanes use task
branches based on `main` or `origin/main`.

## Current State

- control lane is on `main` and aligned with `origin/main`.
- `docs/articles/` is untracked in the control lane and is intentionally outside
  this control plan.
- TUI lane exists at `.worktrees/tui` on `feature/tui-reader-footer-hints` with
  uncommitted transcript reader/footer hint changes. Focused tests pass:
  `tests/coding/test_native_tui_transcript_reader.py` and
  `tests/coding/test_native_tui_playback_harness.py`.
- code lane exists at `.worktrees/code` on `feature/v1-code-hardening`, created
  from current `main`. Baseline coding tests pass:
  `tests/coding/test_cli.py` and `tests/coding/test_bootstrap.py`.
- method lane exists at `.worktrees/method` on `feature/method-runtime`,
  created from current `main`. Baseline method/work tests pass:
  `tests/method`, `tests/work`,
  `tests/coding/domain/test_coding_domain_app.py`, and
  `tests/coding/test_prompt_command.py`.
- AI and agent lanes should be created only when active work requires them.

## Control Responsibilities

- Keep `main` as the integration fact.
- Maintain this plan as the short-term lane coordination artifact.
- Dispatch focused briefs to TUI/code/method/AI/agent agents.
- Review lane reports before integration.
- Run final verification in the control lane after merging lane work.
- Push only from the control lane unless explicitly agreed otherwise.

## Lane Rules

- Before switching branches in any lane, check dirty state.
- Do not overwrite uncommitted user or agent changes.
- Keep lane commits narrow and verifiable.
- Prefer frequent integration into `main` over long-lived divergent branches.
- Cross-lane contract changes must be clarified in the control lane before
  dependent lanes consume them.

## Initial Backlog

### P0: Lane Bootstrap

- [x] Inspect and classify existing TUI lane dirty changes.
- [x] Create `.worktrees/code` from current `main`.
- [x] Create `.worktrees/method` from current `main`.
- [x] Verify active implementation lanes have a clean or intentionally
  tracked baseline before assigning new work.

### P1: V1 Code Hardening

- Add an executable/source identity command or diagnostic surface so users can
  tell whether they are running the repo `.venv` script or a packaged binary.
- Tighten binary build/install documentation and version visibility.
- Identify the next narrow runtime/session/tool/policy hardening slice after the
  identity diagnostic is complete.

### P1: Native TUI Productization

- Finish or retire the current transcript reader/footer hints dirty work.
- Expand playback coverage around transcript reader, footer hints, resize, and
  modal input routing.
- Keep TUI changes inside product adapter / TUI boundaries unless a control-lane
  contract change has been accepted.

### P1: Method Runtime

- Clarify the next method-runtime slice beyond prompt injection: method identity,
  method plan facts, and work-event projection should be visible to execution
  without becoming another UI surface.
- Keep method semantics independent from CLI/TUI/RPC channel mechanics.
- Preserve ARD-006: `--method` remains deferred for Native TUI until method
  context can be represented and verified in-session.

## Active Briefs

### TUI Lane Brief

```text
Lane:
  /home/dev/workspace/loushang/.worktrees/tui

Branch:
  feature/tui-reader-footer-hints

Mission:
  Finish the current transcript reader/footer hints slice.

Allowed files:
  docs/internals/architecture/tui/native-terminal-core/key-designs/KD-018-transcript-reader-and-copy-semantics.md
  src/loushang/coding/ui/transcript_reader.py
  src/loushang/coding/ui/playback_scenarios/transcript.py
  tests/coding/test_native_tui_transcript_reader.py
  tests/coding/test_native_tui_playback_harness.py

Verification:
  uv --cache-dir /home/dev/workspace/loushang/.uv-cache run --extra dev pytest tests/coding/test_native_tui_transcript_reader.py tests/coding/test_native_tui_playback_harness.py -q
```

### Code Lane Brief

```text
Lane:
  /home/dev/workspace/loushang/.worktrees/code

Branch:
  feature/v1-code-hardening

Mission:
  Implement the first V1 code hardening slice: executable/source identity
  diagnostics so users can tell whether they are running the repo .venv script
  or a packaged binary.

Forbidden:
  Do not touch Native TUI renderer/playback internals in this slice.

Verification:
  Start with focused CLI tests, then run tests/coding/test_cli.py and
  tests/coding/test_bootstrap.py before reporting.
```

### Method Lane Brief

```text
Lane:
  /home/dev/workspace/loushang/.worktrees/method

Branch:
  feature/method-runtime

Mission:
  Identify and implement the next narrow method-runtime slice beyond prompt
  injection, preserving current non-interactive method behavior.

Allowed files:
  src/loushang/method/
  src/loushang/work/
  tests/coding/domain/test_coding_domain_app.py
  tests/coding/test_cli.py
  tests/coding/test_prompt_command.py
  docs/internals/specs/
  docs/internals/architecture/coding/

Forbidden:
  Do not enable --method in Native TUI or RPC mode in this slice.
  Do not rewrite existing method assets.
  Do not touch Native TUI renderer/playback internals.

Verification:
  Start with method-focused CLI/domain tests, then run any affected work/method
  integration tests before reporting.
```

## Agent Brief Template

```text
Lane:
  <worktree path>

Branch:
  <branch name>

Mission:
  <one narrow objective>

Allowed files:
  <paths or modules>

Forbidden:
  <paths, branch operations, or integration actions to avoid>

Inputs:
  <docs, tests, references>

Deliverables:
  <code, tests, docs, report>

Verification:
  <required commands>

Report:
  changed files
  decisions
  verification output
  residual risks
  next blockers
```

## Integration Checklist

Before merging a lane branch into `main`:

- The lane reports changed files, decisions, verification output, residual risks,
  and next blockers.
- Control lane reviews the diff.
- Required focused tests pass.
- Broader tests pass when the change crosses subsystem boundaries.
- `git diff --check` passes.
- The merge does not include unrelated worktree state or untracked artifacts.
