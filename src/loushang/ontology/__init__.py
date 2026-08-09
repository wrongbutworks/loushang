"""实验性的 operational ontology infrastructure.

当前公开 facade 保留动态对象图原型的兼容行为。版本化 schema 编译、运行时
snapshot 和受控 mutation 正在逐步建立；本包不宣称实现完整 Palantir Foundry、
OWL 推理器或生产级图存储。

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

from loushang.ontology.core.constraints import IntegrityViolation
from loushang.ontology.core.link_type import Cardinality, LinkType
from loushang.ontology.core.object import OntologyObject
from loushang.ontology.core.object_type import ObjectType
from loushang.ontology.core.ontology import Ontology
from loushang.ontology.core.projection import ProjectionState, StoreMutation
from loushang.ontology.core.property import DerivedProperty, Property, TemporalProperty
from loushang.ontology.core.store import ObjectStore
from loushang.ontology.core.store_port import (
    OntologyReadStore,
    OntologyStore,
    OperationalMutationStore,
    ProjectionStore,
)
from loushang.ontology.facts import (
    AssertionKind,
    FactBatch,
    FactCommit,
    FactProjection,
    FactRecord,
    LinkAssertion,
    ObjectAssertion,
    PropertyAssertion,
    StoredFact,
    project_facts,
)
from loushang.ontology.fusion.mapper import DataFusion, FieldMapping, SourceMapping
from loushang.ontology.query.builder import QueryBuilder
from loushang.ontology.query.contracts import QueryRequest, QueryResult
from loushang.ontology.rules.engine import Rule, RuleEngine
from loushang.ontology.schema import (
    CompiledOntologySchema,
    InterfaceTypeDefinition,
    LinkCardinality,
    LinkTypeDefinition,
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    SchemaCompilationError,
    SchemaDiagnostic,
    SchemaVersion,
    ValueType,
)

__all__ = [
    "Ontology",
    "IntegrityViolation",
    "ObjectType",
    "Property",
    "TemporalProperty",
    "DerivedProperty",
    "LinkType",
    "Cardinality",
    "OntologyObject",
    "ObjectStore",
    "ProjectionState",
    "StoreMutation",
    "AssertionKind",
    "FactBatch",
    "FactCommit",
    "FactProjection",
    "FactRecord",
    "LinkAssertion",
    "ObjectAssertion",
    "PropertyAssertion",
    "StoredFact",
    "project_facts",
    "OntologyReadStore",
    "OntologyStore",
    "OperationalMutationStore",
    "ProjectionStore",
    "QueryBuilder",
    "QueryRequest",
    "QueryResult",
    "RuleEngine",
    "Rule",
    "DataFusion",
    "FieldMapping",
    "SourceMapping",
    "CompiledOntologySchema",
    "InterfaceTypeDefinition",
    "LinkCardinality",
    "LinkTypeDefinition",
    "ObjectTypeDefinition",
    "OntologyCompiler",
    "OntologyPackageDraft",
    "PropertyDefinition",
    "SchemaCompilationError",
    "SchemaDiagnostic",
    "SchemaVersion",
    "ValueType",
]
