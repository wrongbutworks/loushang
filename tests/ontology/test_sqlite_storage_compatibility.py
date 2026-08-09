from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from loushang.ontology import ProjectionState, StoreMutation
from loushang.ontology.schema import (
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    ValueType,
)
from loushang.ontology.storage import (
    SQLITE_STORAGE_FORMAT,
    SQLITE_STORAGE_FORMAT_VERSION,
    SQLiteObjectStore,
    SQLiteStorageFormatError,
    SQLiteStoreCompatibilityError,
    SQLiteStoredSchemaMismatchError,
)


def _schema(*, version: str = "1.0.0", extra_property: bool = False):
    properties = [
        PropertyDefinition("code", ValueType.STRING, required=True, unique=True),
        PropertyDefinition("score", ValueType.INTEGER),
    ]
    if extra_property:
        properties.append(PropertyDefinition("description", ValueType.STRING))
    return OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.sqlite-compatibility",
            namespace="urn:test:sqlite-compatibility",
            version=version,
            object_types=[ObjectTypeDefinition("Asset", properties=properties)],
        )
    )


def _tables(database: Path) -> set[str]:
    with sqlite3.connect(database) as connection:
        return {
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
            if not name.startswith("sqlite_")
        }


def test_new_database_records_an_explicit_storage_format(tmp_path: Path) -> None:
    database = tmp_path / "ontology.sqlite3"

    SQLiteObjectStore(database).close()

    with sqlite3.connect(database) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM ontology_metadata"))
    assert metadata["storage_format"] == SQLITE_STORAGE_FORMAT
    assert metadata["storage_format_version"] == str(SQLITE_STORAGE_FORMAT_VERSION)


def test_non_ontology_database_is_rejected_without_silent_initialization(
    tmp_path: Path,
) -> None:
    database = tmp_path / "other.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE application_data(id INTEGER PRIMARY KEY)")
    before = _tables(database)

    with pytest.raises(SQLiteStorageFormatError, match="storage format metadata"):
        SQLiteObjectStore(database)

    assert _tables(database) == before


def test_unsupported_storage_version_is_rejected_without_upgrade(
    tmp_path: Path,
) -> None:
    database = tmp_path / "future.sqlite3"
    SQLiteObjectStore(database).close()
    future_version = SQLITE_STORAGE_FORMAT_VERSION + 1
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE ontology_metadata SET value = ? WHERE key = 'storage_format_version'",
            (str(future_version),),
        )

    with pytest.raises(SQLiteStorageFormatError) as exc_info:
        SQLiteObjectStore(database)

    assert exc_info.value.expected_version == SQLITE_STORAGE_FORMAT_VERSION
    assert exc_info.value.found_version == str(future_version)
    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            "SELECT value FROM ontology_metadata WHERE key = 'storage_format_version'"
        ).fetchone()
    assert stored == (str(future_version),)


def test_versioned_database_missing_a_required_table_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "incomplete.sqlite3"
    SQLiteObjectStore(database).close()
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE projection_links")

    with pytest.raises(SQLiteStorageFormatError, match="projection_links"):
        SQLiteObjectStore(database)


def test_versioned_database_missing_runtime_metadata_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "incomplete-metadata.sqlite3"
    SQLiteObjectStore(database).close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM ontology_metadata WHERE key = 'source_watermark'"
        )

    with pytest.raises(SQLiteStorageFormatError, match="source_watermark"):
        SQLiteObjectStore(database)


def test_corrupt_stored_schema_is_reported_as_storage_format_failure(
    tmp_path: Path,
) -> None:
    database = tmp_path / "corrupt.sqlite3"
    store = SQLiteObjectStore(database)
    store.bind_schema(_schema())
    store.close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE ontology_schema SET payload = ? WHERE singleton = 1",
            ("{not-json",),
        )

    with pytest.raises(SQLiteStorageFormatError, match="stored ontology schema"):
        SQLiteObjectStore(database)


def test_expected_schema_rejects_same_version_with_different_content(
    tmp_path: Path,
) -> None:
    database = tmp_path / "schema.sqlite3"
    stored_schema = _schema()
    store = SQLiteObjectStore(database)
    store.bind_schema(stored_schema)
    store.close()

    reopened = SQLiteObjectStore(database, expected_schema=stored_schema)
    reopened.close()

    with pytest.raises(SQLiteStoredSchemaMismatchError) as exc_info:
        SQLiteObjectStore(
            database,
            expected_schema=_schema(extra_property=True),
        )

    assert exc_info.value.stored_schema == stored_schema
    assert exc_info.value.expected_schema.version == stored_schema.version


def test_bind_schema_uses_the_same_public_mismatch_failure(tmp_path: Path) -> None:
    store = SQLiteObjectStore(tmp_path / "schema.sqlite3")
    store.bind_schema(_schema())

    with pytest.raises(SQLiteStoredSchemaMismatchError):
        store.bind_schema(_schema(extra_property=True))

    store.close()


def test_online_backup_round_trips_authority_journal_and_projection(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ontology.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    schema = _schema()
    with SQLiteObjectStore(database) as store:
        store.bind_schema(schema)
        asset = store.create("Asset", {"code": "A-1", "score": 1})
        store.set_property(asset, "score", 2, timestamp=20.0, source="test")
        state = store.rebuild_projections()
        store.backup_to(backup)

    restored = SQLiteObjectStore(backup, expected_schema=schema)
    restored_asset = restored.get(asset.id)
    assert restored_asset is not None
    assert restored_asset.get("score") == 2
    assert [item.sequence for item in restored.read_mutations()] == [1, 2]
    assert restored.current_watermark == 2
    assert restored.projection_state == state
    restored.close()


def test_immediate_reopen_preserves_projection_state(tmp_path: Path) -> None:
    database = tmp_path / "ontology.sqlite3"
    schema = _schema()
    store = SQLiteObjectStore(database)
    store.bind_schema(schema)
    store.create("Asset", {"code": "A-1"})
    state = store.projection_state
    store.close()

    reopened = SQLiteObjectStore(database, expected_schema=schema)
    assert reopened.projection_state == state
    reopened.close()


def test_backup_does_not_overwrite_without_explicit_permission(tmp_path: Path) -> None:
    database = tmp_path / "ontology.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    store = SQLiteObjectStore(database)
    backup.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="backup destination"):
        store.backup_to(backup)

    assert backup.read_text(encoding="utf-8") == "keep"
    store.backup_to(backup, overwrite=True)
    SQLiteObjectStore(backup).close()
    store.close()
    store.close()


def test_wave1_state_values_are_available_from_the_public_package() -> None:
    assert ProjectionState.__module__ == "loushang.ontology.core.projection"
    assert StoreMutation.__module__ == "loushang.ontology.core.projection"
    assert issubclass(SQLiteStorageFormatError, SQLiteStoreCompatibilityError)
    assert issubclass(SQLiteStoredSchemaMismatchError, SQLiteStoreCompatibilityError)
