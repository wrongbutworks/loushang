"""本体管理器——统一入口，协调类型注册、对象创建和查询."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from loushang.ontology.core.link_type import Cardinality, LinkType
from loushang.ontology.core.object import OntologyObject
from loushang.ontology.core.object_type import ObjectType
from loushang.ontology.core.property import Property
from loushang.ontology.core.store import ObjectStore
from loushang.ontology.query.builder import QueryBuilder
from loushang.ontology.schema import (
    CompiledOntologySchema,
    LinkCardinality,
    LinkTypeDefinition,
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    SchemaVersion,
    ValueType,
)

_PYTHON_VALUE_TYPES: dict[type, ValueType] = {
    str: ValueType.STRING,
    int: ValueType.INTEGER,
    float: ValueType.NUMBER,
    bool: ValueType.BOOLEAN,
    datetime: ValueType.DATETIME,
    dict: ValueType.JSON,
    list: ValueType.JSON,
}

_CARDINALITIES = {
    Cardinality.ONE_TO_ONE: LinkCardinality.ONE_TO_ONE,
    Cardinality.ONE_TO_MANY: LinkCardinality.ONE_TO_MANY,
    Cardinality.MANY_TO_ONE: LinkCardinality.MANY_TO_ONE,
    Cardinality.MANY_TO_MANY: LinkCardinality.MANY_TO_MANY,
}


class Ontology:
    """本体管理器——Palantir 式动态本体的统一入口.

    用法::

        onto = Ontology()

        # 1. 定义类型
        onto.define_object_type("Person", properties=[
            Property("name", str, required=True, indexed=True),
            Property("age", int),
        ])
        onto.define_object_type("Company", properties=[
            Property("name", str, required=True, indexed=True),
        ])
        onto.define_link_type("works_for", "Person", "Company")

        # 2. 创建对象
        alice = onto.create("Person", name="Alice", age=30)
        acme = onto.create("Company", name="ACME")

        # 3. 建立关系
        onto.link(alice, "works_for", acme)

        # 4. 查询
        results = onto.query().start_from(alice).follow("works_for").execute()
    """

    def __init__(
        self,
        *,
        package_id: str = "loushang.dynamic",
        namespace: str = "urn:loushang:ontology:dynamic",
        schema_version: SchemaVersion | str = "1.0.0",
    ) -> None:
        self._store = ObjectStore()
        self._package_id = package_id
        self._namespace = namespace
        self._schema_version = schema_version
        self._defined_object_types: list[ObjectType] = []
        self._defined_link_types: list[LinkType] = []
        self._compiled_schema: CompiledOntologySchema | None = None

    # ------------------------------------------------------------------
    # 类型定义
    # ------------------------------------------------------------------

    def define_object_type(
        self,
        name: str,
        properties: list[Property] | None = None,
        parent_types: list[str] | None = None,
        abstract: bool = False,
        icon: str | None = None,
        description: str = "",
        display_name_property: str | None = None,
    ) -> ObjectType:
        """注册对象类型."""
        self._require_mutable_schema()
        obj_type = ObjectType(
            name=name,
            properties=properties or [],
            parent_types=parent_types or [],
            abstract=abstract,
            icon=icon,
            description=description,
            display_name_property=display_name_property,
        )
        self._store.register_object_type(obj_type)
        self._defined_object_types.append(obj_type)
        return obj_type

    def define_link_type(
        self,
        name: str,
        source_type: str,
        target_type: str,
        **kwargs: Any,
    ) -> LinkType:
        """注册关系类型."""
        self._require_mutable_schema()
        link_type = LinkType(name=name, source_type=source_type, target_type=target_type, **kwargs)
        self._store.register_link_type(link_type)
        self._defined_link_types.append(link_type)
        return link_type

    def get_object_type(self, name: str) -> ObjectType | None:
        return self._store.get_object_type(name)

    def get_link_type(self, name: str) -> LinkType | None:
        return self._store.get_link_type(name)

    @property
    def compiled_schema(self) -> CompiledOntologySchema | None:
        """The frozen schema snapshot, or ``None`` while definitions are open."""

        return self._compiled_schema

    def compile_schema(self) -> CompiledOntologySchema:
        """Compile the current definitions without changing facade state."""

        return OntologyCompiler().compile(
            OntologyPackageDraft(
                package_id=self._package_id,
                namespace=self._namespace,
                version=self._schema_version,
                object_types=[
                    _object_type_definition(object_type)
                    for object_type in self._defined_object_types
                ],
                link_types=[
                    _link_type_definition(link_type)
                    for link_type in self._defined_link_types
                ],
            )
        )

    def freeze_schema(self) -> CompiledOntologySchema:
        """Compile and bind the schema exactly once before runtime writes."""

        if self._compiled_schema is not None:
            return self._compiled_schema
        compiled = self.compile_schema()
        self._store.bind_schema(compiled)
        self._compiled_schema = compiled
        return compiled

    def _require_mutable_schema(self) -> None:
        if self._compiled_schema is not None:
            raise RuntimeError("Ontology schema is frozen; type definitions cannot be changed")

    # ------------------------------------------------------------------
    # 对象生命周期
    # ------------------------------------------------------------------

    def create(
        self,
        object_type: str,
        obj_id: UUID | None = None,
        **properties: Any,
    ) -> OntologyObject:
        """创建对象实例."""
        # Preserve the historical unknown-type error without freezing an empty
        # or incomplete schema after a failed create attempt.
        if self._store.get_object_type(object_type) is None:
            raise ValueError(f"Object type '{object_type}' not registered")
        self.freeze_schema()
        return self._store.create(object_type, properties=properties, obj_id=obj_id)

    def get(self, obj_id: UUID) -> OntologyObject | None:
        """按 UUID 获取对象."""
        return self._store.get(obj_id)

    def delete(self, obj_id: UUID) -> bool:
        """删除对象."""
        return self._store.delete(obj_id)

    # ------------------------------------------------------------------
    # 关系操作
    # ------------------------------------------------------------------

    def link(
        self,
        source: OntologyObject,
        link_type: str,
        target: OntologyObject,
        **kwargs: Any,
    ) -> None:
        """建立关系."""
        self._store.link(source.id, link_type, target.id, **kwargs)

    def unlink(
        self,
        source: OntologyObject,
        link_type: str,
        target: OntologyObject,
        **kwargs: Any,
    ) -> None:
        """删除关系."""
        self._store.unlink(source.id, link_type, target.id, **kwargs)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def query(self) -> QueryBuilder:
        """开始构建查询."""
        return QueryBuilder(self._store)

    def find_by_property(
        self,
        property_name: str,
        value: Any,
        object_type: str | None = None,
    ) -> list[OntologyObject]:
        """按属性值查找."""
        return self._store.find_by_property(property_name, value, object_type)

    def find_by_type(self, object_type: str) -> list[OntologyObject]:
        """按类型查找所有对象."""
        return self._store.get_by_type(object_type)

    def all_objects(self) -> list[OntologyObject]:
        return self._store.all_objects()

    def count(self) -> int:
        return self._store.count()


def _object_type_definition(object_type: ObjectType) -> ObjectTypeDefinition:
    return ObjectTypeDefinition(
        name=object_type.name,
        properties=[_property_definition(prop) for prop in object_type.properties],
        parent_types=object_type.parent_types,
        abstract=object_type.abstract,
        icon=object_type.icon,
        description=object_type.description,
        display_name_property=object_type.display_name_property,
    )


def _property_definition(prop: Property) -> PropertyDefinition:
    value_type: ValueType | object
    if isinstance(prop.data_type, type):
        value_type = _PYTHON_VALUE_TYPES.get(prop.data_type, prop.data_type)
    else:
        value_type = prop.data_type
    return PropertyDefinition(
        name=prop.name,
        value_type=value_type,
        required=prop.required,
        unique=prop.unique,
        indexed=prop.indexed,
        default=prop.default,
        description=prop.description,
    )


def _link_type_definition(link_type: LinkType) -> LinkTypeDefinition:
    return LinkTypeDefinition(
        name=link_type.name,
        source_type=link_type.source_type,
        target_type=link_type.target_type,
        cardinality=_CARDINALITIES.get(link_type.cardinality, link_type.cardinality),
        required=link_type.required,
        inverse_name=link_type.inverse_name,
        temporal=link_type.temporal,
        description=link_type.description,
    )
