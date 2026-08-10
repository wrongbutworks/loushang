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
operational-origin slices are also implemented. The identity and
reproducibility closure in
[ARD-004](ARD-004-schema-identity-semantic-references-and-source-input-cuts.md)
is implemented. [ARD-005](ARD-005-source-aware-sqlite-v3.md),
[ARD-006](ARD-006-product-hosted-source-adapter-contract.md), and
[ARD-007](ARD-007-fact-schema-revalidation-receipts.md) now close durable
source-aware projection, the Product-hosted adapter boundary, and exact
Fact-selection reuse across schema versions.

It currently provides:

- versioned schema drafts, compilation, immutable snapshots, diagnostics, and
  schema diff, with package-local stable semantic IDs for object types,
  object properties, and link types, plus an explicit StateAuthority for each
  operational definition;
- an append-only bitemporal FactStore with provenance and lineage, where Fact
  v2 records bind a complete `SchemaIdentity` and durable assertions use stable
  semantic IDs rather than renameable API names;
- pure, deterministic Fact commit planning and atomic bitemporal
  `FactSelection`;
- immutable, schema-bound source bindings and mapped source snapshots for
  source-backed object existence, properties, and links, with explicit
  complete/partial/unknown coverage;
- deterministic source-adapter manifests that distinguish vendor application
  schema versions from target Ontology schema identity, plus detached output
  conformance checks;
- one Product-side fixed SQLite ERP fixture under `tests/integration/ontology/`
  proving source read, conformance, mixed materialization, durable restart,
  typed query, and source-head freshness without adding a production connector;
- deterministic source-plus-Fact object/property/link materialization, including
  property bindings independent from object-existence bindings: object existence
  and links expose `FactOrigin` or `SourceOrigin`, while ontology-owned
  properties may additionally expose `SchemaDefaultOrigin`;
- explicit rejection of mapped properties or links whose `valid_from` is later
  than the selected materialization `valid_at`;
- immutable `MaterializationCut` build coordinates containing deterministic
  mapped-payload digests plus explicit, pure Fact and source-head
  `ProjectionFreshness` evaluation;
- a narrow ProjectionReadStore and atomic whole-snapshot ProjectionStore,
  including synchronized replacement in the Memory reference adapter;
- backend-neutral typed queries over projection reads, guarded by complete
  `SchemaIdentity` rather than a version string alone;
- independent Memory and SQLite FactStore/ProjectionStore adapters;
- SQLite v3 source-aware cut/origin persistence, corruption checks, schema
  identity, restart, and backup;
- content-addressed Fact schema-revalidation receipts that authorize an exact
  old-schema Fact selection for one target schema without rewriting Facts.

The materialization path accepts both a detached `FactSelection` and
immutable mapped source snapshots. Ordinary source-backed values therefore do
not require per-property Facts, while FactStore remains authoritative for
records inside its declared scope. Memory and SQLite now preserve the same
source cuts and origin kinds. Source adapter implementations remain hosted and
executed by Product; Ontology serializes manifests and validates detached
outputs but contains no connector runtime.
Projection replacement installs disposable infrastructure state; it is not
object CRUD. There is no dynamic `Ontology` facade, mutable ObjectStore,
callable RuleEngine, direct DataFusion, or Ontology/HarnessWork Action bridge.

This is infrastructure, not a domain ontology and not a Palantir product
clone. Runtime coordination, concrete vendor adapters, command compilation,
Actions, Decisions, generated SDKs, standards bridges, SQL pushdown, and
environmental packages remain later work.

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
contracts, and source-head freshness.

[ARD-004](ARD-004-schema-identity-semantic-references-and-source-input-cuts.md)
closes the first runtime identity boundary: schema owns the single-package
`SchemaIdentity`; Facts and source bindings target it explicitly; Fact
assertions use stable semantic IDs; and a selected source cut includes coverage
and the exact mapped-payload digest while freshness continues to compare cheap
observable heads. Whole-snapshot materialization accepts only complete source
coverage.

ARD-005 replaces the undeployed SQLite v2 physical layout with one v3 format
that round-trips exact source cuts, `FactOrigin`, `SourceOrigin`, and
`SchemaDefaultOrigin`. ARD-006 defines a serializable adapter manifest,
structural Product-hosted protocol, and public output conformance boundary;
Ontology still does not run vendor code. ARD-007 permits an exact old-schema
Fact selection to be validated for a target schema through a content-addressed
receipt recorded in the materialization cut. Change sets, logic bindings,
derived computation origins, write routing, multi-package profiles, full Fact
journal migration, and deployment switching remain deferred.

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
Product-hosted adapter --> Manifest + Binding + MappedInput ----+
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
schema.identity ----------------------> Foundation JSON
schema compiler/diff -----------------> schema.identity + Foundation JSON
facts.model --------------------------> schema.identity + Foundation JSON
facts.ports --------------------------> facts.model
facts.commit -------------------------> facts.model + facts.ports
source.model -------------------------> schema.identity + Foundation JSON
source.adapter -----------------------> source.model + schema.identity
projection.model ---------------------> schema + Foundation JSON
projection.ports ---------------------> projection.model
projection.materializer -------------> facts.ports + source
                                       + projection.model + schema
projection.revalidation -------------> facts + schema + materializer
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
- `source/`: immutable schema-bound source authority bindings, mapped
  object/property/link snapshots, exact content-digested cuts, declared
  coverage, observable source revision coordinates, adapter manifests, and
  detached conformance checks; no concrete connector;
- `projection/model.py`: immutable object, property, link, build state,
  value origins, materialization cut, freshness observation, and snapshot;
- `projection/ports.py`: projection reads and atomic replacement;
- `projection/materializer.py`: schema validation and deterministic snapshot
  construction;
- `projection/revalidation*.py`: immutable schema-revalidation receipts and
  pure validation of an exact Fact selection against a target schema;
- `query/`: immutable requests/results, fluent builder, and reference evaluator;
- `storage/memory.py`: independent reference Fact and Projection adapters;
- `storage/sqlite.py`: direct SQLite Fact and Projection adapters plus physical
  compatibility failures.

The complete package deliberately has no `ontology/core/` directory.

## SQLite v3

The only supported physical identity is `loushang.ontology.sqlite`, version 3,
with `storage_layout=source-aware-projection`. Any other storage version or
layout is rejected; there is no v2 compatibility reader or migration path for
development stores.

```text
ontology_metadata       ontology_schema
semantic_facts          fact_batches
projection_metadata     projection_source_inputs
projection_objects
projection_properties   projection_links
```

`authority_objects`, `mutation_journal`, and `projection_unique_values` are
not part of the current layout. Every projected object, property, and link
stores a constrained origin kind plus strict kind-specific JSON. Startup
reconstructs the public snapshot and rejects missing cuts, malformed origins,
or origin/cut mismatches.

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
4. [ARD-004: Schema Identity, Semantic References, And Source Input Cuts](ARD-004-schema-identity-semantic-references-and-source-input-cuts.md)
5. [ARD-005: Source-Aware SQLite v3](ARD-005-source-aware-sqlite-v3.md)
6. [ARD-006: Product-Hosted Source Adapter Contract](ARD-006-product-hosted-source-adapter-contract.md)
7. [ARD-007: Fact Schema Revalidation Receipts](ARD-007-fact-schema-revalidation-receipts.md)
8. [Wave 2A Facts And Provenance](wave2a-facts-provenance.md)
9. [Schema Evolution](schema-evolution.md)

The larger design and reference analysis remains in
[`drafts/loushang-ontology-operational-infrastructure.md`](drafts/loushang-ontology-operational-infrastructure.md).
It is directional material, not current implementation truth.
