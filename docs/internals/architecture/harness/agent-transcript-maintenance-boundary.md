# Agent Transcript Maintenance Runtime Boundary

## Decision

`loushang.harness.agent_transcript` owns the standard maintenance mechanics
around an open Agent transcript:

- context token extraction and estimation from stable Agent/AI message values;
- context-window accounting, reserve/percentage thresholds, stale-checkpoint
  detection, and threshold decisions;
- standard compaction result, plan, preparation, status, lifecycle, checkpoint
  commit, common runtime events, and overflow-recovery guard;
- retry classification, retry/backoff/cancellation/waiter lifecycle, live
  failed-assistant removal, and common retry events.

This is an optional Agent/AI profile. `harness.conversation` and generic
`harness.context` stay independent of Agent and AI message types.

## Ownership

Harness provides:

```text
ContextUsageSnapshot / CompactionDecision
CompactionPlan / CompactionPreparation / CompactionResult / CompactionStatus
AgentTranscriptCompactionRuntime
AgentTranscriptRetryRuntime
```

The compaction runtime operates through the existing `AgentTranscriptSession`:
it reads the active branch, receives a Product-supplied preparation and summary
executor, appends the standard compaction checkpoint only after successful
execution, refreshes context, and publishes common lifecycle events. It does
not own prompt wording, a provider call, or an extension API.

The retry runtime consumes a `RetryPolicy`, a live message-state port, and
continuation/cancellation callbacks. It does not discover credentials, choose
a model, or dispatch Product UI events.

## Product Binding

A Product supplies:

- compaction policy defaults and runtime-selected settings;
- transcript preparation strategy, summary prompt, model call, and any
  Product-specific artifact details;
- extension before/after interception translation and diagnostics wording;
- context application, retry continuation, and Product presentation;
- model catalog, authentication, provider behavior, and approval policy.

Coding binds these ports through thin `CompactionController` and
`RetryController` adapters. Coding keeps its exact compaction and branch
summary prompts, model invocation, Coding extension hook mapping, diagnostics
projection, default settings, and TUI/RPC/HTML output projection.

## Dependency Rule

`harness.agent_transcript.maintenance` may import the public Agent message
aliases and stable `loushang.ai.types`. It must not import Coding, AI provider
calls, AI utility policy, model/provider registries, authentication, Product
configuration, or UI/RPC types. Product-specific strategy execution and
overflow classification are injected through callbacks rather than imported.

## Verification

- Harness tests cover context checkpoint staleness, compaction checkpoint
  commit/event ordering, and retry completion without importing Coding.
- Coding tests preserve compaction prompt/hook behavior, retry policy mapping,
  session state, and display projections.
- Architecture tests prohibit a Coding import from maintenance and require the
  Coding adapters to import the Harness runtimes.
