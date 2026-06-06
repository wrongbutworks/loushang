# `domain`

## Role

- coding domain app integration boundary
- bridge from `loushang.method` assets to prepared coding turns
- method plan metadata projection into CLI runner and work-log paths

## Owns

- `CodingDomainRequest`
- `CodingDomainPreparedTurn`
- `MethodPolicy`
- `CodingDomainApp.prepare_turns(...)`
- method metadata 到 coding turn metadata 的 projection glue

## Does Not Own

- `MethodRegistry`
- `MethodLoader`
- `MethodCompiler`
- `MethodProjector`
- `MethodDescriptor`
- `MethodPlan`
- `MethodStep`

这些对象归属 `loushang.method`。`loushang.coding` 只消费它们，不重新定义
method resource ownership。

## Depends On

- `loushang.method`
- `prompt`
- `session`
- `loushang.work` when work logs are enabled

## Commands

- `prepare_turn(request)`
- `prepare_turns(request)`

The CLI-facing method commands are owned by `cli`, but they should delegate method
loading/selection/plan projection to `loushang.method` and `CodingDomainApp`:

- `--list-methods`
- `--show-method`
- `--show-method-plan`
- `--method`
- `--no-method`

## Queries

- none as a standalone coding component

Method list/show/plan queries are visibility surfaces over `loushang.method`
resources, not session-local method state.

## Events

- 当前无独立 coding domain event protocol

Method-driven non-interactive runs are observed through `loushang.work`:

- `WorkPlanStarted`
- `WorkStepStarted`
- `WorkStepCompleted`
- `WorkStepFailed`
- `WorkPlanCompleted`
- `WorkPlanFailed`

Step deviation is represented as `WorkStepDeviation` metadata, not as a separate
`step_deviation` event kind.

## Key Data

- `CodingDomainRequest`
- `CodingDomainPreparedTurn`
- `MethodPolicy`
- `MethodDescriptor`
- `MethodPlan`
- `MethodStep`
- `MethodProjection`
- `WorkEvent`
- `WorkPlanRun`
- `WorkStepRun`

## Out Of Scope

- method resource discovery ownership
- method registry lifecycle
- automatic method selection
- TUI method picker
- TUI method step status rendering
- work event log storage implementation

## Current Constraints

- `--method` is supported on non-interactive prompt/print/json paths.
- `--method` is rejected in TUI and RPC paths until ARD-006 preconditions are met.
- `--work-log` is supported for one-shot text/print/json prompts and rejected in TUI/RPC paths.
- Fixed linear `MethodPlan` execution is represented as one prepared coding turn per step.

## Reference Implementation Alignment

- `CodingDomainApp` keeps method application out of raw CLI/session code.
- `loushang.method` owns method resources and projection.
- `loushang.work` owns plan/step observability and replay semantics.
- `loushang.coding` owns only coding-specific assembly and execution routing.
