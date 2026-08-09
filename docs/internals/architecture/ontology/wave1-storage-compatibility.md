# Ontology SQLite Storage Compatibility

> Historical contract. ARD-002 replaced the undeployed combined v2 layout
> with `storage_layout=phase2`, removed Wave 1 authority/journal tables, and
> added direct FactStore and immutable ProjectionStore adapters. Consult
> [ARD-002](ARD-002-ports-immutable-projection-and-sqlite-v2.md) for the current
> physical contract. This document is retained only as implementation history.

## Status

Superseded physical compatibility contract for the former combined SQLite v2
backend.
Wave 2A retained the Wave 1 detection, schema-snapshot, and backup rules while
replacing the development-only physical format v1 with v2. ARD-001 later
removed the public mutable object-store surface without rewriting the v2 file
layout. The current format is defined together with semantic Facts by
[Wave 2A Facts And Provenance](wave2a-facts-provenance.md).

## Two Independent Versions

SQLite persistence carries two independent identities:

| Identity | Meaning | Compatibility rule |
| --- | --- | --- |
| `storage_format` + `storage_format_version` | physical SQLite layout and encoding | the adapter accepts exactly the format version it implements |
| compiled package ID, namespace, version, and content | immutable semantic schema snapshot | `expected_schema`, when supplied, must equal the complete stored snapshot |

A matching semantic version does not make different schema content compatible.
Likewise, changing the physical storage layout must not be represented by
changing an ontology package version.

The current physical identity is `loushang.ontology.sqlite`, version `2`.
Version 1 is unsupported and has no reader or migration path.

## Open And Detection Contract

Opening a path follows this order:

1. connect to SQLite and inspect its catalog;
2. initialize the current v2 tables only when the database has no application
   tables;
3. otherwise require the format metadata, runtime metadata, and complete v2
   table set before loading any ontology state;
4. load and compile the stored schema snapshot;
5. optionally compare it with `expected_schema`;
6. restore semantic facts and committed batch identities; historical Wave 1
   object/journal/projection state is validated internally because it remains
   part of the unchanged v2 layout.

An unrelated database, an unversioned ontology database, a future or malformed
format version, missing tables or metadata, an invalid stored schema, and
runtime values that cannot be decoded fail explicitly with
`SQLiteStorageFormatError`. Detection does not add tables to an existing
non-ontology database and does not silently repair or upgrade an incompatible
ontology database. A database marked v1 is rejected without mutation.

`SQLiteStoredSchemaMismatchError` is separate from physical-format failure. It
reports both the stored and expected compiled snapshots. The same failure is
used when a caller tries to bind a different schema to an already-bound SQLite
store.

`expected_schema` verifies an existing stored snapshot. It does not bind a
schema to a newly initialized empty database; callers bind through
`SQLiteFactStore.bind_schema(...)`.

## Durability And Backup Contract

One accepted FactBatch persists fact rows, its idempotent batch identity, and
the fact watermark in one SQLite transaction. Reopen therefore restores the
same Fact sequence and replay behavior. Projection refresh is not a second
semantic commit and its persistent coordination belongs to a later phase.

`SQLiteFactStore.backup_to(path)` uses SQLite's online backup mechanism, so
the destination represents one consistent database snapshot. It refuses the
source path and refuses to overwrite an existing destination unless
`overwrite=True` is explicit. The backup is a complete v2 store and is
opened through the same format and schema checks as its source.

`close()` is idempotent and releases the SQLite connection. The store must not
be used after it is closed; context-manager use is preferred.

## Public Surface

Application code uses the stable package-level imports:

```python
from loushang.ontology.storage import (
    SQLITE_STORAGE_FORMAT,
    SQLITE_STORAGE_FORMAT_VERSION,
    SQLiteFactStore,
    SQLiteStorageFormatError,
    SQLiteStoreCompatibilityError,
    SQLiteStoredSchemaMismatchError,
)
```

The SQLite adapter remains under `loushang.ontology.storage`; it is not promoted
to the top-level ontology package because storage selection is an application
composition concern. `SQLiteObjectStore`, `ProjectionState`, and
`StoreMutation` are not public semantic write contracts.

## Explicit Non-Goals

- migration, in-place repair, downgrade, or multi-version readers;
- multi-process or distributed writer coordination;
- SQL query pushdown, optimizer behavior, or a backend registry;
- source adapters, Actions, standards bridges, or domain packages;
- backup scheduling, retention, encryption, or remote object storage.
