"""对象类型定义——本体中的"类"."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loushang.ontology.core.property import Property


@dataclass
class ObjectType:
    """对象类型定义，类似于数据库表结构或面向对象的类.

    Palantir 式本体的核心：一切都是对象，对象有类型，类型定义属性和可参与的关系。

    Args:
        name: 类型名称，如 "Enterprise", "DischargePort", "MonitoringData"
        properties: 属性定义列表
        parent_types: 父类型（支持多重继承）
        abstract: 是否为抽象类型（不能直接创建实例）
        icon: 可视化图标标识
        description: 人类可读描述
        display_name_property: 用于显示的对象属性名
    """

    name: str
    properties: list[Property] | tuple[Property, ...] = field(default_factory=list)
    parent_types: list[str] | tuple[str, ...] = field(default_factory=list)
    abstract: bool = False
    icon: str | None = None
    description: str = ""
    display_name_property: str | None = None

    # 运行时注册的关系名（由 Ontology 在 define_link_type 时填充）
    outgoing_link_types: set[str] | frozenset[str] = field(default_factory=set, repr=False)
    incoming_link_types: set[str] | frozenset[str] = field(default_factory=set, repr=False)
    _schema_frozen: bool = field(default=False, init=False, repr=False)

    def __setattr__(self, name: str, value: object) -> None:
        if name != "_schema_frozen" and getattr(self, "_schema_frozen", False):
            raise RuntimeError(f"Object type '{self.name}' schema is frozen")
        object.__setattr__(self, name, value)

    def add_outgoing_link_type(self, name: str) -> None:
        if not isinstance(self.outgoing_link_types, set):
            raise RuntimeError(f"Object type '{self.name}' schema is frozen")
        self.outgoing_link_types.add(name)

    def add_incoming_link_type(self, name: str) -> None:
        if not isinstance(self.incoming_link_types, set):
            raise RuntimeError(f"Object type '{self.name}' schema is frozen")
        self.incoming_link_types.add(name)

    def freeze_schema(self) -> None:
        """Make all schema-bearing collections immutable."""

        if self._schema_frozen:
            return
        object.__setattr__(self, "properties", tuple(self.properties))
        object.__setattr__(self, "parent_types", tuple(self.parent_types))
        object.__setattr__(self, "outgoing_link_types", frozenset(self.outgoing_link_types))
        object.__setattr__(self, "incoming_link_types", frozenset(self.incoming_link_types))
        object.__setattr__(self, "_schema_frozen", True)

    def get_property(self, name: str) -> Property | None:
        """按名称查找属性定义."""
        for prop in self.properties:
            if prop.name == name:
                return prop
        return None

    def all_properties(self, registry: dict[str, ObjectType] | None = None) -> list[Property]:
        """获取所有属性（含继承自父类型的）."""
        props = list(self.properties)
        if registry:
            for parent_name in self.parent_types:
                parent = registry.get(parent_name)
                if parent:
                    props.extend(parent.all_properties(registry))
        return props

    def validate_properties(self, data: dict[str, object]) -> dict[str, object]:
        """校验并填充默认值，返回处理后的数据字典."""
        result = dict(data)
        prop_map = {p.name: p for p in self.properties}

        # 检查必填
        for prop in self.properties:
            if prop.required and prop.name not in result:
                if prop.default is not None:
                    result[prop.name] = prop.default
                else:
                    raise ValueError(f"Required property '{prop.name}' missing for {self.name}")

        # 校验存在的属性
        for key, value in list(result.items()):
            if key in prop_map:
                prop_map[key].validate(value)

        return result
