# Ontology Wave 1 SQLite Storage Compatibility

## Status

Accepted compatibility contract for the Wave 1 SQLite reference adapter. This
contract freezes format detection, schema-snapshot verification, backup, and
public import behavior. It does not introduce a migration framework or expand
the Semantic Kernel into later ontology waves.

## Two Independent Versions

SQLite persistence carries two independent identities:

| Identity | Meaning | Compatibility rule |
| --- | --- | --- |
| `storage_format` + `storage_format_version` | physical SQLite layout and encoding | the adapter accepts exactly the format version it implements |
| compiled package ID, namespace, version, and content | immutable semantic schema snapshot | `expected_schema`, when supplied, must equal the complete stored snapshot |

A matching semantic version does not make different schema content compatible.
Likewise, changing the physical storage layout must not be represented by
changing an ontology package version.

The current physical identity is `loushang.ontology.sqlite`, version `1`.

## Open And Detection Contract

Opening a path follows this order:

1. connect to SQLite and inspect its catalog;
2. initialize the Wave 1 tables only when the database has no application
   tables;
3. otherwise require the format metadata, runtime metadata, and complete Wave 1
   table set before loading any ontology state;
4. load and compile the stored schema snapshot;
5. optionally compare it with `expected_schema`;
6. restore authority, mutation journal, projection state, and watermarks.

An unrelated database, an unversioned ontology database, a future or malformed
format version, missing tables or metadata, an invalid stored schema, and
runtime values that cannot be decoded fail explicitly with
`SQLiteStorageFormatError`. Detection does not add tables to an existing
non-ontology database and does not silently repair or upgrade an incompatible
ontology database.

`SQLiteStoredSchemaMismatchError` is separate from physical-format failure. It
reports both the stored and expected compiled snapshots. The same failure is
used when a caller tries to bind a different schema to an already-bound SQLite
store.

`expected_schema` verifies an existing stored snapshot. It does not bind a
schema to a newly initialized empty database; callers bind through
`Ontology.from_schema(...)` or `SQLiteObjectStore.bind_schema(...)`.

## Durability And Backup Contract

One accepted mutation persists the authoritative object history, operational
mutation journal, rebuildable projections, source/projected watermarks, and one
shared projection build timestamp in one SQLite transaction. A direct reopen
therefore returns the same `ProjectionState` as the committed in-memory store.

`SQLiteObjectStore.backup_to(path)` uses SQLite's online backup mechanism, so
the destination represents one consistent database snapshot. It refuses the
source path and refuses to overwrite an existing destination unless
`overwrite=True` is explicit. The backup is a complete Wave 1 store and is
opened through the same format and schema checks as its source.

`close()` is idempotent and releases the SQLite connection. The store must not
be used after it is closed; context-manager use is preferred.

## Public Surface

Application code uses the stable package-level imports:

```python
from loushang.ontology import ProjectionState, StoreMutation
from loushang.ontology.storage import (
    SQLITE_STORAGE_FORMAT,
    SQLITE_STORAGE_FORMAT_VERSION,
    SQLiteObjectStore,
    SQLiteStorageFormatError,
    SQLiteStoreCompatibilityError,
    SQLiteStoredSchemaMismatchError,
)
```

The SQLite adapter remains under `loushang.ontology.storage`; it is not promoted
to the top-level ontology package because storage selection is an application
composition concern. `ProjectionState` and `StoreMutation` are top-level values
because public Store ports return them.

## Explicit Non-Goals

- migration, in-place repair, downgrade, or multi-version readers;
- multi-process or distributed writer coordination;
- SQL query pushdown, optimizer behavior, or a backend registry;
- semantic Fact/Provenance records, adapters, Actions, or domain packages;
- backup scheduling, retention, encryption, or remote object storage.
