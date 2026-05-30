"""对象关系（链接类型）定义."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class Cardinality(Enum):
    """关系基数约束."""

    ONE_TO_ONE = auto()      # 1:1
    ONE_TO_MANY = auto()     # 1:N
    MANY_TO_ONE = auto()     # N:1
    MANY_TO_MANY = auto()    # N:M


@dataclass(frozen=True)
class LinkType:
    """对象间链接（关系）的定义.

    Args:
        name: 关系名称，如 "owns", "emits", "monitors"
        source_type: 源对象类型名
        target_type: 目标对象类型名
        cardinality: 基数约束
        required: 源对象是否必须至少有一个此关系
        inverse_name: 反向关系名称，如 "owned_by"
        temporal: 关系是否带时间戳（支持历史关系查询）
        description: 人类可读描述
    """

    name: str
    source_type: str
    target_type: str
    cardinality: Cardinality = Cardinality.ONE_TO_MANY
    required: bool = False
    inverse_name: str | None = None
    temporal: bool = True  # Palantir 默认所有关系带时序
    description: str = ""

    def allows_multiple_targets(self) -> bool:
        """是否允许源对象链接到多个目标."""
        return self.cardinality in (Cardinality.ONE_TO_MANY, Cardinality.MANY_TO_MANY)

    def allows_multiple_sources(self) -> bool:
        """是否允许多个源对象链接到同一个目标."""
        return self.cardinality in (Cardinality.MANY_TO_ONE, Cardinality.MANY_TO_MANY)
