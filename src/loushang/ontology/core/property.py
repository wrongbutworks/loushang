"""本体属性定义."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Property:
    """对象类型的属性定义.

    类似于数据库表的列定义，但支持更丰富的类型系统和约束.

    Args:
        name: 属性名称（英文标识符）
        data_type: 数据类型，可以是 Python 原生类型或自定义类型名
        required: 是否必填
        unique: 是否唯一（用于主键或业务键）
        indexed: 是否建立索引（加速查询）
        default: 默认值
        validator: 自定义校验函数
        description: 人类可读描述
    """

    name: str
    data_type: type | str
    required: bool = False
    unique: bool = False
    indexed: bool = False
    default: Any = None
    validator: Callable[[Any], bool] | None = None
    description: str = ""

    def validate(self, value: Any) -> None:
        """校验属性值是否合法."""
        if value is None:
            if self.required:
                raise ValueError(f"Property '{self.name}' is required")
            return

        if self.validator is not None and not self.validator(value):
            raise ValueError(f"Property '{self.name}' validation failed for value {value!r}")


@dataclass(frozen=True)
class TemporalProperty(Property):
    """时序属性：值随时间变化，保留历史版本.

    这是 Palantir 式本体的核心特征之一。
    每次更新都会创建新的时间戳版本，旧版本保留可查询。
    """

    retention_days: int | None = None  # 历史版本保留天数，None 表示永久保留


@dataclass(frozen=True)
class DerivedProperty(Property):
    """派生属性：值通过规则/公式动态计算.

    例如：排放口对象的 `is_compliant` 属性可由最新监测数据与标准比较得出。
    """

    formula: str = ""  # 计算表达式或规则引用
    dependencies: list[str] = field(default_factory=list)  # 依赖的属性名
