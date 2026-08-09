from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

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
    SQLiteFactStore,
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

    SQLiteFactStore(database).close()

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
        SQLiteFactStore(database)

    assert _tables(database) == before


def test_unsupported_storage_version_is_rejected_without_upgrade(
    tmp_path: Path,
) -> None:
    database = tmp_path / "future.sqlite3"
    SQLiteFactStore(database).close()
    future_version = SQLITE_STORAGE_FORMAT_VERSION + 1
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE ontology_metadata SET value = ? WHERE key = 'storage_format_version'",
            (str(future_version),),
        )

    with pytest.raises(SQLiteStorageFormatError) as exc_info:
        SQLiteFactStore(database)

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
    SQLiteFactStore(database).close()
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE projection_links")

    with pytest.raises(SQLiteStorageFormatError, match="projection_links"):
        SQLiteFactStore(database)


def test_versioned_database_missing_runtime_metadata_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "incomplete-metadata.sqlite3"
    SQLiteFactStore(database).close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM ontology_metadata WHERE key = 'source_watermark'"
        )

    with pytest.raises(SQLiteStorageFormatError, match="source_watermark"):
        SQLiteFactStore(database)


def test_corrupt_stored_schema_is_reported_as_storage_format_failure(
    tmp_path: Path,
) -> None:
    database = tmp_path / "corrupt.sqlite3"
    store = SQLiteFactStore(database)
    store.bind_schema(_schema())
    store.close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE ontology_schema SET payload = ? WHERE singleton = 1",
            ("{not-json",),
        )

    with pytest.raises(SQLiteStorageFormatError, match="stored ontology schema"):
        SQLiteFactStore(database)


def test_expected_schema_rejects_same_version_with_different_content(
    tmp_path: Path,
) -> None:
    database = tmp_path / "schema.sqlite3"
    stored_schema = _schema()
    store = SQLiteFactStore(database)
    store.bind_schema(stored_schema)
    store.close()

    reopened = SQLiteFactStore(database, expected_schema=stored_schema)
    reopened.close()

    with pytest.raises(SQLiteStoredSchemaMismatchError) as exc_info:
        SQLiteFactStore(
            database,
            expected_schema=_schema(extra_property=True),
        )

    assert exc_info.value.stored_schema == stored_schema
    assert exc_info.value.expected_schema.version == stored_schema.version


def test_bind_schema_uses_the_same_public_mismatch_failure(tmp_path: Path) -> None:
    store = SQLiteFactStore(tmp_path / "schema.sqlite3")
    store.bind_schema(_schema())

    with pytest.raises(SQLiteStoredSchemaMismatchError):
        store.bind_schema(_schema(extra_property=True))

    store.close()


def test_backup_does_not_overwrite_without_explicit_permission(tmp_path: Path) -> None:
    database = tmp_path / "ontology.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    store = SQLiteFactStore(database)
    backup.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="backup destination"):
        store.backup_to(backup)

    assert backup.read_text(encoding="utf-8") == "keep"
    store.backup_to(backup, overwrite=True)
    SQLiteFactStore(backup).close()
    store.close()
    store.close()
    assert issubclass(SQLiteStorageFormatError, SQLiteStoreCompatibilityError)
    assert issubclass(SQLiteStoredSchemaMismatchError, SQLiteStoreCompatibilityError)
