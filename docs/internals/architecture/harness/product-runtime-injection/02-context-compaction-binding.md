# Context Compaction Binding

## Status

Accepted implementation contract for the `harness/context-compaction-binding`
wave. The following two delivery commits replace Coding's private
compaction-runtime facade with a Harness-owned, transcript-aware capability.
They do not redefine compaction prompts or move model execution into Harness.

## Purpose And Requirements

`context.compaction` lets a Product select bounded-context behavior without
copying transcript planning, lifecycle, checkpoint, or diagnostic mechanics.
This component satisfies PDRI-001 through PDRI-012, with particular emphasis
on durable fact protection (PDRI-006), resume snapshots (PDRI-008), and
controlled contribution admission (PDRI-009).

The durable Agent transcript remains the source of truth. A compaction writes
a checkpoint that changes the context projection; it never deletes transcript
records. Memory retrieval and compaction are separate capabilities.

## Slot And Capability Shape

The existing `context.compaction` slot is a session-scoped, single selection
with a `turn` refresh boundary. A selection identifies one mechanism and a
strict JSON configuration:

```json
{
  "implementation": "agent_transcript.turn_aware_summary",
  "implementationVersion": 1,
  "config": {
    "enabled": true,
    "compactPercent": 80,
    "reserveTokens": 8192,
    "keepRecentTokens": 32768
  }
}
```

`agent_transcript.turn_aware_summary/v1` is the standard Harness mechanism.
It computes threshold and overflow decisions, preserves user-turn and tool
result boundaries, prepares a summary input, and commits an Agent transcript
compaction checkpoint exactly once after successful execution.

The initial schema deliberately contains only the four values that control
the established runtime semantics:

| Field | Meaning |
| --- | --- |
| `enabled` | Enables automatic threshold compaction. Manual compaction remains available. |
| `compactPercent` | Percent-of-context threshold. |
| `reserveTokens` | Reserve-based threshold. The lower threshold wins. |
| `keepRecentTokens` | Token budget retained from the newest transcript history. |

Unknown fields, non-integral token values, invalid percentages, and unsupported
mechanism versions fail profile binding. There is no implicit fallback to a
different mechanism.

## Ownership And Ports

Harness owns the mechanism and all product-neutral behavior:

- budget normalization and automatic threshold / one-shot overflow decisions;
- transcript cut-point planning, including previous checkpoints, complete turns,
  tool result non-cut boundaries, and split-turn preparation;
- cancellation, single-flight lifecycle, checkpoint commit ordering, retry
  continuation decisions, common runtime events, and diagnostics;
- mechanism identifier, version, configuration validation, snapshot semantics,
  and binding lifecycle.

The Product supplies three bounded ports:

1. a summary executor that transforms `CompactionPreparation` into
   `CompactionResult`;
2. an optional pre-compaction adapter, such as a Product extension hook;
3. an optional post-commit projection adapter.

The executor may call a model and use Product prompts, but it cannot choose a
different cut point or append a transcript record. Only Harness commits the
checkpoint. Coding therefore retains its code-change/file-operation summary
format, prompts, model/auth resolution, extension event translation, commands,
settings defaults, and UI/RPC projections.

Branch summarization is not context compaction. It remains a Product operation
and cannot produce a compaction checkpoint.

## Binding, Refresh, And Resume

The selected mechanism ID and version are session-stable because a resumed
transcript must retain the same checkpoint semantics. The slot may refresh at a
turn boundary only when the implementation and version are unchanged and the
runtime is idle; the refreshed JSON configuration applies to the next
compaction. Rebinding while a compaction is active fails rather than cancelling
or replacing the active operation.

The resolved runtime profile is persisted as session metadata. It records only
the mechanism ID, version, and JSON configuration; it never serializes prompt
text, credentials, model objects, executors, or extension instances.

## OEM And Extension Admission

The first implementation admits Product and trusted OEM selection of registered
Harness mechanisms. OEM configuration must pass the selected mechanism's
schema. Extensions may contribute ordinary Product hook instructions through
the Product adapter, but they may not register arbitrary Python planners,
executors, or transcript writers.

A later trusted-provider contract may admit an additional mechanism only after
it declares a versioned schema, lifecycle behavior, permission grant, and
contract suite. This restriction prevents `context.compaction` from becoming a
generic code-execution injection point.

## Failure And Transaction Rules

- Cancellation, executor failure, invalid preparation, and hook cancellation
  leave the transcript and current context projection unchanged.
- A successful executor result is appended once as a checkpoint before the
  context projection is refreshed or post-commit adapters run.
- A failed post-commit adapter is reported as a Product diagnostic and must not
  retry the append.
- Overflow recovery performs at most one compact-and-retry attempt per run.
- A branch-context summary is visible context but never a compaction boundary.

## Required Contract Tests

- configuration validation and JSON snapshot round-trip;
- default threshold parity with Coding's current settings;
- complete tool turn preservation, split-turn preparation, and previous-summary
  continuation;
- cancellation/failure leaves no checkpoint; successful execution appends one;
- overflow recovery and retry do not append duplicate summaries;
- an independent neutral executor can bind the standard mechanism;
- Coding retains its prompt/model executor but contains no private planner or
  `CodingCompactionRuntime` facade after cutover.
