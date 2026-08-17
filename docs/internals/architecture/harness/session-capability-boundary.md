# Session Capability Boundary

## Status

Implemented incrementally. Contract version 2 production-mounts the sealed
`interaction.side_question` facet and adopts the existing transcript lifecycle
trio as one indivisible binding. Process continuity retains its Process owner
until its stable-reference contract is implemented.

## Version 2 Decision

`harness.session` version 2 has four facets and two focused Consumers:

| Facet | Provider input | Consumer |
| --- | --- | --- |
| `interaction.side_question` | one Product-admitted, root-owned `LegacySideQuestionBinding` candidate | `SessionSideQuestionCapabilityConsumer` |
| `conversation.store` | the existing root-owned transcript lifecycle candidate | `SessionTranscriptCapabilityConsumer` |
| `agent.transcript_profile` | the same transcript lifecycle candidate | `SessionTranscriptCapabilityConsumer` |
| `context.compaction` | the same transcript lifecycle candidate and dynamic selected mechanism | `SessionTranscriptCapabilityConsumer` |

The Product construction root resolves the side-question factory and binds the
transcript Store/Profile/Compaction trio once, before AgentProduct graph
construction. The combined Session Provider constructs neither a second
Runtime Profile Binder nor another Store. It transfers both focused candidates
through these states:

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

The three transcript facets deliberately share one facet implementation and
one disposer because `AgentTranscriptProfileRuntime.bind_lifecycle()` binds
them as one unit. Model Input and compaction callers use a stable narrow port:
before Mount, synchronous compaction reads the root-owned candidate; after the
single Graph publication window, Model Input and compaction revalidate the
typed transcript Consumer lease on each use. The durable transcript header,
Runtime Profile snapshot, Store identity, UoW, and Model Input record schema
are unchanged and are not persisted as Graph facts.

The two transcript Runtime-binding fields used by this handoff are additive.
A generic Product that still returns the earlier Store/key/profile/binding/
disposer shape receives a stable `harness.transcript.legacy` selection snapshot
and its previously selected custom-or-default compaction capability. This keeps
the old AgentProduct path constructible without pretending that legacy Product
facts came from the standard Profile resolver.

Session shutdown first joins active compaction and side-question work. The
Provider then attempts auxiliary index publication before releasing the
transcript binding. Failed runtime disposers retain only the failed entries and
the graph-owned candidate, so Graph retirement can retry without repeating
successful cleanup.

## Deferred Work

- `continuity.provider_packs` is Process-scoped and is released by the Product
  runtime, not by an individual Session. A later Session Consumer may receive
  only a typed stable lease/reference from that process owner. The concrete
  ContinuityHub must not be inserted into the Session Bundle.

The accepted future `harness.session -> harness.resources/workspace` edges are
also deferred until real Session Consumers use those facets. Version 2 is
currently pulled into the graph by the direct
`harness.model_input -> harness.session` transcript requirement; it does not
fabricate either future Session dependency.

## Dependency And Import Rules

- Definition imports only neutral Capability contracts.
- Provider may import the focused legacy binding and side-question runtime
  contracts, but not Coding, Graph Runtime/Binder/Planner/Projector, Product
  services, or a service locator.
- Consumer holds only a requirement-scoped `CapabilityFacetSet`; it does not
  import the Provider or a graph manager.
- `AgentProductSession` remains the only production Graph/Binder/Projector
  owner and the only Provider-construction/Consumer-capture site.
- Version 2 is a direct dependency of `harness.model_input`. It does not
  fabricate dependencies on `harness.resources` or `harness.workspace`; those
  target edges become real only when a later Session Provider actually consumes
  their declared facets.

## Acceptance Evidence

- standard, Extension-selected, direct-construction, and absent Provider paths;
- graph construction failure, cancellation, pre-publication rollback, reuse
  rejection, disposal retry, and stale Consumer lease;
- active request cancellation and join before factory disposal;
- one graph bind and one Provider construction for one signature; and
- durable transcript resume remains independent of the auxiliary
  side-question selection;
- new/load/open/continue/in-memory/fork preserve the same transcript binding,
  header and Model Input reconstruction behavior; and
- index publication precedes transcript release, failed cleanup is retryable,
  and cached transcript Consumer leases become stale after retirement.
