"""Internal mutation port used by Store-managed ontology objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from loushang.ontology.core.object import OntologyObject


class ManagedObjectMutationPort(Protocol):
    """Route compatibility object writes through their owning runtime."""

    def set_property(
        self,
        obj: OntologyObject,
        name: str,
        value: Any,
        *,
        timestamp: float | None = None,
        author: str | None = None,
        source: str | None = None,
    ) -> None: ...

    def link_objects(
        self,
        source: OntologyObject,
        link_type: str,
        target: OntologyObject,
        *,
        timestamp: float | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None: ...

    def unlink_objects(
        self,
        source: OntologyObject,
        link_type: str,
        target: OntologyObject,
        *,
        timestamp: float | None = None,
    ) -> None: ...


__all__ = ["ManagedObjectMutationPort"]
