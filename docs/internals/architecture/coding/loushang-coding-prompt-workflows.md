# Loushang Coding Prompt Workflows

## Status

Implementation direction, May 15, 2026. This document records the path from the
current control-flow scenario runners and single-prompt CLI toward first-class
prompt workflow commands such as:

- `loushang -p "prompt"` / `loushang --prompt "prompt"`: run one prompt
  against a coding session and render the product transcript.
- `loushang -ps workflow.yaml`: run a prompt script or workflow against a
  coding session or deterministic fake backend.

The implementation point is now `src/loushang/coding/workflow/`. It provides a
small auxiliary engine for loading workflow files, executing steps, recording
normalized events, and checking assertions. It is not a replacement for
`AgentSessionRuntime`; real workflows adapt into the existing runtime, and fake
workflows use a deterministic adapter for fast regression.

The older scripts remain useful references:

- `scenarios/coding/control_flow_session.py` exercises prompt control-flow
  contracts in a hand-authored deterministic runner.
- `scenarios/coding/tui_lifecycle_session.py` drives `run_coding_tui` through
  inline prompt callbacks so UI lifecycle behavior can be reproduced without a
  manual terminal or a live model.

The current fake workflow scenarios live under `scenarios/coding/workflows/`.

## Goals

- Make prompt, steer, follow, abort, and recovery behavior scriptable.
- Reproduce race-sensitive TUI failures without manual terminal input.
- Keep deterministic fake scenarios fast enough for local debugging.
- Allow future live scenarios to run against real models with explicit opt-in.
- Reuse the same step model for manual scenarios and future CLI workflows.

## Non-Goals

- Do not make the deterministic scenario runner a product CLI yet.
- Do not hide provider or tool failures behind silent recovery.
- Do not put live model scenarios in the unit-test suite.
- Do not require `LOUSHANG_LIVE_MODEL_TESTS` for manual scenario execution.

## Workflow Layers

Prompt workflows have three layers:

1. Prompt smoke workflows: sequential real-session prompts plus file, command,
   and assistant-text assertions. Example: `scenarios/coding/bmi.workflow.yaml`.
2. Fake control-flow workflows: deterministic prompt, steer, follow-up, abort,
   wait, and expect actions. These are fast enough for unit tests and do not call
   a model.
3. Future live and TUI playback workflows: the same action vocabulary backed by
   real `AgentSessionRuntime` events or prompt_toolkit key playback.

Methodology workflows, such as TDD or debugging recipes, should be templates
above this engine. They should compile down to workflow steps rather than add
new runtime behavior to the runner.

## Step Model

Prompt workflows are ordered steps. The current vocabulary is:

- `prompt`: start a user turn.
- `hold`: keep the run active so control actions can race with it.
- `steer`: send mid-run steering text.
- `follow_up`: queue follow-up intent for the current run.
- `abort`: interrupt the active run.
- `wait`: sleep for a fixed number of seconds to model timing gaps.
- `wait_for`: wait until an event has happened.
- `expect`: assert state after the workflow.

The fake backend uses normalized workflow events such as `run.started`,
`run.aborted`, `assistant.message`, `queue.steer_added`, and
`queue.follow_up_added`.

`expect` supports these workflow-level assertion groups:

- `events`: normalized events that must exist.
- `not_events`: normalized events that must not exist.
- `queue`: legacy queue convenience checks using `steering` and `follow_up`.
- `session_state`: partial checks against the adapter session-state snapshot.
  Nested objects are matched recursively, so scenarios can assert facts such as
  `runStatus`, `pendingMessageCount`, and `queue.followUp` without depending on
  the full runtime payload.
- `session_stats`: partial checks against reference-style session stats, including
  `tokens`, `cost`, `contextUsage`, and `latestCompaction`.
- `context_usage`: partial checks against the current context usage snapshot.
  This exists as a direct assertion path so compaction scenarios can inspect
  usage facts without nesting through stats.

Example:

```yaml
name: abort recovery
backend: fake
steps:
  - prompt: 请详细阅读 src/loushang/coding/ui/mode.py 并分析控制流
    hold: true
  - wait_for:
      event: run.started
      timeout_s: 1
  - wait: 0.01
  - abort: {}
  - wait_for:
      event: run.aborted
      timeout_s: 1
  - prompt: 你好
  - expect:
      events:
        - event: assistant.message
          contains: 你好
      not_events:
        - event: assistant.message
          contains: 请详细阅读
      queue:
        steering: []
        follow_up: []
      session_state:
        runStatus: idle
        pendingMessageCount: 0
        queue:
          steering: []
          followUp: []
      session_stats:
        latestCompaction:
      context_usage:
        messageCount: 2
```

## Control-Flow Contracts

A prompt workflow is valid only if these contracts hold:

- Abort is terminal for the active run: no later tool end, assistant final, or
  repeated cancellation error should be emitted for that run.
- After abort cleanup settles, the next prompt starts a new run normally.
- Steering during an active run is recorded as steering, not as a new prompt.
- Follow-up during an active run is recorded separately from steering.
- Provider cancellation is treated as intentional only when the active abort path
  requested it.
- Error events from stale aborted runs must not poison later prompts.

## CLI Direction

`loushang -p` is the small single-prompt product surface. It:

- Create or resume one coding session.
- Submit one prompt.
- Renders the same stable transcript blocks as TUI: user prompt, assistant/tool
  summary blocks, and a worked divider.
- Exit with a non-zero status when the turn ends in an unsuppressed error.

`--mode print` remains the lower-level print adapter. It is for callers that
want the historic text projection of session events. It does not own the product
`-p` semantics and should not grow TUI-style transcript behavior.

`loushang -ps` loads a workflow file or a directory of `*.workflow.yaml`,
`*.workflow.yml`, and `*.workflow.json` files. It:

- Executes the ordered step model above.
- Uses the real `AgentSession` adapter when `backend` is omitted.
- Uses the deterministic fake adapter when `backend: fake`.
- Prints workflow and per-step progress before waiting on the model or backend.
- Applies step timeouts so a stuck provider stream does not silently hang forever.
- In `--mode json`, suppresses human progress lines and emits one JSON report
  containing workflow, normalized event, step, and check results.

Manual commands:

```bash
uv --cache-dir .uv-cache run loushang --no-session -ps scenarios/coding/bmi.workflow.yaml
uv --cache-dir .uv-cache run loushang -ps scenarios/coding/workflows/abort-recovery.workflow.yaml
uv --cache-dir .uv-cache run loushang --no-session -ps scenarios/coding/workflows
uv --cache-dir .uv-cache run loushang --mode json --no-session -ps scenarios/coding/workflows
uv --cache-dir .uv-cache run pytest tests/coding/test_workflow_scenarios.py -q
```

TUI maps prompt submission by runtime state:

- Idle `Enter`: submit a new prompt.
- Running `Enter`: send steering text into the active run.
- Running `Alt+Enter`: queue follow-up text with `session.follow_up(<text>)`.
- `Ctrl+J`: insert a newline in the composer.
- `Esc` / `Ctrl-C`: abort the active run.

Queued steering and follow-up messages are shown transiently under the
`Working` line while the active run is still open. Steering is labeled as
messages to submit after the next tool call, and follow-up is labeled as
messages to submit at the end of the turn.

`/follow <text>` remains a text fallback for follow-up intent, but the primary
interactive path is the running `Alt+Enter` keybinding.

## Promotion Path

1. Keep `src/loushang/coding/workflow/` as an auxiliary engine.
2. Continue migrating deterministic control-flow scenarios into workflow files.
3. Add richer wait and expectation patterns only when a real scenario needs
   them.
4. Revisit real-runtime action workflows after fake control-flow regression is
   stable.
5. Add TUI playback on top of the same action semantics, keeping visual layout
   tests separate from runtime correctness tests.
