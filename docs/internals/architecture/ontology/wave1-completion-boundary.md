# Ontology Wave 1 Completion Boundary

## Status

Accepted implementation boundary for completing the Semantic Kernel wave.
This boundary closes the storage, projection, query, uniqueness, interface,
and reference-integrity gaps left by Semantic Kernel V1. It does not enter the
Facts/Provenance, Action/Decision, standards, or domain waves.

Implementation status: complete. The contract is covered by the shared
Memory/SQLite conformance suite, restart and rollback tests, interface compiler
tests, typed-query tests, architecture import gates, Ruff, and mypy.
The physical SQLite format and public adapter lifecycle are frozen separately by
the [Wave 1 SQLite Storage Compatibility](wave1-storage-compatibility.md)
contract.

## Runtime Spine

```text
CompiledOntologySchema
        -> OntologyStore
             -> committed mutation sequence
             -> object/property/link authority
             -> synchronous serving projection
        -> typed QueryRequest
             -> QueryResult + ProjectionState
```

`ObjectStore` remains the in-memory reference implementation and compatibility
name. `SQLiteObjectStore` implements the same contract with the Python standard
library. `Ontology` accepts an injected store; it does not select a backend
through a registry or configuration service.

The committed mutation sequence is an operational storage journal, not the
Wave 2 semantic Fact model. It does not classify asserted, derived, or inferred
facts and carries no evidence or confidence semantics.

## Commit And Projection Contract

Each successful object, property, link, unlink, or delete mutation receives one
strictly increasing source watermark. The primary object projection, current
property projection, link adjacency projection, and unique-value projection
reach that watermark in the same commit.

`ProjectionState` reports schema version, projection version, source watermark,
projected watermark, build time, and freshness. `rebuild_projections()` derives
all serving projections deterministically from authoritative object/property/
link history without adding a source mutation.

SQLite commits authority rows, the mutation journal, projections, unique keys,
and watermarks in one database transaction. Expected validation, uniqueness,
cardinality, ownership, reference, and duplicate-ID failures happen before the
transaction and do not advance either watermark.

## Constraint Semantics

- `unique=True` is enforced by the stable declaring-property identity. An
  inherited property retains its declaring identity; a child override defines
  a new identity.
- deleting an object with an active incoming or outgoing link is rejected.
  Callers unlink explicitly before delete; Wave 1 has no cascade policy.
- required links remain a transaction-level declaration. They are checked by
  explicit validation and are not silently enforced during single-object
  creation, which cannot yet supply a multi-object mutation plan.
- link properties must belong to the strict Foundation JSON algebra.
- general expression constraints remain outside Wave 1; type, required,
  unique, endpoint, cardinality, interface, and reference constraints are the
  complete accepted set.

## Interface Semantics

An interface is a named structural property contract in a compiled package.
An object type explicitly declares the interfaces it implements. Compilation
requires every interface property to resolve through the object's own or
inherited properties with the same value type and compatible requiredness.
Interfaces do not add runtime storage, inheritance, methods, Actions, or
authorization.

## Query Contract

`QueryRequest` is an immutable ordered sequence of typed start, traversal,
filter, sort, offset, limit, and as-of steps. `QueryResult` returns stable object
IDs plus schema version, projection state, and diagnostics. A schema-version
mismatch is a result diagnostic rather than an implicit query against another
schema.

The compatibility `QueryBuilder` compiles to this request. Memory and SQLite
may initially share the reference evaluator; SQL pushdown and cost-based query
planning are Platform Scale work.

## Acceptance Gates

- one conformance suite passes for Memory and SQLite;
- SQLite close/reopen preserves schema, IDs, property/link history, current
  values, indexes, mutation watermarks, and query results;
- SQLite detects incompatible or malformed storage before loading state, never
  silently upgrades it, and produces a consistently reopenable online backup;
- rejected mutations leave state and watermarks unchanged;
- unique, link-cardinality, ownership, and delete-reference constraints are
  enforced before commit;
- deterministic rebuild restores equivalent primary/property/link projections;
- typed query results expose schema version and fresh projection state;
- the dynamic `Ontology` facade works with either injected store;
- Foundation-only and HarnessWork integration dependency boundaries remain
  intact.

## Implementation Map

| Contract | Canonical owner |
| --- | --- |
| Store port | `ontology.core.store_port` |
| Memory reference store | `ontology.core.store.ObjectStore` |
| SQLite reference adapter | `ontology.storage.sqlite.SQLiteObjectStore` |
| mutation/projection state | `ontology.core.projection` |
| explicit integrity diagnostics | `ontology.core.constraints` |
| typed query values | `ontology.query.contracts` |
| reference query evaluator | `ontology.query.engine` |
| interface schema contract | `ontology.schema.definitions` and compiler |

## Non-Goals

- semantic Facts, bitemporal provenance, evidence, confidence, or corrections;
- schema migration, hot upgrade, multi-writer optimistic concurrency, or a
  backend registry;
- SQL query optimization, full-text search, graph databases, or distributed
  projections;
- ActionType, MutationPlan, authorization, approval, DecisionType, or Outcome;
- RDF, OWL, JSON-LD, SHACL, MCP, SDK generation, or domain packages.
