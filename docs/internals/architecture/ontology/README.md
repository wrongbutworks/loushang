# Loushang Ontology Architecture

## Current State

The ontology subsystem has completed Wave 1, the operational semantic kernel.
It now owns a versioned structural schema, managed object/link mutations,
replaceable Memory/SQLite stores, a committed operational mutation sequence,
synchronous rebuildable projections, explicit integrity validation, and typed
backend-neutral queries. Its SQLite reference format is now explicitly
versioned, validated before state loading, protected by exact schema-snapshot
checks, and covered by a consistent online-backup contract.

Wave 1 is infrastructure, not a domain ontology and not a Palantir product
clone. Facts/provenance, standards bridges, Actions/Decisions, generated SDKs,
distributed serving, and environmental packages remain later, separately
accepted waves.

## Runtime Shape

```text
Product / Domain Adapter
           |
           | schema, mutations, QueryRequest
           v
     +-------------+       +----------------------+
     |             |------>| Memory or SQLite     |
     |  Ontology   |<------| authority/projection |
     |             |       +----------------------+
     +-------------+
           |
           +-------> QueryResult / diagnostics / integrity violations
           |
           +-------> optional HarnessWork integration adapter

Ontology -------> Foundation JSON
```

The storage journal is an operational recovery mechanism, not a semantic Fact
model. SQLite is the correctness reference adapter and shares the in-process
query evaluator with Memory; SQL pushdown is deliberately deferred.

## Source Ownership

- `schema/`: drafts, compiler, immutable snapshots, interface contracts, diff;
- `core/store_port.py`: replaceable read/write Store contract;
- `core/store.py`: Memory authority and reference mutation semantics;
- `storage/sqlite.py`: durable transactional reference adapter;
- `wave1-storage-compatibility.md`: SQLite format, reopen, backup, and public API
  compatibility contract;
- `core/projection.py`: mutation watermark and projection freshness values;
- `core/constraints.py`: explicit snapshot-integrity diagnostics;
- `query/contracts.py`: immutable typed request/result contract;
- `query/engine.py`: backend-neutral reference evaluator;
- `core/ontology.py`: dynamic compatibility facade and Store injection;
- `integrations/harnesswork.py`: the only optional HarnessWork dependency.

## Normative Reading Order

1. [Wave 1 Completion Boundary](wave1-completion-boundary.md)
2. [Wave 1 SQLite Storage Compatibility](wave1-storage-compatibility.md)
3. [Semantic Kernel V1](semantic-kernel-v1.md)
4. [Runtime Enforcement Matrix V1](runtime-enforcement-v1.md)
5. [Managed Mutation Boundary V1](managed-mutation-boundary-v1.md)
6. [Schema Evolution V1](schema-evolution-v1.md)

The larger design and reference analysis remains in
[`drafts/loushang-ontology-operational-infrastructure.md`](drafts/loushang-ontology-operational-infrastructure.md).
It is directional material, not current implementation truth.
