"""Public persistent FactStore adapters and physical-format failures."""

from loushang.ontology.storage.sqlite import (
    SQLITE_STORAGE_FORMAT,
    SQLITE_STORAGE_FORMAT_VERSION,
    SQLiteFactStore,
    SQLiteStorageFormatError,
    SQLiteStoreCompatibilityError,
    SQLiteStoredSchemaMismatchError,
)

__all__ = [
    "SQLITE_STORAGE_FORMAT",
    "SQLITE_STORAGE_FORMAT_VERSION",
    "SQLiteFactStore",
    "SQLiteStorageFormatError",
    "SQLiteStoreCompatibilityError",
    "SQLiteStoredSchemaMismatchError",
]
