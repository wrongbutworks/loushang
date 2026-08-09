# ARD-001: FactStore Is The Sole Semantic Authority

Status: Accepted, 2026-08-09.

Tracking: [#437](https://github.com/zhnt/loushang/issues/437).

## Context

Wave 1 introduced a mutable object authority and an operational mutation
journal. Wave 2A later introduced the semantic Fact/Provenance spine. Keeping
both public write paths would force every caller to decide whether a business
change belongs in an object mutation or a Fact and would allow state without
source, evidence, bitemporal meaning, or correction lineage.

There are no production consumers of `loushang.ontology` and no legacy
ontology deployment to preserve. This decision therefore chooses one semantic
authority before source adapters, generated APIs, Actions, or domain packages
make the split permanent.

## Decision

The append-only `FactStore` is the only semantic state authority.

```text
Published Schema
       |
       v
FactBatch ---> FactStore ---> facts_as_of(valid_at, recorded_at)
                                  |
                                  v
                             Materializer
                                  |
                                  v
                    read-only Object/Property/Link view
                                  |
                                  v
                          typed QueryResult
```

The following rules are normative:

1. New asserted, derived, inferred, Agent-produced, or future Action-produced
   semantic state enters through `FactBatch -> FactStore`.
2. Object, property, link, index, cache, and search state is a disposable
   projection. It must be rebuildable from a published schema, the FactStore,
   and explicit valid/recorded times.
3. A completed Fact projection is read-only. Mutation attempts fail and tell
   the caller to append facts and rebuild.
4. The public package does not expose `Ontology`, `ObjectStore`, mutable
   `OntologyStore`, operational mutation ports, callable rules, direct fusion,
   or an ontology-named HarnessWork executor.
5. Future CRUD and Action APIs are command translators. Successful commands
   produce deterministic, idempotent Fact batches; they do not create another
   object authority.
6. Projection failure never rewrites or discards accepted facts. Projection
   freshness and failure reporting belong to the later materialization
   coordinator.
7. Raw external records that have not passed semantic mapping are not Facts.
   Source staging and mapping remain outside the authority boundary.

## Public And Internal Boundaries

The current public semantic surface is:

- versioned schema definitions, compiler, snapshots, and evolution values;
- Fact/Provenance models, FactStore ports, MemoryFactStore, and Fact projection;
- read-only typed query contracts;
- `SQLiteFactStore`, which exposes only FactStore, schema binding, backup, and
  lifecycle operations.

`core.store.ObjectStore` and the combined SQLite object backend remain internal
projection/storage builders until Phase 2 splits the ports and adapters. Their
presence does not authorize application imports or direct business writes.
Architecture gates protect the public boundary and the returned Fact
projection is sealed at runtime.

SQLite physical format v2 remains unchanged in this phase. Its historical
Wave 1 object, journal, and projection tables remain readable internally so
the format is not silently rewritten. There is still no v1 reader or migration
path.

## Removed Alternatives

The following greenfield compatibility surfaces are removed rather than
deprecated:

- the dynamic `Ontology` facade;
- `Rule` / `RuleEngine` Python-callable mutation rules;
- `FieldMapping` / `SourceMapping` / `DataFusion` direct object ingestion;
- the premature `ontology.integrations.harnesswork` Action bridge;
- top-level mutable ObjectStore and Wave 1 operational-journal ports;
- the public `SQLiteObjectStore` name.

No shim, alias, warning period, or legacy namespace is retained.

## Consequences

Benefits:

- one semantic write protocol and one provenance model;
- deterministic replay and audit are mandatory rather than optional;
- query and future SDK surfaces cannot bypass semantic lineage;
- rules, source adapters, Actions, and Decisions can share FactBatch commit
  semantics without sharing execution runtimes.

Costs:

- the current internal projection builder still contains Wave 1 mutation
  mechanics until Phase 2 separates ports/adapters;
- there is temporarily no convenience CRUD facade;
- there is temporarily no ontology-to-HarnessWork execution adapter;
- callers must construct facts explicitly until the command compiler exists.

These costs are intentional. Reintroducing convenience APIs before they
compile to the sole authority would recreate the ambiguity this decision
removes.

## Phase Boundary

This phase does not implement:

- the runtime/materialization coordinator or persistent projection refresh;
- schema-bound FactBatch changes;
- CRUD command compilation;
- safe derivation, source adapters, standards, Action, or Decision contracts;
- the Phase 2 Memory/SQLite port and adapter split.

Those capabilities must preserve this decision rather than add a second write
authority.
