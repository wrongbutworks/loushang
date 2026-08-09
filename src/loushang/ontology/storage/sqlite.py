"""SQLite v2 semantic FactStore adapter and internal projection persistence."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import cast
from uuid import UUID

from loushang.foundation.json import (
    JSONValue,
    dump_json_value,
    require_json_mapping,
    require_json_value,
)
from loushang.ontology.core._value_codec import decode_store_value, encode_store_value
from loushang.ontology.core.object import LinkVersion, OntologyObject, PropertyVersion
from loushang.ontology.core.projection import ProjectionState, StoreMutation
from loushang.ontology.core.schema_runtime import PropertyValidators
from loushang.ontology.core.store import ObjectStore, _PendingMutation
from loushang.ontology.facts.model import FactBatch, FactRecord
from loushang.ontology.facts.store import FactCommit, MemoryFactStore, StoredFact
from loushang.ontology.schema import (
    CompiledOntologySchema,
    OntologyCompiler,
    SchemaCompilationError,
)

SQLITE_STORAGE_FORMAT = "loushang.ontology.sqlite"
SQLITE_STORAGE_FORMAT_VERSION = 2

_REQUIRED_TABLES = frozenset(
    {
        "ontology_schema",
        "ontology_metadata",
        "authority_objects",
        "mutation_journal",
        "projection_objects",
        "projection_properties",
        "projection_unique_values",
        "projection_links",
        "semantic_facts",
        "fact_batches",
    }
)
_REQUIRED_METADATA_KEYS = frozenset(
    {
        "storage_format",
        "storage_format_version",
        "source_watermark",
        "projected_watermark",
        "projection_version",
        "projection_built_at",
        "fact_watermark",
    }
)


class SQLiteStoreCompatibilityError(RuntimeError):
    """Base class for failures detected before a SQLite store can be used."""


class SQLiteStorageFormatError(SQLiteStoreCompatibilityError):
    """Raised when an existing database is not this supported storage format."""

    def __init__(
        self,
        database: Path,
        reason: str,
        *,
        found_format: str | None = None,
        found_version: str | None = None,
    ) -> None:
        self.database = database
        self.reason = reason
        self.expected_format = SQLITE_STORAGE_FORMAT
        self.expected_version = SQLITE_STORAGE_FORMAT_VERSION
        self.found_format = found_format
        self.found_version = found_version
        super().__init__(
            f"SQLite ontology storage at '{database}' is incompatible: {reason}"
        )


class SQLiteStoredSchemaMismatchError(SQLiteStoreCompatibilityError):
    """Raised when a database schema differs from the caller's expected snapshot."""

    def __init__(
        self,
        database: Path,
        *,
        stored_schema: CompiledOntologySchema,
        expected_schema: CompiledOntologySchema,
    ) -> None:
        self.database = database
        self.stored_schema = stored_schema
        self.expected_schema = expected_schema
        super().__init__(
            f"SQLite ontology schema at '{database}' does not match the expected "
            f"snapshot for package '{expected_schema.package_id}' version "
            f"'{expected_schema.version}'"
        )


@dataclass(slots=True)
class _ObjectRuntimeSnapshot:
    obj: OntologyObject
    properties: dict[str, list[PropertyVersion]]
    outgoing: dict[str, list[LinkVersion]]


class _SQLiteObjectStore(ObjectStore):
    """Internal combined backend retained until the adapter split in Phase 2.

    The in-memory authority remains the reference execution model. SQLite
    persists that authority, the operational mutation journal, and rebuildable
    query projections in the same transaction. SQLite v2 also persists the
    append-only semantic fact journal and idempotent batch identities. Query
    pushdown is intentionally deferred.
    """

    def __init__(
        self,
        database: str | Path,
        *,
        expected_schema: CompiledOntologySchema | None = None,
    ) -> None:
        super().__init__()
        self._fact_store = MemoryFactStore()
        self._database = Path(database)
        self._connection = sqlite3.connect(self._database)
        self._closed = False
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            tables = self._database_tables()
            if tables:
                self._validate_existing_database(tables)
            else:
                self._initialize_database()
            self._load_database(expected_schema=expected_schema)
        except SQLiteStoreCompatibilityError:
            self._connection.close()
            self._closed = True
            raise
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            sqlite3.DatabaseError,
        ) as exc:
            self._connection.close()
            self._closed = True
            raise SQLiteStorageFormatError(
                self._database,
                "stored ontology runtime data is invalid",
            ) from exc

    @property
    def database(self) -> Path:
        return self._database

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True

    def __enter__(self) -> _SQLiteObjectStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def backup_to(
        self,
        destination: str | Path,
        *,
        overwrite: bool = False,
    ) -> None:
        """Create a transactionally consistent SQLite backup."""

        self._require_open()
        target_path = Path(destination)
        if self._database.resolve() == target_path.resolve():
            raise ValueError(
                "SQLite backup destination must differ from the source database"
            )
        if target_path.exists() and not overwrite:
            raise FileExistsError(
                f"SQLite backup destination already exists: {target_path}"
            )
        if target_path.exists():
            with NamedTemporaryFile(
                dir=target_path.parent,
                prefix=f".{target_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                staging_path = Path(temporary.name)
            try:
                self._write_backup(staging_path)
                staging_path.replace(target_path)
            finally:
                staging_path.unlink(missing_ok=True)
            return
        self._write_backup(target_path)

    def _write_backup(self, target_path: Path) -> None:
        target = sqlite3.connect(target_path)
        try:
            self._connection.backup(target)
        finally:
            target.close()

    def bind_schema(
        self,
        schema: CompiledOntologySchema,
        *,
        property_validators: PropertyValidators | None = None,
    ) -> None:
        self._require_open()
        if self.schema is not None:
            if self.schema == schema:
                return
            raise SQLiteStoredSchemaMismatchError(
                self._database,
                stored_schema=self.schema,
                expected_schema=schema,
            )
        super().bind_schema(schema, property_validators=property_validators)
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO ontology_schema(singleton, payload) VALUES (1, ?)",
                (schema.to_json(),),
            )
            self._persist_metadata()

    @property
    def fact_watermark(self) -> int:
        return self._fact_store.fact_watermark

    def get_fact(self, fact_id: UUID) -> StoredFact:
        return self._fact_store.get_fact(fact_id)

    def read_facts(self, *, after_sequence: int = 0) -> tuple[StoredFact, ...]:
        return self._fact_store.read_facts(after_sequence=after_sequence)

    def facts_as_of(
        self,
        *,
        valid_at: float,
        recorded_at: float,
    ) -> tuple[StoredFact, ...]:
        return self._fact_store.facts_as_of(
            valid_at=valid_at,
            recorded_at=recorded_at,
        )

    def commit_fact_batch(self, batch: FactBatch) -> FactCommit:
        """Append one semantic fact batch in a single SQLite transaction."""

        self._require_open()
        if self.schema is None:
            raise RuntimeError("SQLite fact commits require a bound schema")
        plan = self._fact_store._plan_commit(batch)
        if plan.commit.replayed:
            return plan.commit
        with self._connection:
            self._connection.executemany(
                """
                INSERT INTO semantic_facts(sequence, fact_id, payload)
                VALUES (?, ?, ?)
                """,
                [
                    (entry.sequence, str(entry.fact.fact_id), entry.fact.to_json())
                    for entry in plan.entries
                ],
            )
            self._connection.execute(
                """
                INSERT INTO fact_batches(
                    batch_id, digest, first_sequence, last_sequence, fact_count
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    plan.batch.batch_id,
                    plan.digest,
                    plan.commit.first_sequence,
                    plan.commit.last_sequence,
                    plan.commit.fact_count,
                ),
            )
            self._persist_metadata(fact_watermark=plan.commit.last_sequence)
        self._fact_store._apply_commit(plan)
        return plan.commit

    def rebuild_projections(self) -> ProjectionState:
        self._require_open()
        previous = (
            self._projection_version,
            self._projected_watermark,
            self._projection_built_at,
        )
        self._rebuild_memory_projections()
        self._projection_version += 1
        self._projected_watermark = self._watermark
        self._projection_built_at = time.time()
        try:
            with self._connection:
                self._persist_projections()
                self._persist_metadata()
        except Exception:
            (
                self._projection_version,
                self._projected_watermark,
                self._projection_built_at,
            ) = previous
            raise
        return self.projection_state

    def _commit_mutation(
        self,
        pending: _PendingMutation,
        apply: Callable[[], None],
    ) -> None:
        self._require_open()
        sequence = self._watermark + 1
        committed_at = time.time()
        before = self._capture_runtime_snapshot()
        apply()
        try:
            with self._connection:
                self._persist_authority()
                self._connection.execute(
                    """
                    INSERT INTO mutation_journal(sequence, kind, payload, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        sequence,
                        pending.kind,
                        dump_json_value(pending.payload, name="ontology mutation", sort_keys=True),
                        pending.timestamp,
                    ),
                )
                self._persist_projections()
                self._persist_metadata(
                    source_watermark=sequence,
                    projected_watermark=sequence,
                    projection_built_at=committed_at,
                )
        except Exception:
            # SQLite rolled its transaction back. Restore the same managed
            # object instances so callers do not retain stale object handles.
            self._restore_runtime_snapshot(before)
            raise
        self._append_committed_mutation(pending, sequence=sequence)
        self._projection_built_at = committed_at

    def _initialize_database(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ontology_schema (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ontology_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS authority_objects (
                    object_id TEXT PRIMARY KEY,
                    object_type TEXT NOT NULL,
                    state_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mutation_journal (
                    sequence INTEGER PRIMARY KEY,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projection_objects (
                    object_id TEXT PRIMARY KEY,
                    object_type TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS projection_objects_type
                    ON projection_objects(object_type);
                CREATE TABLE IF NOT EXISTS projection_properties (
                    object_id TEXT NOT NULL,
                    property_name TEXT NOT NULL,
                    declaring_type TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    PRIMARY KEY (object_id, property_name),
                    FOREIGN KEY (object_id) REFERENCES projection_objects(object_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS projection_property_lookup
                    ON projection_properties(property_name, value_json);
                CREATE TABLE IF NOT EXISTS projection_unique_values (
                    declaring_type TEXT NOT NULL,
                    property_name TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    PRIMARY KEY (declaring_type, property_name, value_json),
                    FOREIGN KEY (object_id) REFERENCES projection_objects(object_id)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS projection_links (
                    source_id TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    properties_json TEXT NOT NULL,
                    PRIMARY KEY (source_id, link_type, target_id),
                    FOREIGN KEY (source_id) REFERENCES projection_objects(object_id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES projection_objects(object_id)
                        ON DELETE RESTRICT
                );
                CREATE INDEX IF NOT EXISTS projection_links_target
                    ON projection_links(target_id, link_type);
                CREATE TABLE IF NOT EXISTS semantic_facts (
                    sequence INTEGER PRIMARY KEY,
                    fact_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fact_batches (
                    batch_id TEXT PRIMARY KEY,
                    digest TEXT NOT NULL,
                    first_sequence INTEGER NOT NULL,
                    last_sequence INTEGER NOT NULL,
                    fact_count INTEGER NOT NULL
                );
                """
            )
            self._persist_metadata()

    def _database_tables(self) -> set[str]:
        try:
            return {
                name
                for (name,) in self._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
                if not name.startswith("sqlite_")
            }
        except sqlite3.DatabaseError as exc:
            raise SQLiteStorageFormatError(
                self._database,
                "database header or catalog is invalid",
            ) from exc

    def _validate_existing_database(self, tables: set[str]) -> None:
        if "ontology_metadata" not in tables:
            raise SQLiteStorageFormatError(
                self._database,
                "storage format metadata table is missing",
            )
        try:
            metadata = dict(
                self._connection.execute("SELECT key, value FROM ontology_metadata")
            )
        except sqlite3.DatabaseError as exc:
            raise SQLiteStorageFormatError(
                self._database,
                "storage format metadata cannot be read",
            ) from exc

        found_format = cast(str | None, metadata.get("storage_format"))
        found_version = cast(str | None, metadata.get("storage_format_version"))
        missing_metadata = _REQUIRED_METADATA_KEYS - metadata.keys()
        if missing_metadata:
            raise SQLiteStorageFormatError(
                self._database,
                "storage format metadata is incomplete: "
                f"{', '.join(sorted(missing_metadata))}",
                found_format=found_format,
                found_version=found_version,
            )
        assert found_format is not None
        assert found_version is not None
        if found_format != SQLITE_STORAGE_FORMAT:
            raise SQLiteStorageFormatError(
                self._database,
                f"unsupported storage format '{found_format}'",
                found_format=found_format,
                found_version=found_version,
            )
        try:
            version = int(found_version)
        except ValueError as exc:
            raise SQLiteStorageFormatError(
                self._database,
                f"storage format version '{found_version}' is not an integer",
                found_format=found_format,
                found_version=found_version,
            ) from exc
        if version != SQLITE_STORAGE_FORMAT_VERSION:
            raise SQLiteStorageFormatError(
                self._database,
                f"unsupported storage format version '{found_version}'",
                found_format=found_format,
                found_version=found_version,
            )
        missing = _REQUIRED_TABLES - tables
        if missing:
            raise SQLiteStorageFormatError(
                self._database,
                f"required storage tables are missing: {', '.join(sorted(missing))}",
                found_format=found_format,
                found_version=found_version,
            )

    def _load_database(
        self,
        *,
        expected_schema: CompiledOntologySchema | None,
    ) -> None:
        schema_row = self._connection.execute(
            "SELECT payload FROM ontology_schema WHERE singleton = 1"
        ).fetchone()
        if schema_row is None:
            if self._database_contains_runtime_state():
                raise SQLiteStorageFormatError(
                    self._database,
                    "runtime state exists without a stored ontology schema",
                )
            return
        try:
            schema = OntologyCompiler().load_json(cast(str, schema_row[0]))
        except SchemaCompilationError as exc:
            raise SQLiteStorageFormatError(
                self._database,
                "stored ontology schema is invalid",
            ) from exc
        if expected_schema is not None and schema != expected_schema:
            raise SQLiteStoredSchemaMismatchError(
                self._database,
                stored_schema=schema,
                expected_schema=expected_schema,
            )
        if self.schema is None:
            ObjectStore.bind_schema(self, schema)

        for object_id, object_type, state_json in self._connection.execute(
            "SELECT object_id, object_type, state_json FROM authority_objects ORDER BY rowid"
        ):
            obj = _decode_object(UUID(object_id), object_type, state_json)
            obj._bind_mutation_port(self)
            self._objects[obj.id] = obj

        self._rebuild_memory_projections()
        self._mutations = [
            StoreMutation(
                sequence=sequence,
                kind=kind,
                payload=require_json_mapping(json.loads(payload), name="ontology mutation"),
                timestamp=timestamp,
            )
            for sequence, kind, payload, timestamp in self._connection.execute(
                "SELECT sequence, kind, payload, timestamp FROM mutation_journal ORDER BY sequence"
            )
        ]
        metadata = dict(self._connection.execute("SELECT key, value FROM ontology_metadata"))
        self._watermark = int(metadata.get("source_watermark", "0"))
        self._projected_watermark = int(metadata.get("projected_watermark", "0"))
        self._projection_version = int(metadata.get("projection_version", "1"))
        self._projection_built_at = float(metadata.get("projection_built_at", str(time.time())))
        self._load_fact_store(metadata)

    def _load_fact_store(self, metadata: dict[str, str]) -> None:
        loaded_entries: list[StoredFact] = []
        for sequence, fact_id, payload in self._connection.execute(
            "SELECT sequence, fact_id, payload FROM semantic_facts ORDER BY sequence"
        ):
            fact = FactRecord.from_json(payload)
            if str(fact.fact_id) != fact_id:
                raise SQLiteStorageFormatError(
                    self._database,
                    "stored semantic fact identity does not match its payload",
                )
            loaded_entries.append(StoredFact(sequence=sequence, fact=fact))
        entries = tuple(loaded_entries)

        stored_watermark = int(metadata["fact_watermark"])
        if stored_watermark != len(entries):
            raise SQLiteStorageFormatError(
                self._database,
                "stored fact watermark does not match the semantic fact journal",
            )

        batch_rows = tuple(
            self._connection.execute(
                """
                SELECT batch_id, digest, first_sequence, last_sequence, fact_count
                FROM fact_batches ORDER BY first_sequence
                """
            )
        )
        ranges = [
            sequence
            for _, _, first_sequence, last_sequence, _ in batch_rows
            for sequence in range(first_sequence, last_sequence + 1)
        ]
        expected_ranges = list(range(1, stored_watermark + 1))
        if ranges != expected_ranges:
            raise SQLiteStorageFormatError(
                self._database,
                "stored fact batches do not cover the semantic fact journal",
            )

        batches: dict[str, tuple[str, FactCommit]] = {}
        entries_by_sequence = {entry.sequence: entry for entry in entries}
        for batch_id, digest, first_sequence, last_sequence, fact_count in batch_rows:
            if not isinstance(digest, str) or len(digest) != 64:
                raise SQLiteStorageFormatError(
                    self._database,
                    "stored fact batch digest is invalid",
                )
            restored_batch = FactBatch(
                batch_id,
                [
                    entries_by_sequence[sequence].fact
                    for sequence in range(first_sequence, last_sequence + 1)
                ],
            )
            if restored_batch.content_digest != digest:
                raise SQLiteStorageFormatError(
                    self._database,
                    "stored fact batch digest does not match its semantic facts",
                )
            commit = FactCommit(
                batch_id=batch_id,
                first_sequence=first_sequence,
                last_sequence=last_sequence,
                fact_count=fact_count,
            )
            batches[batch_id] = (digest, commit)
        self._fact_store._restore_committed_state(entries, batches)

    def _database_contains_runtime_state(self) -> bool:
        for query in (
            "SELECT 1 FROM authority_objects LIMIT 1",
            "SELECT 1 FROM mutation_journal LIMIT 1",
            "SELECT 1 FROM projection_objects LIMIT 1",
            "SELECT 1 FROM projection_properties LIMIT 1",
            "SELECT 1 FROM projection_unique_values LIMIT 1",
            "SELECT 1 FROM projection_links LIMIT 1",
            "SELECT 1 FROM semantic_facts LIMIT 1",
            "SELECT 1 FROM fact_batches LIMIT 1",
        ):
            if self._connection.execute(query).fetchone():
                return True
        return False

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("SQLite ontology backend is closed")

    def _capture_runtime_snapshot(self) -> dict[UUID, _ObjectRuntimeSnapshot]:
        return {
            object_id: _ObjectRuntimeSnapshot(
                obj=obj,
                properties={name: list(versions) for name, versions in obj._properties.items()},
                outgoing={name: list(versions) for name, versions in obj._outgoing.items()},
            )
            for object_id, obj in self._objects.items()
        }

    def _restore_runtime_snapshot(
        self,
        snapshot: dict[UUID, _ObjectRuntimeSnapshot],
    ) -> None:
        self._objects = {object_id: item.obj for object_id, item in snapshot.items()}
        for item in snapshot.values():
            item.obj._properties = {
                name: list(versions) for name, versions in item.properties.items()
            }
            item.obj._outgoing = {
                name: list(versions) for name, versions in item.outgoing.items()
            }
            item.obj._incoming = {}
        self._rebuild_memory_projections()

    def _persist_authority(self) -> None:
        self._connection.execute("DELETE FROM authority_objects")
        self._connection.executemany(
            "INSERT INTO authority_objects(object_id, object_type, state_json) VALUES (?, ?, ?)",
            [
                (str(obj.id), obj.object_type, _encode_object(obj))
                for obj in self._objects.values()
            ],
        )

    def _persist_projections(self) -> None:
        self._connection.execute("DELETE FROM projection_links")
        self._connection.execute("DELETE FROM projection_unique_values")
        self._connection.execute("DELETE FROM projection_properties")
        self._connection.execute("DELETE FROM projection_objects")
        self._connection.executemany(
            "INSERT INTO projection_objects(object_id, object_type) VALUES (?, ?)",
            [(str(obj.id), obj.object_type) for obj in self._objects.values()],
        )

        property_rows: list[tuple[str, str, str, str]] = []
        unique_rows: list[tuple[str, str, str, str]] = []
        link_rows: list[tuple[str, str, str, str]] = []
        for obj in self._objects.values():
            type_def = self._object_types[obj.object_type]
            declarations = self._resolved_property_declarations(type_def)
            for name in obj._properties:
                value = obj.get(name)
                if value is None:
                    continue
                declaration = declarations.get(name)
                owner = declaration[0] if declaration is not None else obj.object_type
                prop = declaration[1] if declaration is not None else None
                value_json = dump_json_value(
                    encode_store_value(value),
                    name="projected ontology value",
                    sort_keys=True,
                )
                property_rows.append((str(obj.id), name, owner, value_json))
                if prop is not None and prop.unique:
                    unique_rows.append((owner, name, value_json, str(obj.id)))
            for link_name in obj._outgoing:
                for link in obj.get_links(link_name):
                    link_rows.append(
                        (
                            str(obj.id),
                            link_name,
                            str(link.target_id),
                            dump_json_value(link.properties, name="link properties", sort_keys=True),
                        )
                    )

        self._connection.executemany(
            """
            INSERT INTO projection_properties(
                object_id, property_name, declaring_type, value_json
            ) VALUES (?, ?, ?, ?)
            """,
            property_rows,
        )
        self._connection.executemany(
            """
            INSERT INTO projection_unique_values(
                declaring_type, property_name, value_json, object_id
            ) VALUES (?, ?, ?, ?)
            """,
            unique_rows,
        )
        self._connection.executemany(
            """
            INSERT INTO projection_links(source_id, link_type, target_id, properties_json)
            VALUES (?, ?, ?, ?)
            """,
            link_rows,
        )

    def _persist_metadata(
        self,
        *,
        source_watermark: int | None = None,
        projected_watermark: int | None = None,
        projection_built_at: float | None = None,
        fact_watermark: int | None = None,
    ) -> None:
        values = {
            "storage_format": SQLITE_STORAGE_FORMAT,
            "storage_format_version": str(SQLITE_STORAGE_FORMAT_VERSION),
            "source_watermark": str(
                self._watermark if source_watermark is None else source_watermark
            ),
            "projected_watermark": str(
                self._projected_watermark
                if projected_watermark is None
                else projected_watermark
            ),
            "projection_version": str(self._projection_version),
            "projection_built_at": str(
                self._projection_built_at
                if projection_built_at is None
                else projection_built_at
            ),
            "fact_watermark": str(
                self.fact_watermark if fact_watermark is None else fact_watermark
            ),
        }
        self._connection.executemany(
            "INSERT OR REPLACE INTO ontology_metadata(key, value) VALUES (?, ?)",
            values.items(),
        )


class SQLiteFactStore:
    """Public SQLite v2 adapter exposing only the semantic FactStore authority.

    The v2 file still contains the Wave 1 object/projection tables so its format
    remains unchanged. Those tables and their direct mutation implementation
    are deliberately hidden until Phase 2 replaces them with a projection-only
    adapter.
    """

    def __init__(
        self,
        database: str | Path,
        *,
        expected_schema: CompiledOntologySchema | None = None,
    ) -> None:
        self._backend = _SQLiteObjectStore(
            database,
            expected_schema=expected_schema,
        )

    @property
    def database(self) -> Path:
        return self._backend.database

    @property
    def schema(self) -> CompiledOntologySchema | None:
        return self._backend.schema

    @property
    def fact_watermark(self) -> int:
        return self._backend.fact_watermark

    def bind_schema(self, schema: CompiledOntologySchema) -> None:
        self._backend.bind_schema(schema)

    def get_fact(self, fact_id: UUID) -> StoredFact:
        return self._backend.get_fact(fact_id)

    def read_facts(self, *, after_sequence: int = 0) -> tuple[StoredFact, ...]:
        return self._backend.read_facts(after_sequence=after_sequence)

    def facts_as_of(
        self,
        *,
        valid_at: float,
        recorded_at: float,
    ) -> tuple[StoredFact, ...]:
        return self._backend.facts_as_of(
            valid_at=valid_at,
            recorded_at=recorded_at,
        )

    def commit_fact_batch(self, batch: FactBatch) -> FactCommit:
        return self._backend.commit_fact_batch(batch)

    def backup_to(
        self,
        destination: str | Path,
        *,
        overwrite: bool = False,
    ) -> None:
        self._backend.backup_to(destination, overwrite=overwrite)

    def close(self) -> None:
        self._backend.close()

    def __enter__(self) -> SQLiteFactStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _encode_object(obj: OntologyObject) -> str:
    document: dict[str, JSONValue] = {
        "properties": {
            name: [
                {
                    "value": encode_store_value(version.value),
                    "timestamp": version.timestamp,
                    "author": version.author,
                    "source": version.source,
                }
                for version in versions
            ]
            for name, versions in obj._properties.items()
        },
        "outgoing": {
            name: [
                {
                    "target_id": str(version.target_id),
                    "timestamp": version.timestamp,
                    "active": version.active,
                    "properties": require_json_mapping(
                        version.properties,
                        name="link properties",
                    ),
                }
                for version in versions
            ]
            for name, versions in obj._outgoing.items()
        },
    }
    return dump_json_value(document, name="ontology object authority", sort_keys=True)


def _decode_object(object_id: UUID, object_type: str, state_json: str) -> OntologyObject:
    document = require_json_mapping(json.loads(state_json), name="ontology object authority")
    properties_document = require_json_mapping(document.get("properties", {}), name="properties")
    outgoing_document = require_json_mapping(document.get("outgoing", {}), name="outgoing")

    properties: dict[str, list[PropertyVersion]] = {}
    for name, raw_versions in properties_document.items():
        versions = cast(list[JSONValue], require_json_value(raw_versions, name="property history"))
        properties[name] = []
        for raw_version in versions:
            version = require_json_mapping(raw_version, name="property version")
            properties[name].append(
                PropertyVersion(
                    value=decode_store_value(version["value"]),
                    timestamp=float(cast(int | float, version["timestamp"])),
                    author=cast(str | None, version.get("author")),
                    source=cast(str | None, version.get("source")),
                )
            )

    outgoing: dict[str, list[LinkVersion]] = {}
    for name, raw_versions in outgoing_document.items():
        versions = cast(list[JSONValue], require_json_value(raw_versions, name="link history"))
        outgoing[name] = []
        for raw_version in versions:
            version = require_json_mapping(raw_version, name="link version")
            outgoing[name].append(
                LinkVersion(
                    target_id=UUID(cast(str, version["target_id"])),
                    timestamp=float(cast(int | float, version["timestamp"])),
                    active=cast(bool, version["active"]),
                    properties=require_json_mapping(
                        version.get("properties", {}),
                        name="link properties",
                    ),
                )
            )
    return OntologyObject(
        object_type=object_type,
        obj_id=object_id,
        properties=properties,
        outgoing_links=outgoing,
    )


__all__ = [
    "SQLITE_STORAGE_FORMAT",
    "SQLITE_STORAGE_FORMAT_VERSION",
    "SQLiteFactStore",
    "SQLiteStorageFormatError",
    "SQLiteStoreCompatibilityError",
    "SQLiteStoredSchemaMismatchError",
]
