# Loushang Ontology Architecture

## Current State

The ontology subsystem has completed Wave 1, the operational semantic kernel,
and Wave 2A, the minimal semantic Fact/Provenance spine. It now owns a versioned
structural schema, managed object/link mutations, an append-only bitemporal
FactStore, deterministic Fact-to-object projection, replaceable Memory/SQLite
implementations, explicit integrity validation, and typed backend-neutral
queries. SQLite format v2 persists semantic facts and idempotent batch identity
alongside the Wave 1 runtime and rejects v1 without migration.

This is infrastructure, not a domain ontology and not a Palantir product clone.
Standards bridges, source adapters/fusion, Actions/Decisions, generated SDKs,
distributed serving, and environmental packages remain later, separately
accepted waves.

## Runtime Shape

```text
Source / future Adapter --FactBatch--> FactStore (Memory / SQLite v2)
                                           |
                         select(valid_at, recorded_at)
                                           |
                                           v
CompiledOntologySchema ------------> Fact Projector
                                           |
                                           v
                                 Object / Property / Link
                                           |
                                           v
                             QueryResult / diagnostics

Direct Product mutation -----------> Wave 1 compatibility ObjectStore
Optional HarnessWork integration --> isolated integration adapter

Ontology -------> Foundation JSON
```

The storage journal remains an operational recovery mechanism and is not a
semantic Fact model. Facts are separate immutable records with source,
provenance, valid time, recorded time, and correction lineage. SQLite is the
correctness reference adapter; SQL pushdown is deliberately deferred.

## Source Ownership

- `schema/`: drafts, compiler, immutable snapshots, interface contracts, diff;
- `core/store_port.py`: replaceable read/write Store contract;
- `core/store.py`: Memory authority and reference mutation semantics;
- `facts/model.py`: immutable fact envelope, assertion payloads, and FactBatch;
- `facts/store.py`: FactStore port and Memory reference implementation;
- `facts/projection.py`: strict bitemporal Fact-to-object/link materializer;
- `storage/sqlite.py`: durable SQLite v2 ObjectStore and FactStore adapter;
- `wave2a-facts-provenance.md`: current Fact/Provenance and SQLite v2 contract;
- `wave1-storage-compatibility.md`: retained Wave 1 reopen/backup rules, updated
  for the current physical format;
- `core/projection.py`: mutation watermark and projection freshness values;
- `core/constraints.py`: explicit snapshot-integrity diagnostics;
- `query/contracts.py`: immutable typed request/result contract;
- `query/engine.py`: backend-neutral reference evaluator;
- `core/ontology.py`: dynamic compatibility facade and Store injection;
- `integrations/harnesswork.py`: the only optional HarnessWork dependency.

## Normative Reading Order

1. [Wave 2A Facts And Provenance](wave2a-facts-provenance.md)
2. [Wave 1 Completion Boundary](wave1-completion-boundary.md)
3. [SQLite Storage Compatibility](wave1-storage-compatibility.md)
4. [Semantic Kernel V1](semantic-kernel-v1.md)
5. [Runtime Enforcement Matrix V1](runtime-enforcement-v1.md)
6. [Managed Mutation Boundary V1](managed-mutation-boundary-v1.md)
7. [Schema Evolution V1](schema-evolution-v1.md)

The larger design and reference analysis remains in
[`drafts/loushang-ontology-operational-infrastructure.md`](drafts/loushang-ontology-operational-infrastructure.md).
It is directional material, not current implementation truth.
