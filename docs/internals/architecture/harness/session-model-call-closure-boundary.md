# Session And Model-Call Closure Boundary

## Status

Status: accepted implementation contract for PR8. Production closure remains
pending until the acceptance matrix in this document passes.

This boundary defines how one current Product Session, its committed Capability
graph, its authoritative transcript, and every Harness-managed model call fit
together. It refines PR8 of the
[Capability Runtime Convergence Plan](capability-runtime-convergence-plan.md)
without introducing another Agent loop, provider runtime, transcript store, or
generic transaction framework.

## Authorities

The following authorities remain separate:

- `SessionTransitionHost` owns the single current-Session pointer and the
  irreversible release/publication order;
- the Session-owned `RuntimeCapabilityGraphRuntime` owns its committed Mount
  generation and registration inventory;
- the existing Agent transcript unit of work owns durable conversation facts;
- AI owns `PreparedModelRequest`, provider attempt identity, and the final
  pre-transport barrier; and
- `ModelInputTranscriptCommitter` projects one logical sampling input and the
  final provider payload into the authoritative transcript.

No combined mutable authority is added. In particular, a Model Input snapshot
references Profile, Mount, and registration clocks; it does not publish or
repair those clocks.

## Session And Candidate-Graph Nesting

The current Session publication point remains the assignment performed by
`SessionTransitionHost.replace`. A candidate Capability graph is a private,
rollback-capable child of its candidate Session until that assignment.

The required order is:

```text
serialize Session operation
  -> construct candidate Session and candidate-private stores/registries
  -> plan and commit the candidate Capability graph privately
  -> run all veto-capable old-Session release callbacks
  -> clear the current-Session slot
  -> dispose the old Session and its graph
  -> publish the candidate Session pointer
  -> activate/rebind Product adapters
  -> run after-commit observers
```

The graph commit before Session publication is not a second public publication.
Candidate registrations must either target candidate-private registries or
remain staged; they must not change the current Session's effective surface.

Failure semantics are fixed as follows:

- candidate construction or graph binding failure disposes the complete
  candidate and leaves the old Session current and usable;
- a veto-capable before-release failure does the same;
- old-Session disposal failure leaves the current slot empty and rolls back the
  unpublished candidate, because the old Session may already be partly
  disposed and must not be republished;
- after the candidate pointer is published, activation, rebind, or after-commit
  failure is reported as post-publication degradation and never resurrects the
  old Session; and
- candidate rollback and Session shutdown join their owned graph,
  registration, retry, compaction, side-question, and watcher cleanup before
  reporting completion.

These rules preserve the existing transition evidence in
`tests/harness/runtime/test_transition.py::test_transition_host_does_not_publish_session_after_dispose_failure`
and
`tests/harness/runtime/test_session_operations.py::test_session_operation_reports_after_commit_without_rolling_back`.
They do not require a cross-Store transaction or rollback of an object after
its irreversible disposal has started.

Only the current Session may create a Model Input committer. The committer must
capture that Session's exact transcript leaf/revision and exact committed graph
and registration snapshots. A candidate graph cannot authorize model transport
before its Session is current.

## Per-Sampling Committer

One static committer cannot close an Agent run. A main turn may sample more
than once after Tool results, queued input, or retry, and each committed Model
Input advances the transcript revision. The Session composition therefore
provides a per-sampling factory or equivalent narrow adapter that:

1. runs after Agent context transformation and Tool projection;
2. captures the current transcript leaf and revision;
3. captures the current committed Profile/Mount/registration references;
4. assigns an explicit invocation purpose;
5. creates a fresh `ModelInputTranscriptCommitter` for the logical input; and
6. injects that committer into AI's existing `CallOptions` before calling the
   normal AI entrypoint.

AI still prepares the final provider payload, invokes the committer, checks
cancellation, and begins transport. Harness never reconstructs provider
payloads and AI never imports Harness.

One AI provider retry retains its `invocation_id` and increments
`PreparedModelRequest.attempt`; the same per-sampling committer records each
prepared attempt. A Product-level retry or a later Tool/queue continuation is
a new logical sampling invocation with a new committer and invocation ID.

## Model-Call Inventory

Every Harness-managed path must resolve to one of the following rows. The
table describes semantic invocations; several rows intentionally share the one
Agent-loop sampling site.

| ID | Path and evidence | Purpose | Required durable boundary |
| --- | --- | --- | --- |
| MC-01 | Main prompt through `src/loushang/agent/agent.py::_run_prompt_messages` and `src/loushang/agent/agent_loop.py::_collect_assistant_response` | `main` | The user/application prompt is committed before a fresh Model Input committer is created. |
| MC-02 | Tool continuation through `src/loushang/agent/agent_loop.py::_run_loop` and `src/loushang/harness/session/agent_event_router.py::AgentEventRouter.handle` | `tool_continuation` | Every Tool result `message_end` append completes before the next sampling factory reads the transcript. |
| MC-03 | Agent continuation, queued input, and Product retry through `src/loushang/agent/agent.py::_run_continuation` and `src/loushang/harness/transcript/retry_runtime.py::AgentTranscriptRetryRuntime.continue_retry` | `continuation` or `retry` | Committed queued input and retry state precede a new logical invocation; it is not an AI provider attempt of the previous invocation. |
| MC-04 | Manual, automatic, overflow, and split-turn compaction through `src/loushang/harness/transcript/summarization.py::execute_transcript_compaction` | `compaction_history` or `compaction_turn_prefix` | Each actual summary request gets its own committed Model Input before transport; a split turn may create two invocations. |
| MC-05 | Branch summary through `src/loushang/harness/transcript/summarization.py::execute_branch_summary` | `branch_summary` | The selected branch-delta facts and prompt are committed before transport and remain reachable after navigation. |
| MC-06 | Side question through `src/loushang/harness/session/side_question.py::AgentSideQuestionProvider.ask` | `side_question` | The child remains Tool-disabled and output-transient, but its inherited context, boundary prompt, and question are committed as hidden Model Input facts in the parent transcript before transport. |
| MC-07 | Injected `stream_fn` through `src/loushang/agent/agent_loop.py::_collect_assistant_response` | caller-declared | A durable Harness profile accepts only the standard AI entrypoint or a conformance-declared adapter that honors the injected prepared-request committer. Otherwise it fails before transport. Standalone Agent use may still inject an unconstrained stream without claiming durable closure. |

The only direct AI stream/complete imports below the Product layer remain the
standalone Agent defaults and the shared transcript summarizer. The architecture
gate inventories those source modules so a new direct entrypoint cannot bypass
this table silently.

## Commit-Before-Sample Invariants

For every durable Harness-managed invocation:

```text
logical facts committed
  -> logical context frozen
  -> provider payload prepared and frozen
  -> Model Input facts committed
  -> cancellation/deadline rechecked
  -> provider transport may begin
```

The following are invalid and fail closed:

- sampling a Tool result whose transcript append has not completed;
- using a Model Input committer after another writer changed its captured leaf
  or revision;
- capturing graph/registration snapshots from a non-current Session;
- sending through an adapter that cannot run AI's prepared-request barrier; or
- continuing transport after required durable commit failure, cancellation, or
  an unknown commit outcome that cannot be reconciled.

The current awaited event path is retained as the Tool-result ordering seam:
`tests/coding/test_agent_session_retry.py::test_agent_session_retry_preserves_queued_messages_until_retry_continues`
characterizes continuation ordering, while PR8 adds an explicit
Tool-result-commit failure regression before changing production wiring.

## Compaction Lineage

PR8 adds a new compaction lineage payload version rather than rewriting old
records. The new payload references the Model Input snapshot IDs for every
summary request used to produce the checkpoint or branch summary. Split-turn
compaction retains both ordered snapshot IDs.

Existing v1 compaction and branch-summary records remain readable and
resumable. They are reported as `derivation-unverifiable`; the reader must not
invent request lineage, rewrite them during load, or reject an otherwise valid
legacy Session.

## Concurrency And Failure Policy

- A per-transcript Model Input commit uses the existing revision/leaf
  precondition. A concurrent writer causes a conflict and zero transport for
  that attempt.
- Side questions and summary calls that race a main-turn transcript mutation
  fail closed and may be retried from a new source revision.
- An unknown Store outcome is reconciled only through the existing operation
  identity and authoritative reload behavior. PR8 does not add a second WAL.
- Provider retries may append more than one prepared snapshot for one logical
  invocation. Product retries always start a new logical invocation.
- Shutdown cancels new sampling, waits for owned commit/transport tasks to
  quiesce, and only then disposes graph/registration state needed by those
  tasks.

## Compatibility

- standalone AI and Agent calls without a committer remain supported and keep
  importing no Harness modules;
- synthetic Product tests may opt out of durable closure explicitly, but a
  durable Product profile may not silently downgrade because a custom stream
  was supplied;
- current transcript and compaction wire versions remain readable;
- Product prompts, retry classification, model selection, compaction policy,
  and presentation remain Product-owned; and
- credentials, raw adapters, callbacks, and environment values never enter
  Model Input facts.

## Acceptance Matrix

PR8 is complete only when deterministic tests prove:

- all MC-01 through MC-07 paths either commit and reconstruct their Model Input
  or fail before transport;
- Tool-result append failure prevents the next model sample;
- provider retry attempts share invocation identity and each commit before its
  corresponding transport;
- Product retry, Tool continuation, and queued continuation use fresh logical
  invocation identities and source revisions;
- compaction-v2 lineage survives kill/restart, resume, fork, branch navigation,
  source deletion, and Extension unload;
- v1 compaction remains readable as derivation-unverifiable;
- concurrent revision conflict and unreconciled durable failure produce zero
  transport calls; and
- Session replacement/shutdown cannot expose a candidate graph early or leave
  an owned model-call task using disposed registrations.

Existing one-turn evidence remains
`tests/harness/transcript/test_model_input.py::test_main_agent_turn_rebuilds_after_restart_and_source_deletion`
and AI barrier evidence remains
`tests/ai/test_prepared_request.py::test_committer_failure_makes_zero_transport_calls`.

## Non-Goals

- no second Agent loop, provider retry runtime, transcript Store, or graph
  Projector;
- no generic distributed transaction or cross-Store rollback;
- no persistence of provider credentials or arbitrary runtime objects;
- no forced migration of v1 compaction records; and
- no PR9 explain/diff/DOT or multi-Product aggregation work.
