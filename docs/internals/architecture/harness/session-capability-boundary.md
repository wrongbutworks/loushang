# Session Capability Boundary

## Status

Implemented incrementally. Contract version 1 production-mounts only the
sealed `interaction.side_question` facet. The accepted `harness.session`
Capability budget also includes the transcript lifecycle and process
continuity seams, but those mechanisms retain their focused owners until their
different scopes and handoff contracts are implemented.

## Version 1 Decision

`harness.session` version 1 has one facet and one focused Consumer:

| Facet | Provider input | Consumer |
| --- | --- | --- |
| `interaction.side_question` | one Product-admitted, root-owned `LegacySideQuestionBinding` candidate | `SessionSideQuestionCapabilityConsumer` |

The Product construction root resolves and binds the selected factory once.
The Session Provider does not construct a second Runtime Profile binding. It
transfers the same candidate through these states:

```text
root_owned -> graph_constructing -> graph_owned -> disposed
```

Validation or construction failure restores `root_owned`. Graph-wide or node
reuse never calls the Provider factory, so the rejected candidate remains
root-owned and is disposed by the construction root. After publication, only
the Graph Provider disposer may release it. A failed disposer retains the
same owner state so the existing Graph retirement retry can try again.

The selected side-question factory is bound to the live Product Session only
inside Provider construction. The binding callback is a narrow typed port; it
is not part of the Provider fingerprint, graph snapshot, diagnostics, or
runtime projection. The fingerprint contains only the canonical focused
Profile snapshot, Capability/provider versions, and redacted scope identity.

The Consumer revalidates its `CapabilityFacetSet` lease on every `ask`,
`cancel`, and ownership query. It never returns the raw coordinator or selected
Provider. Session shutdown cancels and joins an active request before Graph
retirement; Provider disposal repeats that operation idempotently before
releasing the Profile binding.

## Deferred Facets

The remaining accepted Session facets are not version-1 placeholders:

- `conversation.store`, `agent.transcript_profile`, and `context.compaction`
  share one `AgentTranscriptProfileRuntime` binding created before the
  AgentProduct Session Graph. They must move together through an explicit
  transcript-lifecycle ownership handoff; the Graph must not reconstruct or
  partially own that binding.
- `context.compaction` additionally requires its turn-refresh, active-task
  quiescence, and restart behavior to be explicit before the handoff.
- `continuity.provider_packs` is Process-scoped and is released by the Product
  runtime, not by an individual Session. A later Session Consumer may receive
  only a typed stable lease/reference from that process owner. The concrete
  ContinuityHub must not be inserted into the Session Bundle.

Adding those facets requires a new compatible contract version, updated
Provider fingerprints and Consumers, and its own lifecycle tests. It must not
silently change the meaning of the current Capability Profile fingerprint or
the persisted transcript Runtime Profile snapshot.

## Dependency And Import Rules

- Definition imports only neutral Capability contracts.
- Provider may import the focused legacy binding and side-question runtime
  contracts, but not Coding, Graph Runtime/Binder/Planner/Projector, Product
  services, or a service locator.
- Consumer holds only a requirement-scoped `CapabilityFacetSet`; it does not
  import the Provider or a graph manager.
- `AgentProductSession` remains the only production Graph/Binder/Projector
  owner and the only Provider-construction/Consumer-capture site.
- Version 1 is an independent Session root. It does not fabricate dependencies
  on `harness.resources` or `harness.workspace`; those target edges become real
  only when a later Session Provider actually consumes their declared facets.

## Acceptance Evidence

- standard, Extension-selected, direct-construction, and absent Provider paths;
- graph construction failure, cancellation, pre-publication rollback, reuse
  rejection, disposal retry, and stale Consumer lease;
- active request cancellation and join before factory disposal;
- one graph bind and one Provider construction for one signature; and
- durable transcript resume remains independent of the auxiliary
  side-question selection.
