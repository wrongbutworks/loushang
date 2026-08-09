# Ontology Managed Mutation Boundary V1

## Status

Accepted historical boundary for the initial in-memory managed-write slice. It
is extended by the implemented
[Wave 1 Completion Boundary](wave1-completion-boundary.md), which adds unique
enforcement, delete-reference integrity, the operational commit sequence,
SQLite transactions, and replaceable Store/Projection ports. Action,
authorization, approval, and semantic audit remain deferred.

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

These are preflight guarantees shared by Memory and SQLite. SQLite additionally
commits authority, journal, serving projections, and watermarks in one database
transaction and restores managed object identity after a failed database
commit. Multi-object MutationPlan, concurrent multi-writer coordination, and
external effects remain outside Wave 1.

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

- hidden required-link enforcement during single-object creation (explicit
  integrity validation is implemented);
- ActionType, MutationPlan, approval, audit, and authorization;
- multi-mutation transactions or durable rollback;
- project-management or environmental domain models.
