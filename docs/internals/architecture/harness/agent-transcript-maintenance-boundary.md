# Agent Transcript Maintenance Runtime Boundary

## Decision

`loushang.harness.agent_transcript` owns the standard maintenance mechanics
around an open Agent transcript:

- context token extraction and estimation from stable Agent/AI message values;
- context-window accounting, reserve/percentage thresholds, stale-checkpoint
  detection, and threshold decisions;
- standard compaction result, plan, preparation, status, lifecycle, checkpoint
  commit, common runtime events, and overflow-recovery guard;
- stable Agent-message serialization plus standard compaction, turn-prefix, and
  branch-summary execution through the public AI completion surface;
- branch-delta selection, branch-summary normalization, cancellation, and
  transcript-summary event ordering;
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
it reads the active branch, receives a Product-selected preparation strategy and
summary binding, appends the standard compaction checkpoint only after
successful execution, refreshes context, and publishes common lifecycle events.
`harness.agent_transcript.summarization` owns the reusable model-call and
message-serialization mechanism; it accepts Product prompt profiles,
completion selection, and JSON-safe summary decoration. It does not own prompt
wording, provider discovery, credentials, model policy, or an extension API.

The same optional Agent transcript profile owns branch-delta preparation and
summary execution. A branch summary is a normal visible transcript record, not
a compaction checkpoint, and a Product supplies only its prompt/profile,
domain detail decoration, and presentation.

The retry runtime consumes a `RetryPolicy`, a live message-state port, and
continuation/cancellation callbacks. It does not discover credentials, choose
a model, or dispatch Product UI events.

## Product Binding

A Product supplies:

- compaction policy defaults and runtime-selected settings;
- transcript preparation selection, summary prompt/profile, model and
  credential selection, and any Product-specific artifact details;
- extension before/after interception translation and diagnostics wording;
- context application, retry continuation, and Product presentation;
- model catalog, authentication, provider behavior, and approval policy.

Coding binds compaction ports directly in `AgentSession`; the retry runtime is
already bound there as well. Coding keeps its exact compaction and branch
summary prompts, model invocation, Coding extension hook mapping, diagnostics
projection, default settings, and TUI/RPC/HTML output projection.

## Dependency Rule

`harness.agent_transcript.maintenance` may import public Agent message aliases
and stable `loushang.ai.types`. The adjacent optional
`harness.agent_transcript.summarization` module may additionally use the
public `loushang.ai` completion surface. Neither module may import Coding, AI
provider registries, provider implementations, authentication resolution,
Product configuration, or UI/RPC types. Product-specific prompt/profile,
completion selection, artifact decoration, and overflow classification are
injected through explicit values or callbacks.

## Verification

- Harness tests cover context checkpoint staleness, compaction checkpoint
  commit/event ordering, and retry completion without importing Coding.
- Harness tests cover summary serialization, compaction/branch execution,
  prompt-independent cancellation, and JSON-safe output without Coding.
- Coding session tests preserve Coding prompt/profile, file-detail decoration,
  extension-hook, retry-policy, session-state, and display behavior.
- Architecture tests prohibit a Coding import from maintenance and require the
  Coding session binding to consume the Harness runtimes directly.
