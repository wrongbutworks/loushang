"""Public persistent ontology store adapters and compatibility failures."""

from loushang.ontology.storage.sqlite import (
    SQLITE_STORAGE_FORMAT,
    SQLITE_STORAGE_FORMAT_VERSION,
    SQLiteObjectStore,
    SQLiteStorageFormatError,
    SQLiteStoreCompatibilityError,
    SQLiteStoredSchemaMismatchError,
)

__all__ = [
    "SQLITE_STORAGE_FORMAT",
    "SQLITE_STORAGE_FORMAT_VERSION",
    "SQLiteObjectStore",
    "SQLiteStorageFormatError",
    "SQLiteStoreCompatibilityError",
    "SQLiteStoredSchemaMismatchError",
]
