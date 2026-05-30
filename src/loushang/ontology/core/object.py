"""本体对象实例——动态对象的运行时表示."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from loushang.ontology.core.link_type import LinkType


@dataclass
class PropertyVersion:
    """属性的一个时间戳版本."""

    value: Any
    timestamp: float  # UTC epoch seconds
    author: str | None = None  # 谁修改的
    source: str | None = None  # 数据来源（如 "manual", "iot_api", "etl"）


@dataclass
class LinkVersion:
    """关系链接的一个时间戳版本."""

    target_id: UUID
    timestamp: float
    active: bool = True  # False 表示关系已删除/失效
    properties: dict[str, Any] = field(default_factory=dict)  # 关系上的属性（如权重、置信度）


class OntologyObject:
    """本体中的对象实例——Palantir 式动态对象的核心.

    每个对象有：
    - 全局唯一 UUID
    - 类型标识
    - 带时序版本的属性
    - 带时序版本的出入关系

    对象创建后类型不可变，但属性值和关系可动态演变。
    """

    def __init__(
        self,
        object_type: str,
        obj_id: UUID | None = None,
        properties: dict[str, list[PropertyVersion]] | None = None,
        outgoing_links: dict[str, list[LinkVersion]] | None = None,
        incoming_links: dict[str, list[LinkVersion]] | None = None,
    ) -> None:
        self.object_type = object_type
        self.id = obj_id or uuid4()
        # property_name -> [versions, newest last]
        self._properties: dict[str, list[PropertyVersion]] = properties or {}
        # link_type_name -> [versions, newest last]
        self._outgoing: dict[str, list[LinkVersion]] = outgoing_links or {}
        self._incoming: dict[str, list[LinkVersion]] = incoming_links or {}

    # ------------------------------------------------------------------
    # 属性操作（时序版本）
    # ------------------------------------------------------------------

    def set(
        self,
        name: str,
        value: Any,
        timestamp: float | None = None,
        author: str | None = None,
        source: str | None = None,
    ) -> None:
        """设置属性值，创建新版本."""
        import time

        ts = timestamp if timestamp is not None else time.time()
        version = PropertyVersion(value=value, timestamp=ts, author=author, source=source)
        self._properties.setdefault(name, []).append(version)

    def get(self, name: str, as_of: float | None = None) -> Any | None:
        """获取属性值.

        Args:
            name: 属性名
            as_of: 查询某个时间点的值；None 表示最新值
        """
        versions = self._properties.get(name)
        if not versions:
            return None
        if as_of is None:
            return versions[-1].value
        # 查找最近的不超过 as_of 的版本
        result = None
        for v in versions:
            if v.timestamp <= as_of:
                result = v.value
        return result

    def history(self, name: str) -> list[PropertyVersion]:
        """获取属性的完整历史版本."""
        return list(self._properties.get(name, []))

    def all_properties(self, as_of: float | None = None) -> dict[str, Any]:
        """获取对象在某一时刻的所有属性快照."""
        result: dict[str, Any] = {}
        for name in self._properties:
            val = self.get(name, as_of=as_of)
            if val is not None:
                result[name] = val
        return result

    # ------------------------------------------------------------------
    # 关系操作（时序版本）
    # ------------------------------------------------------------------

    def link(
        self,
        link_type: str,
        target: OntologyObject,
        timestamp: float | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """建立 outgoing 关系."""
        import time

        ts = timestamp if timestamp is not None else time.time()
        version = LinkVersion(
            target_id=target.id,
            timestamp=ts,
            active=True,
            properties=properties or {},
        )
        self._outgoing.setdefault(link_type, []).append(version)

    def unlink(
        self,
        link_type: str,
        target: OntologyObject,
        timestamp: float | None = None,
    ) -> None:
        """软删除关系（追加失效版本，保留历史）."""
        import time

        ts = timestamp if timestamp is not None else time.time()
        # 追加一个新的失效版本，而不是修改旧版本的时间戳
        # 这样历史查询仍能看到旧版本的有效状态
        version = LinkVersion(
            target_id=target.id,
            timestamp=ts,
            active=False,
            properties={},
        )
        self._outgoing.setdefault(link_type, []).append(version)

    def get_links(
        self,
        link_type: str,
        as_of: float | None = None,
        active_only: bool = True,
    ) -> list[LinkVersion]:
        """获取 outgoing 关系."""
        versions = self._outgoing.get(link_type, [])
        result: list[LinkVersion] = []
        seen: set[UUID] = set()
        # 倒序遍历，取每个 target 在 as_of 时刻的最新版本
        for v in reversed(versions):
            if as_of is not None and v.timestamp > as_of:
                continue
            if v.target_id in seen:
                continue
            seen.add(v.target_id)
            if active_only and not v.active:
                continue
            result.append(v)
        return result

    def get_incoming(
        self,
        link_type: str,
        as_of: float | None = None,
        active_only: bool = True,
    ) -> list[LinkVersion]:
        """获取 incoming 关系（需由 Store 维护索引后使用）."""
        versions = self._incoming.get(link_type, [])
        result: list[LinkVersion] = []
        seen: set[UUID] = set()
        for v in reversed(versions):
            if as_of is not None and v.timestamp > as_of:
                continue
            if v.target_id in seen:
                continue
            seen.add(v.target_id)
            if active_only and not v.active:
                continue
            result.append(v)
        return result

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（最新快照）."""
        return {
            "id": str(self.id),
            "object_type": self.object_type,
            "properties": self.all_properties(),
        }

    def __repr__(self) -> str:
        return f"<OntologyObject {self.object_type} {self.id}>"
