"""对象存储——内存中的对象图存储，支持索引和时序查询."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from loushang.foundation.json import JSONValue, require_json_mapping
from loushang.ontology.core._value_codec import encode_store_value, encoded_mapping
from loushang.ontology.core.constraints import IntegrityViolation
from loushang.ontology.core.link_type import LinkType
from loushang.ontology.core.object import LinkVersion, OntologyObject
from loushang.ontology.core.object_type import ObjectType
from loushang.ontology.core.projection import ProjectionState, StoreMutation
from loushang.ontology.core.property import Property
from loushang.ontology.core.schema_runtime import (
    PropertyValidators,
    materialize_compiled_schema,
)

if TYPE_CHECKING:
    from loushang.ontology.schema import CompiledOntologySchema


_MISSING = object()


@dataclass(frozen=True, slots=True)
class _PendingMutation:
    kind: str
    payload: dict[str, JSONValue]
    timestamp: float


class ObjectStore:
    """内存对象存储，管理所有本体实例.

    功能：
    - 按 UUID 和类型索引对象
    - 维护关系双向索引（incoming/outgoing）
    - 支持按属性值查询
    - 支持时序快照查询

    This is the deterministic Memory reference implementation. Durable Wave 1
    execution uses the sibling SQLite adapter through the same Store port.
    """

    def __init__(self) -> None:
        # uuid -> OntologyObject
        self._objects: dict[UUID, OntologyObject] = {}
        # type_name -> set[UUID]
        self._type_index: dict[str, set[UUID]] = {}
        # property_name -> {value -> set[UUID]}  （仅对 indexed=True 的属性）
        self._property_index: dict[str, dict[Any, set[UUID]]] = {}
        # 注册的对象类型和关系类型
        self._object_types: dict[str, ObjectType] = {}
        self._link_types: dict[str, LinkType] = {}
        # The immutable semantic contract bound by the compatibility facade.
        self._schema: CompiledOntologySchema | None = None
        # Operational recovery journal and synchronous materialized projection.
        self._watermark = 0
        self._mutations: list[StoreMutation] = []
        self._projected_watermark = 0
        self._projection_version = 1
        self._projection_built_at = time.time()
        # (declaring object type, property name) -> value -> object id.
        self._unique_index: dict[tuple[str, str], dict[Any, UUID]] = {}

    # ------------------------------------------------------------------
    # 类型注册
    # ------------------------------------------------------------------

    @property
    def schema(self) -> CompiledOntologySchema | None:
        """Return the compiled schema bound to this store, if any."""

        return self._schema

    @property
    def current_watermark(self) -> int:
        """Last committed authority mutation sequence."""

        return self._watermark

    @property
    def projection_state(self) -> ProjectionState:
        """Return a snapshot of materialized projection freshness."""

        return ProjectionState(
            schema_version=str(self._schema.version) if self._schema is not None else None,
            projection_version=self._projection_version,
            source_watermark=self._watermark,
            projected_watermark=self._projected_watermark,
            built_at=self._projection_built_at,
        )

    def read_mutations(self, *, after_sequence: int = 0) -> tuple[StoreMutation, ...]:
        """Read committed operational mutations after ``after_sequence``."""

        return tuple(item for item in self._mutations if item.sequence > after_sequence)

    def bind_schema(
        self,
        schema: CompiledOntologySchema,
        *,
        property_validators: PropertyValidators | None = None,
    ) -> None:
        """Atomically materialize and bind one immutable schema snapshot."""

        if self._schema is schema:
            return
        if self._schema is not None:
            raise RuntimeError("ObjectStore already has a compiled schema")
        if self._objects or self._object_types or self._link_types:
            raise RuntimeError("Cannot bind a compiled schema to an initialized ObjectStore")

        materialized = materialize_compiled_schema(
            schema,
            property_validators=property_validators,
        )
        self._object_types = {
            object_type.name: object_type for object_type in materialized.object_types
        }
        self._link_types = {
            link_type.name: link_type for link_type in materialized.link_types
        }
        self._type_index = {object_type.name: set() for object_type in materialized.object_types}
        self._schema = schema
        self._projection_built_at = time.time()

    def register_object_type(self, obj_type: ObjectType) -> None:
        """注册对象类型."""
        if self._schema is not None:
            raise RuntimeError("ObjectStore schema is frozen; object types cannot be registered")
        self._object_types[obj_type.name] = obj_type
        self._type_index.setdefault(obj_type.name, set())

    def register_link_type(self, link_type: LinkType) -> None:
        """注册关系类型，并更新相关对象类型的关系集合."""
        if self._schema is not None:
            raise RuntimeError("ObjectStore schema is frozen; link types cannot be registered")
        self._link_types[link_type.name] = link_type
        # 更新源类型的 outgoing
        src_type = self._object_types.get(link_type.source_type)
        if src_type:
            src_type.add_outgoing_link_type(link_type.name)
        # 更新目标类型的 incoming
        tgt_type = self._object_types.get(link_type.target_type)
        if tgt_type:
            tgt_type.add_incoming_link_type(link_type.name)

    def get_object_type(self, name: str) -> ObjectType | None:
        return self._object_types.get(name)

    def get_link_type(self, name: str) -> LinkType | None:
        return self._link_types.get(name)

    # ------------------------------------------------------------------
    # 对象 CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        object_type: str,
        properties: dict[str, Any] | None = None,
        obj_id: UUID | None = None,
    ) -> OntologyObject:
        """创建对象实例."""
        type_def = self._object_types.get(object_type)
        if type_def is None:
            raise ValueError(f"Object type '{object_type}' not registered")
        if type_def.abstract:
            raise ValueError(f"Object type '{object_type}' is abstract and cannot be instantiated")

        # 校验并填充默认值
        validated = type_def.validate_properties(properties or {}, self._object_types)

        declared_properties = self._resolved_property_declarations(type_def)
        indexed_properties = {
            name: (owner, prop)
            for name, (owner, prop) in declared_properties.items()
            if (prop.indexed or prop.unique) and name in validated
        }
        for name, (_, prop) in indexed_properties.items():
            _require_indexable_value(prop.name, validated[name])

        obj = OntologyObject(object_type=object_type, obj_id=obj_id)
        if obj.id in self._objects:
            raise ValueError(f"Ontology object {obj.id} already exists")
        for name, (owner, prop) in indexed_properties.items():
            if prop.unique:
                self._require_unique_available(owner, prop, validated[name], obj.id)

        ts = time.time()
        pending = _PendingMutation(
            kind="create_object",
            payload={
                "object_id": str(obj.id),
                "object_type": object_type,
                "properties": encoded_mapping(validated),
                "timestamp": ts,
            },
            timestamp=ts,
        )

        def apply() -> None:
            for name, value in validated.items():
                obj._set_unchecked(name, value, timestamp=ts)
            self._objects[obj.id] = obj
            self._type_index[object_type].add(obj.id)
            for name, (owner, prop) in indexed_properties.items():
                value = validated[name]
                self._property_index.setdefault(name, {}).setdefault(value, set()).add(obj.id)
                if prop.unique:
                    self._unique_index.setdefault((owner, name), {})[value] = obj.id
            obj._bind_mutation_port(self)

        self._commit_mutation(pending, apply)

        return obj

    def set_property(
        self,
        obj: OntologyObject,
        name: str,
        value: Any,
        *,
        timestamp: float | None = None,
        author: str | None = None,
        source: str | None = None,
    ) -> None:
        """Validate and update one property on an object owned by this store."""

        self._require_owned_object(obj)
        _require_optional_text("author", author)
        _require_optional_text("source", source)
        type_def = self._object_types[obj.object_type]
        declaration = self._resolved_property_declarations(type_def).get(name)
        owner, prop = declaration if declaration is not None else (obj.object_type, None)
        if prop is not None:
            prop.validate(value)

        previous_versions = obj.history(name)
        previous_value = previous_versions[-1].value if previous_versions else _MISSING
        if prop is not None and (prop.indexed or prop.unique):
            _require_indexable_value(prop.name, value)
        if prop is not None and prop.unique:
            self._require_unique_available(owner, prop, value, obj.id)

        ts = _mutation_timestamp(timestamp)
        pending = _PendingMutation(
            kind="set_property",
            payload={
                "object_id": str(obj.id),
                "object_type": obj.object_type,
                "property": name,
                "value": encode_store_value(value),
                "timestamp": ts,
                "author": author,
                "source": source,
            },
            timestamp=ts,
        )

        def apply() -> None:
            obj._set_unchecked(
                name,
                value,
                timestamp=ts,
                author=author,
                source=source,
            )
            if prop is not None and (prop.indexed or prop.unique):
                index = self._property_index.setdefault(prop.name, {})
                if previous_value is not _MISSING:
                    previous_ids = index.get(previous_value)
                    if previous_ids is not None:
                        previous_ids.discard(obj.id)
                        if not previous_ids:
                            del index[previous_value]
                index.setdefault(value, set()).add(obj.id)
            if prop is not None and prop.unique:
                unique = self._unique_index.setdefault((owner, prop.name), {})
                if previous_value is not _MISSING and unique.get(previous_value) == obj.id:
                    del unique[previous_value]
                unique[value] = obj.id

        self._commit_mutation(pending, apply)

    def get(self, obj_id: UUID) -> OntologyObject | None:
        """按 UUID 获取对象."""
        return self._objects.get(obj_id)

    def get_by_type(self, object_type: str) -> list[OntologyObject]:
        """按类型获取所有对象."""
        return [obj for obj in self._objects.values() if obj.object_type == object_type]

    def delete(self, obj_id: UUID) -> bool:
        """Delete an unreferenced object and its materialized indexes."""
        obj = self._objects.get(obj_id)
        if obj is None:
            return False
        if any(obj.get_links(name) for name in obj._outgoing) or any(
            obj.get_incoming(name) for name in obj._incoming
        ):
            raise ValueError(f"Cannot delete ontology object {obj_id} with an active link")

        type_def = self._object_types.get(obj.object_type)
        declarations = self._resolved_property_declarations(type_def) if type_def else {}
        ts = time.time()
        pending = _PendingMutation(
            kind="delete_object",
            payload={
                "object_id": str(obj_id),
                "object_type": obj.object_type,
                "timestamp": ts,
            },
            timestamp=ts,
        )

        def apply() -> None:
            del self._objects[obj_id]
            self._type_index[obj.object_type].discard(obj_id)
            for name, (owner, prop) in declarations.items():
                if not (prop.indexed or prop.unique):
                    continue
                value = obj.get(name)
                idx = self._property_index.get(name, {})
                ids = idx.get(value)
                if ids is not None:
                    ids.discard(obj_id)
                    if not ids:
                        del idx[value]
                if prop.unique:
                    unique = self._unique_index.get((owner, name), {})
                    if unique.get(value) == obj_id:
                        del unique[value]

        self._commit_mutation(pending, apply)
        return True

    # ------------------------------------------------------------------
    # 关系管理（维护双向索引）
    # ------------------------------------------------------------------

    def link_objects(
        self,
        source: OntologyObject,
        link_type: str,
        target: OntologyObject,
        *,
        timestamp: float | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Establish a relation between two objects owned by this store."""

        self._require_owned_object(source)
        self._require_owned_object(target)
        self._link_owned(
            source,
            link_type,
            target,
            timestamp=timestamp,
            properties=properties,
        )

    def link(
        self,
        source_id: UUID,
        link_type: str,
        target_id: UUID,
        timestamp: float | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """建立关系，并维护双向索引."""
        source = self._objects.get(source_id)
        target = self._objects.get(target_id)
        if source is None or target is None:
            raise ValueError("Source or target object not found")

        self._link_owned(
            source,
            link_type,
            target,
            timestamp=timestamp,
            properties=properties,
        )

    def _link_owned(
        self,
        source: OntologyObject,
        link_type: str,
        target: OntologyObject,
        *,
        timestamp: float | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        link_def = self._link_types.get(link_type)
        if link_def is None:
            raise ValueError(f"Link type '{link_type}' not registered")

        # 校验类型
        if source.object_type != link_def.source_type:
            raise TypeError(
                f"Link '{link_type}' source must be {link_def.source_type}, got {source.object_type}"
            )
        if target.object_type != link_def.target_type:
            raise TypeError(
                f"Link '{link_type}' target must be {link_def.target_type}, got {target.object_type}"
            )

        _validate_link_cardinality(link_def, source, target)

        ts = _mutation_timestamp(timestamp)
        safe_properties = require_json_mapping(
            properties or {},
            name=f"link '{link_type}' properties",
        )
        pending = _PendingMutation(
            kind="link_objects",
            payload={
                "source_id": str(source.id),
                "target_id": str(target.id),
                "link_type": link_type,
                "timestamp": ts,
                "properties": safe_properties,
            },
            timestamp=ts,
        )

        def apply() -> None:
            source._link_unchecked(
                link_type,
                target,
                timestamp=ts,
                properties=safe_properties,
            )
            target._incoming.setdefault(link_type, []).append(
                LinkVersion(
                    target_id=source.id,
                    timestamp=ts,
                    active=True,
                    properties=safe_properties,
                )
            )

        self._commit_mutation(pending, apply)

    def unlink_objects(
        self,
        source: OntologyObject,
        link_type: str,
        target: OntologyObject,
        *,
        timestamp: float | None = None,
    ) -> None:
        """Remove a relation between two objects owned by this store."""

        self._require_owned_object(source)
        self._require_owned_object(target)
        self._unlink_owned(source, link_type, target, timestamp=timestamp)

    def unlink(
        self,
        source_id: UUID,
        link_type: str,
        target_id: UUID,
        timestamp: float | None = None,
    ) -> None:
        """删除关系."""
        source = self._objects.get(source_id)
        target = self._objects.get(target_id)
        if source is None or target is None:
            return

        self._unlink_owned(source, link_type, target, timestamp=timestamp)

    def _unlink_owned(
        self,
        source: OntologyObject,
        link_type: str,
        target: OntologyObject,
        *,
        timestamp: float | None = None,
    ) -> None:
        link_def = self._link_types.get(link_type)
        if link_def is None:
            raise ValueError(f"Link type '{link_type}' not registered")
        if source.object_type != link_def.source_type:
            raise TypeError(
                f"Link '{link_type}' source must be {link_def.source_type}, "
                f"got {source.object_type}"
            )
        if target.object_type != link_def.target_type:
            raise TypeError(
                f"Link '{link_type}' target must be {link_def.target_type}, "
                f"got {target.object_type}"
            )

        ts = _mutation_timestamp(timestamp)
        pending = _PendingMutation(
            kind="unlink_objects",
            payload={
                "source_id": str(source.id),
                "target_id": str(target.id),
                "link_type": link_type,
                "timestamp": ts,
            },
            timestamp=ts,
        )

        def apply() -> None:
            source._unlink_unchecked(link_type, target, timestamp=ts)
            # Incoming also receives a tombstone with identical temporal semantics.
            target._incoming.setdefault(link_type, []).append(
                LinkVersion(target_id=source.id, timestamp=ts, active=False)
            )

        self._commit_mutation(pending, apply)

    def _require_owned_object(self, obj: OntologyObject) -> None:
        if self._objects.get(obj.id) is not obj:
            raise ValueError(f"Ontology object {obj.id} is not managed by this store")

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def find_by_property(
        self,
        property_name: str,
        value: Any,
        object_type: str | None = None,
    ) -> list[OntologyObject]:
        """按属性值查找对象（利用索引加速）."""
        # 优先使用索引
        if property_name in self._property_index and self._can_use_property_index(
            property_name,
            object_type,
        ):
            ids = self._property_index[property_name].get(value, set())
            if object_type:
                type_ids = self._type_index.get(object_type, set())
                ids = ids & type_ids
            return [self._objects[uid] for uid in ids]

        # 回退到全表扫描
        result: list[OntologyObject] = []
        candidates = (
            [self._objects[uid] for uid in self._type_index.get(object_type, [])]
            if object_type
            else list(self._objects.values())
        )
        for obj in candidates:
            if obj.get(property_name) == value:
                result.append(obj)
        return result

    def _can_use_property_index(
        self,
        property_name: str,
        object_type: str | None,
    ) -> bool:
        candidates = (
            [self._object_types[object_type]]
            if object_type is not None and object_type in self._object_types
            else list(self._object_types.values())
        )
        declarations = [
            declaration
            for candidate in candidates
            if (
                declaration := self._resolved_property_declarations(candidate).get(
                    property_name
                )
            )
            is not None
        ]
        return bool(declarations) and all(
            prop.indexed or prop.unique for _, prop in declarations
        )

    def find_neighbors(
        self,
        obj_id: UUID,
        link_type: str,
        direction: str = "outgoing",
        as_of: float | None = None,
        active_only: bool = True,
    ) -> list[OntologyObject]:
        """查找邻居对象（图遍历基础）."""
        obj = self._objects.get(obj_id)
        if obj is None:
            return []

        if direction == "outgoing":
            links = obj.get_links(link_type, as_of=as_of, active_only=active_only)
        elif direction == "incoming":
            links = obj.get_incoming(link_type, as_of=as_of, active_only=active_only)
        else:
            raise ValueError("direction must be 'outgoing' or 'incoming'")

        return [self._objects[link.target_id] for link in links if link.target_id in self._objects]

    def all_objects(self) -> list[OntologyObject]:
        return list(self._objects.values())

    def count(self) -> int:
        return len(self._objects)

    def validate_integrity(self) -> tuple[IntegrityViolation, ...]:
        """Validate the complete current snapshot without mutating it."""

        violations: list[IntegrityViolation] = []
        unique_values: dict[tuple[str, str], dict[Any, UUID]] = {}
        incoming_counts: dict[tuple[str, UUID], set[UUID]] = {}

        for obj in sorted(self._objects.values(), key=lambda item: str(item.id)):
            type_def = self._object_types.get(obj.object_type)
            if type_def is None:
                violations.append(
                    IntegrityViolation(
                        "unknown_object_type",
                        obj.id,
                        f"objects.{obj.id}.object_type",
                        f"object type '{obj.object_type}' is not registered",
                    )
                )
                continue
            for name, (owner, prop) in self._resolved_property_declarations(type_def).items():
                history = obj.history(name)
                if prop.required and (not history or history[-1].value is None):
                    violations.append(
                        IntegrityViolation(
                            "required_property_missing",
                            obj.id,
                            f"objects.{obj.id}.properties.{name}",
                            f"required property '{name}' is missing",
                        )
                    )
                    continue
                if not history:
                    continue
                value = history[-1].value
                try:
                    prop.validate(value)
                except ValueError as exc:
                    violations.append(
                        IntegrityViolation(
                            "property_type_invalid",
                            obj.id,
                            f"objects.{obj.id}.properties.{name}",
                            str(exc),
                        )
                    )
                if prop.unique:
                    values = unique_values.setdefault((owner, name), {})
                    other = values.get(value)
                    if other is not None and other != obj.id:
                        violations.append(
                            IntegrityViolation(
                                "unique_property_conflict",
                                obj.id,
                                f"objects.{obj.id}.properties.{name}",
                                f"unique property '{name}' conflicts with object {other}",
                            )
                        )
                    values[value] = obj.id

            for link_name in sorted(obj._outgoing):
                link_def = self._link_types.get(link_name)
                active_links = obj.get_links(link_name)
                if link_def is None:
                    violations.append(
                        IntegrityViolation(
                            "unknown_link_type",
                            obj.id,
                            f"objects.{obj.id}.links.{link_name}",
                            f"link type '{link_name}' is not registered",
                        )
                    )
                    continue
                if obj.object_type != link_def.source_type:
                    violations.append(
                        IntegrityViolation(
                            "link_source_type_invalid",
                            obj.id,
                            f"objects.{obj.id}.links.{link_name}",
                            f"link source must be '{link_def.source_type}'",
                        )
                    )
                if not link_def.allows_multiple_targets() and len(active_links) > 1:
                    violations.append(
                        IntegrityViolation(
                            "link_target_cardinality_invalid",
                            obj.id,
                            f"objects.{obj.id}.links.{link_name}",
                            f"link '{link_name}' allows only one target",
                        )
                    )
                for link in active_links:
                    target = self._objects.get(link.target_id)
                    if target is None:
                        violations.append(
                            IntegrityViolation(
                                "link_reference_missing",
                                obj.id,
                                f"objects.{obj.id}.links.{link_name}",
                                f"link target {link.target_id} does not exist",
                            )
                        )
                        continue
                    if target.object_type != link_def.target_type:
                        violations.append(
                            IntegrityViolation(
                                "link_target_type_invalid",
                                obj.id,
                                f"objects.{obj.id}.links.{link_name}",
                                f"link target must be '{link_def.target_type}'",
                            )
                        )
                    incoming_counts.setdefault((link_name, target.id), set()).add(obj.id)

        for link_name, link_def in sorted(self._link_types.items()):
            source_objects = self.get_by_type(link_def.source_type)
            if link_def.required:
                for source in source_objects:
                    if not source.get_links(link_name):
                        violations.append(
                            IntegrityViolation(
                                "required_link_missing",
                                source.id,
                                f"objects.{source.id}.links.{link_name}",
                                f"required link '{link_name}' is missing",
                            )
                        )
            if not link_def.allows_multiple_sources():
                for (candidate_name, target_id), source_ids in incoming_counts.items():
                    if candidate_name == link_name and len(source_ids) > 1:
                        violations.append(
                            IntegrityViolation(
                                "link_source_cardinality_invalid",
                                target_id,
                                f"objects.{target_id}.incoming.{link_name}",
                                f"link '{link_name}' allows only one source",
                            )
                        )

        return tuple(
            sorted(
                violations,
                key=lambda item: (item.path, item.code, item.message),
            )
        )

    # ------------------------------------------------------------------
    # Operational journal and rebuildable projections
    # ------------------------------------------------------------------

    def rebuild_projections(self) -> ProjectionState:
        """Rebuild indexes and incoming edges from authoritative object history."""

        self._rebuild_memory_projections()
        self._projection_version += 1
        self._projected_watermark = self._watermark
        self._projection_built_at = time.time()
        return self.projection_state

    def _rebuild_memory_projections(self) -> None:
        self._type_index = {name: set() for name in self._object_types}
        self._property_index = {}
        self._unique_index = {}

        for obj in self._objects.values():
            self._type_index.setdefault(obj.object_type, set()).add(obj.id)
            type_def = self._object_types.get(obj.object_type)
            if type_def is None:
                continue
            for name, (owner, prop) in self._resolved_property_declarations(type_def).items():
                if not (prop.indexed or prop.unique):
                    continue
                value = obj.get(name)
                if value is None:
                    continue
                _require_indexable_value(name, value)
                self._property_index.setdefault(name, {}).setdefault(value, set()).add(obj.id)
                if prop.unique:
                    self._require_unique_available(owner, prop, value, obj.id)
                    self._unique_index.setdefault((owner, name), {})[value] = obj.id

        for obj in self._objects.values():
            obj._incoming = {}
        for source in self._objects.values():
            for link_name, versions in source._outgoing.items():
                for version in versions:
                    target = self._objects.get(version.target_id)
                    if target is None:
                        continue
                    target._incoming.setdefault(link_name, []).append(
                        LinkVersion(
                            target_id=source.id,
                            timestamp=version.timestamp,
                            active=version.active,
                            properties=dict(version.properties),
                        )
                    )

    def _commit_mutation(
        self,
        pending: _PendingMutation,
        apply: Callable[[], None],
    ) -> None:
        """Commit one validated mutation; persistent stores override this hook."""

        apply()
        self._append_committed_mutation(pending)

    def _append_committed_mutation(
        self,
        pending: _PendingMutation,
        *,
        sequence: int | None = None,
    ) -> StoreMutation:
        next_sequence = self._watermark + 1 if sequence is None else sequence
        if next_sequence != self._watermark + 1:
            raise RuntimeError("Ontology mutation sequence is not contiguous")
        record = StoreMutation(
            sequence=next_sequence,
            kind=pending.kind,
            payload=dict(pending.payload),
            timestamp=pending.timestamp,
        )
        self._mutations.append(record)
        self._watermark = next_sequence
        self._projected_watermark = next_sequence
        self._projection_built_at = time.time()
        return record

    def _resolved_property_declarations(
        self,
        object_type: ObjectType,
    ) -> dict[str, tuple[str, Property]]:
        """Resolve property ownership so inherited unique keys keep their identity."""

        resolved: dict[str, tuple[str, Property]] = {}
        visiting: set[str] = set()

        def visit(current: ObjectType) -> None:
            if current.name in visiting:
                return
            visiting.add(current.name)
            for parent_name in current.parent_types:
                parent = self._object_types.get(parent_name)
                if parent is not None:
                    visit(parent)
            visiting.remove(current.name)
            for prop in current.properties:
                resolved[prop.name] = (current.name, prop)

        visit(object_type)
        return resolved

    def _require_unique_available(
        self,
        owner: str,
        prop: Property,
        value: Any,
        object_id: UUID,
    ) -> None:
        existing = self._unique_index.get((owner, prop.name), {}).get(value)
        if existing is not None and existing != object_id:
            raise ValueError(
                f"Property '{prop.name}' unique constraint conflicts with object {existing}"
            )


def _validate_link_cardinality(
    link_def: LinkType,
    source: OntologyObject,
    target: OntologyObject,
) -> None:
    if not link_def.allows_multiple_targets():
        active_targets = source.get_links(link_def.name)
        if any(link.target_id != target.id for link in active_targets):
            raise ValueError(
                f"Link '{link_def.name}' cardinality allows only one target per source"
            )
    if not link_def.allows_multiple_sources():
        active_sources = target.get_incoming(link_def.name)
        if any(link.target_id != source.id for link in active_sources):
            raise ValueError(
                f"Link '{link_def.name}' cardinality allows only one source per target"
            )


def _require_indexable_value(property_name: str, value: Any) -> None:
    try:
        hash(value)
    except TypeError as exc:
        raise ValueError(
            f"Indexed property '{property_name}' requires a hashable value"
        ) from exc


def _mutation_timestamp(value: float | None) -> float:
    if value is None:
        return time.time()
    if type(value) not in {int, float}:
        raise ValueError("Ontology mutation timestamp must be a finite number")
    try:
        timestamp = float(value)
    except OverflowError as exc:
        raise ValueError("Ontology mutation timestamp must be a finite number") from exc
    if not math.isfinite(timestamp):
        raise ValueError("Ontology mutation timestamp must be a finite number")
    return timestamp


def _require_optional_text(name: str, value: object) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"Ontology mutation {name} must be a string or None")
