from __future__ import annotations

from collections.abc import Iterable

from loushang.method.registry import MethodRegistry
from loushang.method.types import MethodDescriptor


class MethodSelector:
    def __init__(self, source: MethodRegistry | Iterable[MethodDescriptor]) -> None:
        self._source = source

    def select(self, id_or_name: str) -> MethodDescriptor | None:
        if isinstance(self._source, MethodRegistry):
            return self._source.get_method(id_or_name)
        for method in self._source:
            if method.id == id_or_name or method.name == id_or_name:
                return method
        return None


__all__ = ["MethodSelector"]
