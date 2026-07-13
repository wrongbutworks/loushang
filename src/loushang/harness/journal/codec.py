from __future__ import annotations

from collections.abc import Mapping
from typing import Generic, Protocol, TypeVar

H = TypeVar("H")
R = TypeVar("R")


class JournalCodecError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_value") -> None:
        super().__init__(message)
        self.code = code


class JournalRecordCodec(Protocol, Generic[R]):
    def encode_record(self, record: R) -> Mapping[str, object]: ...

    def decode_record(self, value: Mapping[str, object]) -> R: ...


class JournalHeaderCodec(Protocol, Generic[H]):
    def encode_header(self, header: H) -> Mapping[str, object]: ...

    def decode_header(self, value: Mapping[str, object]) -> H: ...


__all__ = [
    "JournalCodecError",
    "JournalHeaderCodec",
    "JournalRecordCodec",
]
