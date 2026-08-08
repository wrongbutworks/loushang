"""对象存储——内存中的对象图存储，支持索引和时序查询."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from loushang.ontology.core.link_type import LinkType
from loushang.ontology.core.object import LinkVersion, OntologyObject
from loushang.ontology.core.object_type import ObjectType
from loushang.ontology.core.schema_runtime import (
    PropertyValidators,
    materialize_compiled_schema,
)

if TYPE_CHECKING:
    from loushang.ontology.schema import CompiledOntologySchema


class ObjectStore:
    """内存对象存储，管理所有本体实例.

    功能：
    - 按 UUID 和类型索引对象
    - 维护关系双向索引（incoming/outgoing）
    - 支持按属性值查询
    - 支持时序快照查询

    注：当前为内存实现，生产环境可替换为图数据库后端（Neo4j, JanusGraph 等）。
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

    # ------------------------------------------------------------------
    # 类型注册
    # ------------------------------------------------------------------

    @property
    def schema(self) -> CompiledOntologySchema | None:
        """Return the compiled schema bound to this store, if any."""

        return self._schema

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

        # 校验并填充默认值
        validated = type_def.validate_properties(properties or {})

        obj = OntologyObject(object_type=object_type, obj_id=obj_id)
        for name, value in validated.items():
            obj.set(name, value)

        self._objects[obj.id] = obj
        self._type_index[object_type].add(obj.id)

        # 更新属性索引
        for prop in type_def.properties:
            if prop.indexed and prop.name in validated:
                self._property_index.setdefault(prop.name, {}).setdefault(validated[prop.name], set()).add(obj.id)

        return obj

    def get(self, obj_id: UUID) -> OntologyObject | None:
        """按 UUID 获取对象."""
        return self._objects.get(obj_id)

    def get_by_type(self, object_type: str) -> list[OntologyObject]:
        """按类型获取所有对象."""
        return [self._objects[uid] for uid in self._type_index.get(object_type, [])]

    def delete(self, obj_id: UUID) -> bool:
        """删除对象（从索引中移除，保留关系历史）."""
        obj = self._objects.pop(obj_id, None)
        if obj is None:
            return False
        self._type_index[obj.object_type].discard(obj_id)
        # 清理属性索引
        type_def = self._object_types.get(obj.object_type)
        if type_def:
            for prop in type_def.properties:
                if prop.indexed:
                    idx = self._property_index.get(prop.name, {})
                    for value_set in idx.values():
                        value_set.discard(obj_id)
        return True

    # ------------------------------------------------------------------
    # 关系管理（维护双向索引）
    # ------------------------------------------------------------------

    def link(
        self,
        source_id: UUID,
        link_type: str,
        target_id: UUID,
        timestamp: float | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """建立关系，并维护双向索引."""
        link_def = self._link_types.get(link_type)
        if link_def is None:
            raise ValueError(f"Link type '{link_type}' not registered")

        source = self._objects.get(source_id)
        target = self._objects.get(target_id)
        if source is None or target is None:
            raise ValueError("Source or target object not found")

        # 校验类型
        if source.object_type != link_def.source_type:
            raise TypeError(
                f"Link '{link_type}' source must be {link_def.source_type}, got {source.object_type}"
            )
        if target.object_type != link_def.target_type:
            raise TypeError(
                f"Link '{link_type}' target must be {link_def.target_type}, got {target.object_type}"
            )

        source.link(link_type, target, timestamp=timestamp, properties=properties)

        # 维护 target 的 incoming 索引
        import time

        ts = timestamp if timestamp is not None else time.time()
        incoming = LinkVersion(target_id=source_id, timestamp=ts, active=True, properties=properties or {})
        target._incoming.setdefault(link_type, []).append(incoming)

    def unlink(self, source_id: UUID, link_type: str, target_id: UUID, timestamp: float | None = None) -> None:
        """删除关系."""
        source = self._objects.get(source_id)
        target = self._objects.get(target_id)
        if source is None or target is None:
            return

        source.unlink(link_type, target, timestamp=timestamp)

        # 标记 target 的 incoming 失效
        import time

        ts = timestamp if timestamp is not None else time.time()
        for v in reversed(target._incoming.get(link_type, [])):
            if v.target_id == source_id and v.active:
                v.active = False
                v.timestamp = ts
                break

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
        if property_name in self._property_index:
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
