"""本体管理器——统一入口，协调类型注册、对象创建和查询."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from loushang.ontology.core.link_type import LinkType
from loushang.ontology.core.object import OntologyObject
from loushang.ontology.core.object_type import ObjectType
from loushang.ontology.core.property import Property
from loushang.ontology.core.store import ObjectStore
from loushang.ontology.query.builder import QueryBuilder


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

    def __init__(self) -> None:
        self._store = ObjectStore()

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
        return obj_type

    def define_link_type(
        self,
        name: str,
        source_type: str,
        target_type: str,
        **kwargs: Any,
    ) -> LinkType:
        """注册关系类型."""
        link_type = LinkType(name=name, source_type=source_type, target_type=target_type, **kwargs)
        self._store.register_link_type(link_type)
        return link_type

    def get_object_type(self, name: str) -> ObjectType | None:
        return self._store.get_object_type(name)

    def get_link_type(self, name: str) -> LinkType | None:
        return self._store.get_link_type(name)

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
