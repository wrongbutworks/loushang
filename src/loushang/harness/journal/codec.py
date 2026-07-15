from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
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


@dataclass(frozen=True)
class FunctionalJournalRecordCodec(Generic[R]):
    encoder: Callable[[R], Mapping[str, object]]
    decoder: Callable[[Mapping[str, object]], R]

    def encode_record(self, record: R) -> Mapping[str, object]:
        return self.encoder(record)

    def decode_record(self, value: Mapping[str, object]) -> R:
        return self.decoder(value)


@dataclass(frozen=True)
class FunctionalJournalHeaderCodec(Generic[H]):
    encoder: Callable[[H], Mapping[str, object]]
    decoder: Callable[[Mapping[str, object]], H]

    def encode_header(self, header: H) -> Mapping[str, object]:
        return self.encoder(header)

    def decode_header(self, value: Mapping[str, object]) -> H:
        return self.decoder(value)


__all__ = [
    "FunctionalJournalHeaderCodec",
    "FunctionalJournalRecordCodec",
    "JournalCodecError",
    "JournalHeaderCodec",
    "JournalRecordCodec",
]
