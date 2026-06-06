# V1 Code Hardening And Native TUI Control Plan

## Goal

Use the control lane to coordinate a short, high-intensity push on:

```text
V1 code hardening + Native TUI productization
```

This plan is a coordination artifact. It is not a detailed implementation plan
for either lane.

## Lane Model

| Lane | Path | Branch rule | Responsibility |
| --- | --- | --- | --- |
| control | `/home/dev/workspace/loushang` | normally `main` | Progress control, direction, final verification, integration, merge/push |
| tui | `.worktrees/tui` | `feature/tui-*` or `lane/tui/*` | Native TUI productization, terminal rendering, playback, transcript reader, surfaces |
| code | `.worktrees/code` | `feature/code-*` or `lane/code/*` | V1 code hardening, CLI/runtime/session/tool/policy/diagnostics |
| ai | `.worktrees/ai` | `feature/ai-*` or `lane/ai/*` | AI/provider/model/usage/auth work when active |
| agent | `.worktrees/agent` | `feature/agent-*` or `lane/agent/*` | Agent loop/session orchestration/queue/tool-call semantics when active |

Only the control lane normally checks out `main`. All other lanes use task
branches based on `main` or `origin/main`.

## Current State

- control lane is on `main` and aligned with `origin/main`.
- `docs/articles/` is untracked in the control lane and is intentionally outside
  this control plan.
- TUI lane exists at `.worktrees/tui` on `feature/tui-reader-footer-hints` with
  uncommitted changes that must be reviewed before branch switching.
- code lane is expected at `.worktrees/code` and should be created from current
  `main`.
- AI and agent lanes should be created only when active work requires them.

## Control Responsibilities

- Keep `main` as the integration fact.
- Maintain this plan as the short-term lane coordination artifact.
- Dispatch focused briefs to TUI/code/AI/agent agents.
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

- Inspect and classify existing TUI lane dirty changes.
- Create `.worktrees/code` from current `main`.
- Verify both active implementation lanes have a clean or intentionally tracked
  baseline before assigning new work.

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
