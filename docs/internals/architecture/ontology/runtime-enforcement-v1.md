# Ontology Runtime Enforcement Matrix V1

## Status

Accepted description of what the Semantic Kernel V1 compiler and in-memory
runtime actually enforce. This matrix is a capability boundary, not a roadmap
promise.

The standard mutation paths in this document are `Ontology.create` and
`Ontology.link`, which delegate to `ObjectStore`. Direct calls to
`OntologyObject.set` or `OntologyObject.link` remain low-level compatibility
operations; they are not schema, policy, indexing, or authorization boundaries.

## Matrix

| Contract | Compiler | Standard runtime | V1 status |
| --- | --- | --- | --- |
| package ID, schema version, identifiers | validates syntax and duplicates | bound snapshot is read-only | enforced |
| property `ValueType` | rejects unknown symbolic types | validates values on object creation | enforced on create |
| property `required` and default | default must be strict JSON | resolves defaults and required fields on create | enforced on create |
| object `abstract` | serialized in compiled schema | rejects direct instantiation | enforced |
| `parent_types` | rejects unknown parents and cycles | resolves inherited defaults, validation, and indexes | enforced |
| link endpoints | rejects unknown object types | validates source and target object types | enforced |
| link cardinality | validates symbolic cardinality | checks active source and target links before linking | enforced on link |
| property `indexed` | serialized | maintained on create/delete, including inherited properties | partial operational support |
| property `unique` | serialized | not enforced across mutation paths | metadata only |
| link `required` | serialized | not enforced without a transaction boundary | metadata only |
| Python property validator | not serialized | dynamic-facade local overlay on create | local compatibility only |
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

Value checks apply to object creation. Direct `OntologyObject.set` remains an
unvalidated low-level operation until a separately accepted mutation boundary
replaces it.

## Deliberate Deferrals

V1 does not partially implement uniqueness, required links, formula execution,
or retention. Those semantics need controlled mutation or transaction
boundaries. Adding them to only one write path would create a misleading
guarantee, so they remain explicitly non-enforced.
