# Loushang Ontology Architecture

## Current State

The ontology subsystem has completed the schema kernel, the Wave 2A
Fact/Provenance spine, the single-authority reset in
[ARD-001](ARD-001-factstore-semantic-authority.md), and the Phase 2 port,
projection, and adapter split in
[ARD-002](ARD-002-ports-immutable-projection-and-sqlite-v2.md). The
materialization-correctness and stable semantic identity slices of
[ARD-003](ARD-003-declared-state-authority-and-multi-source-materialization.md)
are also implemented.

It currently provides:

- versioned schema drafts, compilation, immutable snapshots, diagnostics, and
  schema diff, with package-local stable semantic IDs for object types,
  object properties, and link types;
- an append-only bitemporal FactStore with provenance and lineage;
- pure, deterministic Fact commit planning and atomic bitemporal
  `FactSelection`;
- immutable Fact-to-object/property/link materialization from a detached
  selection;
- immutable projection build coordinates plus explicit, pure
  `ProjectionFreshness` evaluation;
- a narrow ProjectionReadStore and atomic whole-snapshot ProjectionStore;
- backend-neutral typed queries over projection reads;
- independent Memory and SQLite FactStore/ProjectionStore adapters;
- SQLite v2 format detection, corruption checks, schema identity, restart, and
  backup.

In the current Fact-only runtime, FactStore is the only semantic-record input.
ARD-003 narrows that statement for the target architecture: mapped source input
may later materialize source-backed state without per-property Facts, while
FactStore remains authoritative for records inside its declared scope.
Projection replacement installs disposable infrastructure state; it is not
object CRUD. There is no dynamic `Ontology` facade, mutable ObjectStore,
callable RuleEngine, direct DataFusion, or Ontology/HarnessWork Action bridge.

This is infrastructure, not a domain ontology and not a Palantir product
clone. Runtime coordination, command compilation, source adapters, Actions,
Decisions, generated SDKs, standards bridges, SQL pushdown, and environmental
packages remain later work.

## Accepted Direction And Implementation Boundary

[ARD-003](ARD-003-declared-state-authority-and-multi-source-materialization.md)
defines how application-version source mappings and multiple systems of record
will enter materialization. It separates business-state ownership
(`StateAuthority`) from FactStore's semantic-record authority, adding immutable
mapped source inputs, and separating a projection's build cut from observed
freshness. It is tracked in
[#439](https://github.com/zhnt/loushang/issues/439).

Two ARD-003 foundation slices are implemented: materialization correctness
(atomic Fact selection, immutable build coordinates, explicit Fact freshness,
and snapshot-consistent SQLite reads) and stable semantic identity (schema v2
plus identity-based schema-diff v2). `StateAuthority`, mapped source input,
`MaterializationCut`, and multi-source `ValueOrigin` remain next steps. The
runtime shape below therefore remains Fact-only.

## Runtime Shape

```text
Source / future Command Adapter
             |
             | FactBatch
             v
      +---------------+       select_facts(valid_at, recorded_at)
      |   FactStore   |------------------------------------------+
      +---------------+                                          |
             ^                                                    v
             |                                             FactSelection
             |                                                    |
CompiledOntologySchema ----------------------------+              v
                                                   |   +---------------------+
                                                   +-->| Pure Materializer   |
                                                       +---------------------+
                                                               |
                                                               | immutable
                                                               v
                                                    ProjectionSnapshot
                                                               |
                                                atomic replace | read
                                                               v
                                                     ProjectionStore
                                                               |
                                                               v
                                                    QueryRequest/Result
```

A failed materialization or projection replacement cannot undo an accepted
Fact batch. A later Fact commit never mutates the installed snapshot's build
coordinates. Callers compare its `fact_watermark` with an explicitly observed
FactStore watermark through `evaluate_projection_freshness(...)`.

## Dependency Direction

```text
schema -------------------------------> Foundation JSON
facts.model --------------------------> Foundation JSON
facts.ports --------------------------> facts.model
facts.commit -------------------------> facts.model + facts.ports
projection.model ---------------------> schema + Foundation JSON
projection.ports ---------------------> projection.model
projection.materializer -------------> facts.ports + projection.model + schema
query --------------------------------> projection ports/models
storage.memory -----------------------> facts + projection ports/models
storage.sqlite -----------------------> facts + projection ports/models + schema

domain packages -X-> storage
query           -X-> storage
memory adapter  -X-> SQLite adapter
SQLite adapter  -X-> memory adapter
ontology        -X-> Harness / HarnessWork / Method / Product
```

Product or domain adapters may depend on public Ontology contracts when they
need semantic typing. Ontology does not depend back on an execution runtime or
product subsystem.

## Source Ownership

- `schema/`: drafts, stable semantic identity, compiler, immutable schemas,
  diagnostics, and diff;
- `facts/model.py`: immutable Fact envelope, typed assertions, provenance, and
  FactBatch;
- `facts/ports.py`: Fact read/write ports, stable commit values, and atomic
  `FactSelection`;
- `facts/commit.py`: pure commit planning, journal validation, lineage, and
  bitemporal selection;
- `projection/model.py`: immutable object, property, link, build state,
  freshness observation, and snapshot;
- `projection/ports.py`: projection reads and atomic replacement;
- `projection/materializer.py`: schema validation and deterministic snapshot
  construction;
- `query/`: immutable requests/results, fluent builder, and reference evaluator;
- `storage/memory.py`: independent reference Fact and Projection adapters;
- `storage/sqlite.py`: direct SQLite Fact and Projection adapters plus physical
  compatibility failures.

The complete package deliberately has no `ontology/core/` directory.

## SQLite v2

The only supported physical identity is `loushang.ontology.sqlite`, version 2,
with `storage_layout=phase2`. Any other storage version or layout is rejected;
there is no compatibility reader or migration path for development stores.

```text
ontology_metadata       ontology_schema
semantic_facts          fact_batches
projection_metadata     projection_objects
projection_properties   projection_links
```

`authority_objects`, `mutation_journal`, and `projection_unique_values` are
not part of the current layout.

## Removed Greenfield Surface

These paths and symbols intentionally do not exist:

- `ontology.core` and `ontology.core.ontology.Ontology`;
- `ontology.rules`;
- `ontology.fusion`;
- `ontology.integrations.harnesswork`;
- top-level `ObjectStore` and mutable object-store ports;
- public `SQLiteObjectStore`;
- `FactProjection` wrappers and runtime-sealed mutable views.

They must not return as compatibility aliases. Future CRUD, derivation,
Agent, Action, and Decision surfaces use their declared authority. Ontology-owned
commands remain Fact-backed; the later source-backed command contract is
deferred to an Action/write-back ARD.

## Normative Reading Order

1. [ARD-001: FactStore Is The Sole Semantic Authority](ARD-001-factstore-semantic-authority.md)
2. [ARD-002: Ports, Immutable Projections, And The Phase 2 SQLite v2 Layout](ARD-002-ports-immutable-projection-and-sqlite-v2.md)
3. [ARD-003: Declared State Authority And Multi-Source Materialization](ARD-003-declared-state-authority-and-multi-source-materialization.md)
4. [Wave 2A Facts And Provenance](wave2a-facts-provenance.md)
5. [Schema Evolution](schema-evolution.md)

The larger design and reference analysis remains in
[`drafts/loushang-ontology-operational-infrastructure.md`](drafts/loushang-ontology-operational-infrastructure.md).
It is directional material, not current implementation truth.
