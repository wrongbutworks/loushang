# Ontology Semantic Kernel v1

## Status

Accepted historical boundary for the first versioned semantic-kernel slice.
It is extended by the implemented
[Wave 1 Completion Boundary](wave1-completion-boundary.md), which adds the
previously deferred Store/SQLite/projection/query/interface contracts. The
non-goals below describe this initial slice, not the current subsystem state.

## Objective

Separate serializable ontology definitions from mutable runtime objects:

```text
OntologyPackageDraft
        -> OntologyCompiler
        -> CompiledOntologySchema | SchemaDiagnostics
        -> existing Memory ObjectStore
```

The existing `Ontology` class remains the compatibility facade. New schema
contracts live below it and do not depend on Query, Rules, Fusion, HarnessWork,
Agent, Product, or storage implementations.

## V1 Contracts

V1 defines:

- stable package ID, namespace, and schema version;
- symbolic `ValueType` values instead of Python classes in serialized schema;
- immutable property, object-type, and link-type definitions;
- immutable compiled schema snapshots;
- deterministic strict-JSON serialization and loading;
- diagnostics for duplicate names, invalid identifiers, unsupported value
  types, unknown link endpoints, and invalid cardinality;
- a compatibility mapping for the existing `Property(..., str/int/...)` API;
- an explicit schema freeze before the compatibility facade creates runtime
  objects.

The compiler is a pure boundary. It does not register global state, mutate an
ObjectStore, execute rules, open files, or perform I/O.

## Dependency Direction

```text
ontology schema definitions -> loushang.foundation.json
ontology compiler           -> schema definitions + foundation.json
ontology facade             -> compiler + existing Memory ObjectStore
ontology HarnessWork adapter -> public ontology contracts + HarnessWork
```

Ontology production code must use canonical Foundation contracts and must not
reintroduce the retired `loushang.protocol` or `loushang.observability`
namespaces.

## Compatibility Boundary

The current dynamic facade remains available:

```python
ontology.define_object_type("Person", properties=[Property("name", str)])
person = ontology.create("Person", name="Alice")
```

The facade translates supported Python scalar classes to symbolic value types.
Once runtime object creation starts, schema definitions are frozen. V1 does not
silently migrate an already-populated store to a new schema.

The compatibility facade is a draft adapter, not a second runtime registry.
Before compilation, its definitions are not registered in `ObjectStore`.
After successful compilation, the store atomically materializes its runtime
types from the compiled snapshot and binds that snapshot exactly once. A failed
compilation therefore leaves the runtime store untouched.

An already compiled schema can start a runtime without using the dynamic
definition facade:

```python
schema = OntologyCompiler().load_json(payload)
ontology = Ontology.from_schema(schema)
```

`Ontology.from_schema_json(payload)` is the equivalent convenience entry point.
Legacy Python property validators remain available only when the dynamic facade
is used. They are process-local compatibility extensions and are deliberately
not serialized, loaded, or treated as portable schema semantics.

The field-by-field enforcement boundary is normative for V1 and is recorded in
[Runtime Enforcement Matrix V1](runtime-enforcement-v1.md).
Managed runtime writes are further constrained by
[Ontology Managed Mutation Boundary V1](managed-mutation-boundary-v1.md).

Offline compatibility classification is defined separately in
[Ontology Schema Evolution V1](schema-evolution-v1.md); it does not authorize
runtime schema replacement or data migration.

## Non-Goals

V1 does not add:

- ActionType, DecisionType, authorization, approval, or MutationPlan;
- SQLite, Neo4j, distributed indexing, or a generic backend registry;
- OWL, SHACL, JSON-LD, MCP, or LLM authoring;
- new Rule, Fusion, QueryBuilder, or temporal-query semantics beyond routing
  existing writes through the managed mutation boundary;
- a project-management or environmental domain package.

Those capabilities require a stable compiled schema and separately accepted
contracts.

## Acceptance Gates

- the same draft produces byte-equivalent canonical JSON;
- compiled snapshots do not change when caller-owned draft inputs change;
- schema JSON round-trips to an equivalent compiled snapshot;
- invalid identifiers, duplicates, unknown link endpoints, invalid
  cardinality, and unsupported Python types fail with stable diagnostics;
- all existing Ontology tests remain green through the compatibility facade;
- managed object compatibility writes cannot bypass schema, indexes, ownership,
  or link-cardinality checks;
- no Ontology production module imports a legacy Foundation facade.
