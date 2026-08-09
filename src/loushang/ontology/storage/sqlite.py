"""SQLite reference adapter for the Wave 1 ontology store contract."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
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
from loushang.ontology.schema import CompiledOntologySchema, OntologyCompiler


@dataclass(slots=True)
class _ObjectRuntimeSnapshot:
    obj: OntologyObject
    properties: dict[str, list[PropertyVersion]]
    outgoing: dict[str, list[LinkVersion]]


class SQLiteObjectStore(ObjectStore):
    """Durable store with one SQLite transaction per accepted mutation.

    The in-memory authority remains the reference execution model. SQLite
    persists that authority, the operational mutation journal, and rebuildable
    query projections in the same transaction. Query pushdown is intentionally
    deferred; this adapter establishes semantics and restart durability first.
    """

    def __init__(self, database: str | Path) -> None:
        super().__init__()
        self._database = Path(database)
        self._connection = sqlite3.connect(self._database)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_database()
        self._load_database()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SQLiteObjectStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def bind_schema(
        self,
        schema: CompiledOntologySchema,
        *,
        property_validators: PropertyValidators | None = None,
    ) -> None:
        if self.schema is not None:
            if self.schema == schema:
                return
            raise RuntimeError("SQLiteObjectStore already has a different compiled schema")
        super().bind_schema(schema, property_validators=property_validators)
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO ontology_schema(singleton, payload) VALUES (1, ?)",
                (schema.to_json(),),
            )
            self._persist_metadata()

    def rebuild_projections(self) -> ProjectionState:
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
        sequence = self._watermark + 1
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
                )
        except Exception:
            # SQLite rolled its transaction back. Restore the same managed
            # object instances so callers do not retain stale object handles.
            self._restore_runtime_snapshot(before)
            raise
        self._append_committed_mutation(pending, sequence=sequence)

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
                """
            )

    def _load_database(self) -> None:
        schema_row = self._connection.execute(
            "SELECT payload FROM ontology_schema WHERE singleton = 1"
        ).fetchone()
        if schema_row is None:
            return
        schema = OntologyCompiler().load_json(cast(str, schema_row[0]))
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
    ) -> None:
        values = {
            "source_watermark": str(
                self._watermark if source_watermark is None else source_watermark
            ),
            "projected_watermark": str(
                self._projected_watermark
                if projected_watermark is None
                else projected_watermark
            ),
            "projection_version": str(self._projection_version),
            "projection_built_at": str(time.time()),
        }
        self._connection.executemany(
            "INSERT OR REPLACE INTO ontology_metadata(key, value) VALUES (?, ?)",
            values.items(),
        )


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


__all__ = ["SQLiteObjectStore"]
