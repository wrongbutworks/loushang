from __future__ import annotations


class ConversationStoreError(RuntimeError):
    """Base error raised by a conversation storage provider."""


class StoreAlreadyExistsError(ConversationStoreError):
    """Raised when creating a conversation whose key already exists."""


class StoreNotFoundError(ConversationStoreError):
    """Raised when a conversation key cannot be resolved."""


class StoreConflictError(ConversationStoreError):
    """Raised when optimistic revision validation fails."""


class StoreDataError(ConversationStoreError):
    """Raised when persisted conversation data cannot be read or written."""


__all__ = [
    "ConversationStoreError",
    "StoreAlreadyExistsError",
    "StoreConflictError",
    "StoreDataError",
    "StoreNotFoundError",
]
