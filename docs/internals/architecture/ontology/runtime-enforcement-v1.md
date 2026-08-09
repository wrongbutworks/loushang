# Ontology Runtime Enforcement Matrix V1

> Historical implementation evidence. [ARD-001](ARD-001-factstore-semantic-authority.md)
> removes the public direct-object mutation paths described below.

## Status

Accepted description of what the Semantic Kernel V1 compiler and in-memory
runtime actually enforce. This matrix is a capability boundary, not a roadmap
promise.

The standard mutation paths in this document are `Ontology.create`,
`Ontology.set_property`, `Ontology.link`, and `Ontology.unlink`, which delegate
to `ObjectStore`. An `OntologyObject` created by a store remains bound to that
store: its compatibility `set`, `link`, and `unlink` methods route through the
same managed mutation boundary. A standalone `OntologyObject` retains local,
schema-free mutation behavior.

The detailed ownership and failure contract is defined in
[Managed Mutation Boundary V1](managed-mutation-boundary-v1.md).

## Matrix

| Contract | Compiler | Standard runtime | V1 status |
| --- | --- | --- | --- |
| package ID, schema version, identifiers | validates syntax and duplicates | bound snapshot is read-only | enforced |
| property `ValueType` | rejects unknown symbolic types | validates values on object creation and property update | enforced |
| property `required` and default | default must be strict JSON | resolves defaults and required fields on create | enforced on create |
| object `abstract` | serialized in compiled schema | rejects direct instantiation | enforced |
| `parent_types` | rejects unknown parents and cycles | resolves inherited defaults, validation, and indexes | enforced |
| link endpoints | rejects unknown object types | validates source and target object types | enforced |
| link cardinality | validates symbolic cardinality | checks active source and target links before linking | enforced on link |
| property `indexed` | serialized | maintained on create/update/delete and deterministic rebuild, including inherited properties | enforced serving projection |
| property `unique` | serialized | enforced on create/update by stable declaring-property identity | enforced |
| interface contract | validates names and structural conformance through inheritance | materialized as object-type metadata; adds no methods or storage | enforced at compile |
| link `required` | serialized | reported by explicit whole-snapshot integrity validation; single-object creation remains legal | explicit validation |
| link reference integrity | validates endpoint declarations | rejects deletion with active links and reports missing references during integrity validation | enforced |
| link properties | not schema-typed in Wave 1 | copied and validated against strict Foundation JSON | enforced |
| mutation watermark | not applicable | every accepted mutation advances authority and synchronous projection once | enforced |
| Python property validator | not serialized | dynamic-facade local overlay on create/update | local compatibility only |
| `DerivedProperty.formula` | not represented in portable V1 schema | not executed | deferred |
| `TemporalProperty.retention_days` | not represented in portable V1 schema | no retention policy | deferred |
| undeclared object properties | not applicable | accepted by the compatibility object model | open-world compatibility |

## Value Semantics

V1 runtime values use these exact rules:

- `string`: Python `str`;
- `integer`: Python `int`, excluding `bool`;
- `number`: finite Python `int` or `float`, excluding `bool`;
- `boolean`: Python `bool`;
- `datetime`: Python `datetime`;
- `json`: the strict `loushang.foundation.json` algebra.

Value checks apply to object creation and managed property updates. A failed
managed update does not append property history or alter the property index.
Direct `OntologyObject.set` has this behavior for store-managed objects because
it routes to the owning store; only standalone objects remain unvalidated.

## Deliberate Deferrals

Required links are not used as a hidden single-object creation gate; callers
run explicit snapshot validation until a later multi-object MutationPlan owns
transaction-level completeness. Formula/expression execution and temporal
retention remain deferred. General constraints are not interpreted through
arbitrary Python or `eval`.
