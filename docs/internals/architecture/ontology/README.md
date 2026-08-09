# Loushang Ontology Architecture

## Current State

The ontology subsystem has completed the semantic schema kernel, the Wave 2A
Fact/Provenance spine, and the greenfield authority reset in
[ARD-001](ARD-001-factstore-semantic-authority.md). It owns a versioned schema,
an append-only bitemporal FactStore, deterministic Fact-to-object projection,
read-only typed queries, and Memory/SQLite v2 FactStore implementations.

FactStore is the sole semantic authority. Object, property, and link graphs are
sealed, disposable projections. There is no public direct-object mutation
path, dynamic `Ontology` facade, callable RuleEngine, direct DataFusion, or
Ontology/HarnessWork Action bridge.

This is infrastructure, not a domain ontology and not a Palantir product clone.
Runtime coordination, schema-bound batches, CRUD command compilation,
standards bridges, source adapters, Actions/Decisions, generated SDKs,
distributed serving, and environmental packages remain separately accepted
work.

## Runtime Shape

```text
Source / future Command Adapter --FactBatch--> FactStore (Memory / SQLite v2)
                                                   |
                                 select(valid_at, recorded_at)
                                                   |
                                                   v
CompiledOntologySchema --------------------> Fact Materializer
                                                   |
                                                   v
                                  sealed Object / Property / Link view
                                                   |
                                                   v
                                       QueryResult / diagnostics

Ontology -------> Foundation JSON
```

New semantic state has exactly one write route. Future CRUD, derivation,
source, Agent, and Action surfaces must compile to Fact batches. Projection
state may be discarded and rebuilt; it cannot acquire independent business
truth.

SQLite is the correctness reference adapter. Physical format v2 is unchanged
by the authority reset and still rejects v1 without migration. SQL pushdown and
persistent materialization coordination remain deferred.

## Current Dependency Direction

```text
schema -------------------------------> Foundation JSON
facts.model --------------------------> Foundation JSON
facts.store --------------------------> facts.model
internal core projection builder ----> schema + Foundation JSON
facts.projection ---------------------> facts.store + schema + internal core
query --------------------------------> read-only core projection port
storage.sqlite -----------------------> facts + schema + internal core

ontology core -X-> Harness / HarnessWork / Work / Product
```

Product, source, Method, Work, or future Harness adapters may depend on the
public ontology contracts when semantic typing is needed. Ontology core does
not depend back on those execution or product runtimes.

## Source Ownership

- `schema/`: drafts, compiler, immutable snapshots, interface contracts, diff;
- `facts/model.py`: immutable fact envelope, assertion payloads, and FactBatch;
- `facts/store.py`: FactStore ports and Memory reference implementation;
- `facts/projection.py`: strict bitemporal materializer and sealed view result;
- `core/store_port.py`: read-only projection contract used by query;
- `core/store.py`: internal Memory projection builder, not semantic authority;
- `query/contracts.py`: immutable typed request/result contract;
- `query/engine.py`: backend-neutral evaluator over a read-only projection;
- `storage/sqlite.py`: public SQLiteFactStore plus an internal v2 compatibility
  backend pending the Phase 2 adapter split;
- `ARD-001-factstore-semantic-authority.md`: current authority decision;
- `wave2a-facts-provenance.md`: Fact/Provenance and SQLite v2 contract.

## Removed Greenfield Compatibility Surface

These paths and symbols intentionally do not exist:

- `ontology.core.ontology.Ontology`;
- `ontology.rules`;
- `ontology.fusion`;
- `ontology.integrations.harnesswork`;
- top-level `ObjectStore` and mutable Wave 1 Store ports;
- public `SQLiteObjectStore`.

They must not be restored as aliases or deprecation facades. Later capabilities
receive new contracts that preserve FactStore authority.

## Normative Reading Order

1. [ARD-001: FactStore Is The Sole Semantic Authority](ARD-001-factstore-semantic-authority.md)
2. [Wave 2A Facts And Provenance](wave2a-facts-provenance.md)
3. [SQLite Storage Compatibility](wave1-storage-compatibility.md)
4. [Schema Evolution V1](schema-evolution-v1.md)

The following documents are historical implementation evidence and are
superseded where they describe a public mutable object authority:

- [Wave 1 Completion Boundary](wave1-completion-boundary.md)
- [Semantic Kernel V1](semantic-kernel-v1.md)
- [Runtime Enforcement Matrix V1](runtime-enforcement-v1.md)
- [Managed Mutation Boundary V1](managed-mutation-boundary-v1.md)

The larger design and reference analysis remains in
[`drafts/loushang-ontology-operational-infrastructure.md`](drafts/loushang-ontology-operational-infrastructure.md).
It is directional material, not current implementation truth.
