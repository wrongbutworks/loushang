# Loushang Ontology Architecture

## Current State

The ontology subsystem has completed the schema kernel, the Wave 2A
Fact/Provenance spine, the single-authority reset in
[ARD-001](ARD-001-factstore-semantic-authority.md), and the Phase 2 port,
projection, and adapter split in
[ARD-002](ARD-002-ports-immutable-projection-and-sqlite-v2.md). The
materialization-correctness, stable semantic identity, and declared
StateAuthority slices of
[ARD-003](ARD-003-declared-state-authority-and-multi-source-materialization.md)
are implemented. Its Memory-only mapped-source materialization and complete
operational-origin slices are also implemented.

It currently provides:

- versioned schema drafts, compilation, immutable snapshots, diagnostics, and
  schema diff, with package-local stable semantic IDs for object types,
  object properties, and link types, plus an explicit StateAuthority for each
  operational definition;
- an append-only bitemporal FactStore with provenance and lineage;
- pure, deterministic Fact commit planning and atomic bitemporal
  `FactSelection`;
- immutable source bindings and mapped source snapshots for source-backed
  object existence, properties, and links;
- deterministic source-plus-Fact object/property/link materialization: object
  existence and links expose `FactOrigin` or `SourceOrigin`, while properties
  may additionally expose `SchemaDefaultOrigin`;
- immutable `MaterializationCut` build coordinates plus explicit, pure Fact and
  source-head `ProjectionFreshness` evaluation;
- a narrow ProjectionReadStore and atomic whole-snapshot ProjectionStore;
- backend-neutral typed queries over projection reads;
- independent Memory and SQLite FactStore/ProjectionStore adapters;
- SQLite v2 format detection, corruption checks, schema identity, restart, and
  backup.

The Memory materialization path accepts both a detached `FactSelection` and
immutable mapped source snapshots. Ordinary source-backed values therefore do
not require per-property Facts, while FactStore remains authoritative for
records inside its declared scope. The SQLite v2 projection layout remains the
accepted Fact-only physical subset and explicitly rejects source cuts rather
than dropping source lineage.
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

The implemented ARD-003 foundation includes materialization correctness
(atomic Fact selection, immutable build coordinates, explicit Fact freshness,
and snapshot-consistent SQLite reads), stable semantic identity, and declared
state ownership (schema v3 plus identity/authority-aware schema-diff v3), plus
the Memory-only source composition and origin-contract slices. They add
concrete source bindings, full mapped object/property/link snapshots,
`MaterializationCut`, complete operational origins, explicit authority failure
contracts, and source-head freshness. Change sets, logic bindings, derived
computation origins, write routing, and a later SQLite physical layout remain
deferred.

## Proposed Target Designs

[Domain Ontology Ecosystem And Multi-Application Deployment](key-designs/domain-ontology-ecosystem-and-deployment.md)
proposes how the domain-neutral Ontology substrate can support independently
delivered domain packages, mature-ontology alignments, standards knowledge,
vendor adapters, warehouses, and one bureau deployment serving several
applications. Environmental information systems are its first validation
scenario; the design explicitly forbids an environmental package or vendor
adapter dependency in `loushang.ontology`.

This proposal is not Current implementation truth and is not part of the
accepted ARD reading order until reviewed and accepted.

## Runtime Shape

```text
Product source adapter --> SourceBinding + MappedSourceInput ---+
                                                               |
Source / Command Adapter --> FactStore --> FactSelection -------+
                                                               |
CompiledOntologySchema -----------------------------------------+
                                                               v
                                                    +-------------------+
                                                    | Pure Materializer |
                                                    +-------------------+
                                                               |
                                                               v
                                       ProjectionSnapshot + MaterializationCut
                                                               |
                                                atomic replace | read
                                                               v
                                                     ProjectionStore
                                                               |
                                                               v
                                                    QueryRequest/Result
```

A failed materialization or projection replacement cannot undo an accepted
Fact batch. A later Fact commit or source revision never mutates the installed
snapshot's build coordinates. Callers compare its cut with explicitly observed
Fact and source heads through `evaluate_projection_freshness(...)`.

## Dependency Direction

```text
schema -------------------------------> Foundation JSON
facts.model --------------------------> Foundation JSON
facts.ports --------------------------> facts.model
facts.commit -------------------------> facts.model + facts.ports
source.model -------------------------> Foundation JSON
projection.model ---------------------> schema + Foundation JSON
projection.ports ---------------------> projection.model
projection.materializer -------------> facts.ports + source
                                       + projection.model + schema
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

- `schema/`: drafts, stable semantic identity, StateAuthority declarations,
  compiler, immutable schemas, diagnostics, and diff;
- `facts/model.py`: immutable Fact envelope, typed assertions, provenance, and
  FactBatch;
- `facts/ports.py`: Fact read/write ports, stable commit values, and atomic
  `FactSelection`;
- `facts/commit.py`: pure commit planning, journal validation, lineage, and
  bitemporal selection;
- `source/`: immutable source authority bindings, mapped object/property/link
  snapshots, and source revision coordinates; no concrete connector;
- `projection/model.py`: immutable object, property, link, build state,
  value origins, materialization cut, freshness observation, and snapshot;
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
not part of the current layout. SQLite v2 reconstructs Fact-backed object and
link origins from the exact selected Fact IDs. It has no source revision-vector
or `SourceOrigin` columns, so `SQLiteProjectionStore` rejects source-backed
snapshots instead of persisting an incomplete representation.

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
