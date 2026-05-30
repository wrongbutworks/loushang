"""通用动态本体系统——Palantir 式知识图谱框架.

核心模块:
    core    - 本体引擎（对象类型、属性、关系、存储）
    query   - 图查询引擎（链式查询、时序查询）
    rules   - 规则引擎（自动推理、触发器）
    fusion  - 数据融合（多源映射、ETL）

快速开始::

    from loushang.ontology import Ontology, Property

    onto = Ontology()

    onto.define_object_type("Person", properties=[
        Property("name", str, required=True, indexed=True),
        Property("age", int),
    ])

    alice = onto.create("Person", name="Alice", age=30)
    print(alice.get("name"))  # "Alice"
"""

from loushang.ontology.core.ontology import Ontology
from loushang.ontology.core.object_type import ObjectType
from loushang.ontology.core.property import Property, TemporalProperty, DerivedProperty
from loushang.ontology.core.link_type import LinkType, Cardinality
from loushang.ontology.core.object import OntologyObject
from loushang.ontology.core.store import ObjectStore
from loushang.ontology.query.builder import QueryBuilder
from loushang.ontology.rules.engine import RuleEngine, Rule
from loushang.ontology.fusion.mapper import DataFusion, FieldMapping, SourceMapping

__all__ = [
    "Ontology",
    "ObjectType",
    "Property",
    "TemporalProperty",
    "DerivedProperty",
    "LinkType",
    "Cardinality",
    "OntologyObject",
    "ObjectStore",
    "QueryBuilder",
    "RuleEngine",
    "Rule",
    "DataFusion",
    "FieldMapping",
    "SourceMapping",
]
