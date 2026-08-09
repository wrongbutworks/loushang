# Ontology Schema Evolution V1

## Status

Accepted contract for offline comparison of two compiled Semantic Kernel V1
schemas. It describes compatibility; it does not mutate runtime state or data.

## Identity and Lineage

- `package_id` identifies one schema lineage. Schemas with different package
  IDs cannot be compared.
- `namespace` belongs to that lineage; changing it is a breaking change.
- object-type, property, and link-type `name` values are stable API keys.
- rename inference is deliberately absent. A renamed key appears as removal plus
  addition.
- schema versions are reported in the diff but V1 does not enforce SemVer or
  require versions to increase.

This avoids heuristic rename detection and avoids introducing UUID identities
before a concrete need exists.

## Public Contract

```python
from loushang.ontology.schema import compare_schemas

old = compiler.load_json(old_payload)
new = compiler.load_json(new_payload)
diff = compare_schemas(old, new)
```

The pure comparison returns an immutable `SchemaDiff` containing immutable,
path-addressed `SchemaChange` records. Its JSON format identifier is
`loushang.ontology.schema-diff/v1`. Change ordering is stable by path and code;
object, property, and link declaration order does not affect the result.

## Impact Classes

| Impact | Meaning | Representative changes |
| --- | --- | --- |
| `NON_BREAKING` | existing consumers and instances remain valid | add object type, optional property, or optional link; relax required or abstract |
| `BEHAVIORAL` | compatibility remains but presentation or runtime behavior may differ | default, index, description, icon, display name, inverse name, or temporal declaration |
| `BREAKING` | existing consumers, instances, or graph contracts may become invalid | removal; type change; required/unique tightening; abstract tightening; interface contract, parent, endpoint, cardinality, namespace change |

Adding a required property or required link is breaking. Adding a new object
type is non-breaking even when the new type itself contains required fields,
because it does not invalidate existing object types.

`unique` is enforced by both Wave 1 stores, so tightening it is breaking and
relaxing it is non-breaking. Required-link tightening is breaking even though
completeness is checked explicitly rather than as a hidden single-object create
gate. Adding an interface implementation is non-breaking; removing one or
changing an interface property contract is breaking.

## Determinism

The comparator:

- consumes only two `CompiledOntologySchema` values;
- performs no I/O and reads no Store or global registry;
- compares collections by stable names rather than declaration position;
- compares JSON defaults canonically;
- emits detached strict-JSON `before` and `after` values;
- produces the same canonical JSON for the same two schema snapshots.

## Non-Goals

V1 does not add:

- automatic migration, backfill, or migration planning;
- `Ontology.upgrade_schema` or mutation of a bound `ObjectStore`;
- Schema Registry, filesystem persistence, or remote publishing;
- hot reload of a running ontology;
- SemVer validation or release approval policy;
- Action, Decision, OWL, or domain ontology behavior.
