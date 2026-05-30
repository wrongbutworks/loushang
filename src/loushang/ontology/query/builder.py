"""查询构建器——链式图查询 API.

支持 Palantir 风格的链式查询：

    onto.query()
        .start_from(alice)              # 起始对象
        .follow("works_for")            # 沿关系遍历
        .where("industry", "==", "tech") # 属性过滤
        .follow("located_in")           # 继续遍历
        .limit(10)                      # 限制结果数
        .execute()                      # 执行查询
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID

if TYPE_CHECKING:
    from loushang.ontology.core.store import ObjectStore


@dataclass
class QueryStep:
    """查询计划中的一个步骤."""

    kind: str  # "start", "follow", "where", "limit", "offset", "sort"
    params: dict[str, Any] = field(default_factory=dict)


class QueryBuilder:
    """链式查询构建器."""

    def __init__(self, store: ObjectStore) -> None:
        self._store = store
        self._steps: list[QueryStep] = []

    # ------------------------------------------------------------------
    # 链式 API
    # ------------------------------------------------------------------

    def start_from(self, obj: "OntologyObject" | UUID) -> QueryBuilder:
        """设置查询起始对象."""
        from loushang.ontology.core.object import OntologyObject
        obj_id = obj.id if isinstance(obj, OntologyObject) else obj
        self._steps.append(QueryStep("start", {"obj_id": obj_id}))
        return self

    def follow(self, link_type: str, direction: str = "outgoing") -> QueryBuilder:
        """沿指定关系遍历."""
        self._steps.append(QueryStep("follow", {"link_type": link_type, "direction": direction}))
        return self

    def where(self, property_name: str, op: str, value: Any) -> QueryBuilder:
        """属性过滤条件.

        Args:
            property_name: 属性名
            op: 操作符，支持 "==", "!=", "<", "<=", ">", ">=", "in", "contains"
            value: 比较值
        """
        self._steps.append(QueryStep("where", {"property": property_name, "op": op, "value": value}))
        return self

    def where_type(self, object_type: str) -> QueryBuilder:
        """按对象类型过滤."""
        self._steps.append(QueryStep("where_type", {"object_type": object_type}))
        return self

    def limit(self, n: int) -> QueryBuilder:
        """限制结果数量."""
        self._steps.append(QueryStep("limit", {"n": n}))
        return self

    def offset(self, n: int) -> QueryBuilder:
        """跳过前 n 个结果."""
        self._steps.append(QueryStep("offset", {"n": n}))
        return self

    def sort_by(self, property_name: str, ascending: bool = True) -> QueryBuilder:
        """按属性排序."""
        self._steps.append(QueryStep("sort", {"property": property_name, "ascending": ascending}))
        return self

    def as_of(self, timestamp: float) -> QueryBuilder:
        """查询历史时间点快照."""
        self._steps.append(QueryStep("as_of", {"timestamp": timestamp}))
        return self

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def execute(self) -> list[OntologyObject]:
        """执行查询计划，返回结果列表."""
        result_set: list[OntologyObject] = []
        as_of: float | None = None

        for step in self._steps:
            if step.kind == "start":
                obj = self._store.get(step.params["obj_id"])
                result_set = [obj] if obj else []

            elif step.kind == "follow":
                new_set: list[OntologyObject] = []
                seen: set[UUID] = set()
                for obj in result_set:
                    neighbors = self._store.find_neighbors(
                        obj.id,
                        step.params["link_type"],
                        direction=step.params["direction"],
                        as_of=as_of,
                    )
                    for n in neighbors:
                        if n.id not in seen:
                            seen.add(n.id)
                            new_set.append(n)
                result_set = new_set

            elif step.kind == "where":
                result_set = _filter_by_property(
                    result_set,
                    step.params["property"],
                    step.params["op"],
                    step.params["value"],
                    as_of=as_of,
                )

            elif step.kind == "where_type":
                result_set = [o for o in result_set if o.object_type == step.params["object_type"]]

            elif step.kind == "as_of":
                as_of = step.params["timestamp"]

            elif step.kind == "limit":
                result_set = result_set[: step.params["n"]]

            elif step.kind == "offset":
                result_set = result_set[step.params["n"] :]

            elif step.kind == "sort":
                prop = step.params["property"]
                asc = step.params["ascending"]
                result_set.sort(key=lambda o: (o.get(prop, as_of=as_of) or ""), reverse=not asc)

        return result_set

    def execute_ids(self) -> list[UUID]:
        """执行查询，仅返回 UUID 列表."""
        return [o.id for o in self.execute()]

    def execute_first(self) -> OntologyObject | None:
        """执行查询，返回第一个结果."""
        results = self.execute()
        return results[0] if results else None

    def execute_count(self) -> int:
        """执行查询，返回结果数量."""
        return len(self.execute())

    def execute_exists(self) -> bool:
        """执行查询，返回是否有结果."""
        return len(self.execute()) > 0


def _filter_by_property(
    objects: list[OntologyObject],
    prop: str,
    op: str,
    value: Any,
    as_of: float | None = None,
) -> list[OntologyObject]:
    """按属性值过滤对象列表."""
    ops: dict[str, Callable[[Any, Any], bool]] = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        "<": lambda a, b: a is not None and b is not None and a < b,
        "<=": lambda a, b: a is not None and b is not None and a <= b,
        ">": lambda a, b: a is not None and b is not None and a > b,
        ">=": lambda a, b: a is not None and b is not None and a >= b,
        "in": lambda a, b: a in b if b is not None else False,
        "contains": lambda a, b: b in a if a is not None else False,
    }

    fn = ops.get(op)
    if fn is None:
        raise ValueError(f"Unsupported operator: {op}")

    return [o for o in objects if fn(o.get(prop, as_of=as_of), value)]
