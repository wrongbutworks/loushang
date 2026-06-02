from __future__ import annotations

from collections.abc import Iterable

from loushang.method.types import MethodDescriptor


class MethodRegistry:
    def __init__(self, methods: Iterable[MethodDescriptor] = ()) -> None:
        self._methods: tuple[MethodDescriptor, ...] = ()
        self._selected_method_id: str | None = None
        self.replace_methods(methods)

    def replace_methods(self, methods: Iterable[MethodDescriptor]) -> None:
        method_tuple = tuple(methods)
        seen: set[str] = set()
        for method in method_tuple:
            if method.id in seen:
                raise ValueError(f"duplicate method id: {method.id}")
            seen.add(method.id)
        self._methods = method_tuple
        if self._selected_method_id and self.get_method(self._selected_method_id) is None:
            self._selected_method_id = None

    def list_methods(self) -> list[MethodDescriptor]:
        return list(self._methods)

    def get_method(self, id_or_name: str) -> MethodDescriptor | None:
        for method in self._methods:
            if method.id == id_or_name or method.name == id_or_name:
                return method
        return None

    def select_method(self, id_or_name: str) -> MethodDescriptor | None:
        method = self.get_method(id_or_name)
        self._selected_method_id = method.id if method is not None else None
        return method

    def get_selected_method(self) -> MethodDescriptor | None:
        if self._selected_method_id is None:
            return None
        return self.get_method(self._selected_method_id)

    def clear_selected_method(self) -> None:
        self._selected_method_id = None


__all__ = ["MethodRegistry"]
