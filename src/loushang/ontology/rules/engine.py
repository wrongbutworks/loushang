"""规则引擎——基于本体的自动推理.

支持两种规则类型：
1. 属性规则（Property Rules）：当条件满足时，自动设置/更新属性
2. 链接规则（Link Rules）：当条件满足时，自动创建/删除关系

规则在对象状态变化时触发，类似于数据库触发器 + 业务规则引擎。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from loushang.ontology.core.object import OntologyObject
    from loushang.ontology.core.ontology import Ontology


RuleCondition = Callable[["OntologyObject"], bool]
RuleAction = Callable[["Ontology", "OntologyObject"], None]


@dataclass
class Rule:
    """单条规则定义.

    Args:
        name: 规则名称
        trigger_on: 触发时机，"property_change", "link_change", "schedule"
        condition: 条件函数，接收 OntologyObject 返回 bool
        action: 动作函数，接收 Ontology 和 OntologyObject
        priority: 优先级，数字越小优先级越高
        description: 规则描述
    """

    name: str
    trigger_on: str  # "property_change" | "link_change" | "schedule"
    condition: RuleCondition
    action: RuleAction
    priority: int = 0
    description: str = ""
    enabled: bool = True


class RuleEngine:
    """规则引擎，管理规则注册和执行."""

    def __init__(self, ontology: Ontology) -> None:
        self._ontology = ontology
        self._rules: list[Rule] = []
        self._max_iterations: int = 10  # 防止规则级联无限循环

    def register(self, rule: Rule) -> None:
        """注册规则，按优先级排序（数字小优先执行）."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)

    def unregister(self, name: str) -> bool:
        """按名称注销规则."""
        for i, r in enumerate(self._rules):
            if r.name == name:
                self._rules.pop(i)
                return True
        return False

    def evaluate(self, obj: OntologyObject, trigger: str) -> None:
        """评估与触发条件匹配的所有规则."""
        fired = set()
        for iteration in range(self._max_iterations):
            any_fired = False
            for rule in self._rules:
                if not rule.enabled:
                    continue
                if rule.trigger_on != trigger:
                    continue
                if rule.name in fired:
                    continue
                if rule.condition(obj):
                    rule.action(self._ontology, obj)
                    fired.add(rule.name)
                    any_fired = True
            if not any_fired:
                break
        else:
            # 达到最大迭代次数，可能规则循环
            pass  # 可记录警告日志

    # ------------------------------------------------------------------
    # 便捷工厂方法
    # ------------------------------------------------------------------

    @staticmethod
    def property_rule(
        name: str,
        condition: RuleCondition,
        target_property: str,
        value_fn: Callable[[OntologyObject], Any],
        priority: int = 0,
        description: str = "",
    ) -> Rule:
        """创建属性规则：条件满足时自动设置属性值.

        Args:
            value_fn: 计算属性值的函数
        """

        def action(onto: Ontology, obj: OntologyObject) -> None:
            new_value = value_fn(obj)
            obj.set(target_property, new_value)

        return Rule(
            name=name,
            trigger_on="property_change",
            condition=condition,
            action=action,
            priority=priority,
            description=description,
        )

    @staticmethod
    def link_rule(
        name: str,
        condition: RuleCondition,
        link_type: str,
        target_fn: Callable[[OntologyObject], Any],  # 返回 target 对象或 UUID
        priority: int = 0,
        description: str = "",
    ) -> Rule:
        """创建链接规则：条件满足时自动建立关系."""

        def action(onto: Ontology, obj: OntologyObject) -> None:
            target = target_fn(obj)
            if target is not None:
                onto.link(obj, link_type, target)

        return Rule(
            name=name,
            trigger_on="property_change",
            condition=condition,
            action=action,
            priority=priority,
            description=description,
        )
