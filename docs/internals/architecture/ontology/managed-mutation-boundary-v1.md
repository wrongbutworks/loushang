# Ontology Managed Mutation Boundary V1

## Status

Accepted boundary for writes to in-memory, Store-managed ontology objects. It
closes validation and index bypasses without introducing Actions, transactions,
authorization, audit, or a storage backend abstraction.

## Ownership Model

`ObjectStore.create` binds the returned `OntologyObject` to that store for the
remaining lifetime of the Python object. The binding is internal and cannot be
replaced by another store.

```text
standalone OntologyObject.set/link/unlink
        -> local temporal history only

Store-managed OntologyObject.set/link/unlink
        -> owning ObjectStore mutation port
        -> ownership + schema/cardinality preflight
        -> history/index or bidirectional-link update

Ontology.set_property/link/unlink
        -> the same ObjectStore mutation boundary
```

Deleting an object removes it from the store but does not turn the old Python
handle into a standalone object. A later compatibility mutation therefore fails
as "not managed" instead of silently changing detached state.

## Standard Write Surface

- `Ontology.set_property(object, name, value, ...)` is the explicit property
  write API for application, Rule, and Fusion code.
- `Ontology.link(source, link_type, target, ...)` and `Ontology.unlink(...)` are
  the explicit relation write APIs.
- `OntologyObject.set/link/unlink` remain source-compatible. If the object is
  managed, they delegate to its owner; if it is standalone, they retain the
  original local behavior.
- `ObjectStore` UUID-based `link` and `unlink` methods remain compatibility
  surfaces. Object-aware internal and facade paths use identity-based ownership
  checks so an object from another store cannot be accepted merely because a
  UUID matches.

The mutation port in `ontology.core.mutation` is an internal structural
protocol. It is not a public backend SPI and does not expose ontology types to
HarnessWork.

## Enforced Failure Contract

Property writes validate declared properties, including inherited properties,
before appending history. Indexed values must be hashable. After a successful
write, the old index entry is removed and the new entry is installed. Undeclared
properties retain the existing open-world compatibility behavior and are not
indexed.

Relation writes require both exact object instances to be owned by the same
store. Link definition, endpoint types, and cardinality are checked before
either outgoing or incoming state is appended. Unlink writes append matching
temporal tombstones to both directions. Consequently, an expected validation,
ownership, or cardinality failure creates no half relation.

These are in-memory preflight guarantees, not a general transaction claim.
Unexpected process failure, concurrent storage transactions, multi-object
property commits, external effects, and durable rollback are outside V1.

## Consumer Boundary

Rule property actions and Data Fusion updates call `Ontology.set_property`.
The HarnessWork integration continues to accept product handlers that call the
compatibility methods on a managed `OntologyObject`; those calls reach the same
store boundary. HarnessWork itself remains ontology-neutral and does not import
ontology contracts.

## Acceptance Gates

- invalid managed property values change neither history nor indexes;
- valid indexed updates remove stale index entries;
- deleted and cross-store object handles cannot mutate managed state;
- cardinality and ownership failures create no outgoing/incoming half relation;
- standalone objects preserve local mutation behavior;
- Rule, Fusion, and HarnessWork integration tests exercise the managed path;
- the ontology package retains its product/HarnessWork import boundary.

## Deliberate Deferrals

- `unique` property enforcement;
- required-link enforcement;
- ActionType, MutationPlan, approval, audit, and authorization;
- multi-mutation transactions or durable rollback;
- project-management or environmental domain models.
