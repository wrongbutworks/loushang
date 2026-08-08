"""数据融合——将外部数据源映射到本体对象.

支持从不同数据源（数据库、API、文件、消息队列）提取数据，
通过映射配置转换为本体对象，实现多源数据的统一语义层。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loushang.ontology.core.object import OntologyObject
from loushang.ontology.core.ontology import Ontology


@dataclass
class FieldMapping:
    """字段映射定义：外部字段 -> 本体属性.

    Args:
        source_field: 外部数据源中的字段名
        target_property: 本体对象属性名
        transform: 可选的转换函数
        required: 是否必须存在
        default: 默认值
    """

    source_field: str
    target_property: str
    transform: Callable[[Any], Any] | None = None
    required: bool = False
    default: Any = None


@dataclass
class SourceMapping:
    """数据源映射配置.

    定义如何将一个外部数据记录映射为本体对象。

    Args:
        source_name: 数据源标识（如 "erp_db", "iot_api", "csv_file"）
        object_type: 目标本体对象类型
        id_field: 外部主键字段（用于生成或查找对象 UUID）
        field_mappings: 字段映射列表
        link_mappings: 关系映射（外部字段 -> 关系类型和目标对象查找）
    """

    source_name: str
    object_type: str
    id_field: str
    field_mappings: list[FieldMapping] = field(default_factory=list)
    link_mappings: list[dict[str, Any]] = field(default_factory=list)


class DataFusion:
    """数据融合引擎，协调多源数据到本体的映射."""

    def __init__(self, ontology: Ontology) -> None:
        self._ontology = ontology
        self._mappings: dict[str, SourceMapping] = {}
        self._id_cache: dict[tuple[str, Any], Any] = {}  # (source_name, source_id) -> UUID

    def register_mapping(self, mapping: SourceMapping) -> None:
        """注册数据源映射配置."""
        self._mappings[mapping.source_name] = mapping

    def ingest(
        self,
        source_name: str,
        records: list[dict[str, Any]],
    ) -> list[OntologyObject]:
        """摄入一批外部数据记录，映射为本体对象.

        Args:
            source_name: 数据源名称
            records: 外部数据记录列表

        Returns:
            创建或更新的本体对象列表
        """
        mapping = self._mappings.get(source_name)
        if mapping is None:
            raise ValueError(f"No mapping registered for source '{source_name}'")

        results: list[OntologyObject] = []
        for record in records:
            obj = self._map_record(mapping, record)
            results.append(obj)
        return results

    def _map_record(
        self,
        mapping: SourceMapping,
        record: dict[str, Any],
    ) -> OntologyObject:
        """将单条记录映射为对象."""
        # 提取或生成对象 ID
        source_id = record.get(mapping.id_field)
        cache_key = (mapping.source_name, source_id)

        # 尝试查找已有对象
        existing_id = self._id_cache.get(cache_key)
        if existing_id:
            obj = self._ontology.get(existing_id)
            if obj is not None:
                # 更新现有对象
                self._apply_properties(obj, mapping, record)
                return obj

        # 创建新对象
        properties: dict[str, Any] = {}
        for fm in mapping.field_mappings:
            value = record.get(fm.source_field, fm.default)
            if value is None and fm.required:
                raise ValueError(f"Required field '{fm.source_field}' missing in record")
            if fm.transform is not None and value is not None:
                value = fm.transform(value)
            properties[fm.target_property] = value

        obj = self._ontology.create(mapping.object_type, **properties)
        self._id_cache[cache_key] = obj.id
        return obj

    def _apply_properties(
        self,
        obj: OntologyObject,
        mapping: SourceMapping,
        record: dict[str, Any],
    ) -> None:
        """将记录属性应用到已有对象（更新模式）."""
        for fm in mapping.field_mappings:
            value = record.get(fm.source_field)
            if value is not None:
                if fm.transform is not None:
                    value = fm.transform(value)
                self._ontology.set_property(obj, fm.target_property, value)
