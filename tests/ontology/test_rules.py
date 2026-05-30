"""规则引擎测试."""

import pytest

from loushang.ontology import Ontology, Property, RuleEngine


class TestRuleEngine:
    def test_property_rule(self) -> None:
        onto = Ontology()
        onto.define_object_type(
            "Sensor",
            properties=[
                Property("reading", float),
                Property("status", str),
            ],
        )

        engine = RuleEngine(onto)
        rule = RuleEngine.property_rule(
            name="high_temp_alert",
            condition=lambda obj: (obj.get("reading") or 0) > 100,
            target_property="status",
            value_fn=lambda obj: "ALERT",
            description="Temperature too high",
        )
        engine.register(rule)

        sensor = onto.create("Sensor", reading=50.0)
        engine.evaluate(sensor, "property_change")
        assert sensor.get("status") is None

        sensor.set("reading", 150.0)
        engine.evaluate(sensor, "property_change")
        assert sensor.get("status") == "ALERT"

    def test_link_rule(self) -> None:
        onto = Ontology()
        onto.define_object_type("Person", properties=[Property("name", str)])
        onto.define_object_type("Company", properties=[Property("name", str)])
        onto.define_link_type("works_for", "Person", "Company")

        acme = onto.create("Company", name="ACME")

        engine = RuleEngine(onto)
        rule = RuleEngine.link_rule(
            name="auto_assign",
            condition=lambda obj: obj.get("name") == "Alice",
            link_type="works_for",
            target_fn=lambda obj: acme,
        )
        engine.register(rule)

        alice = onto.create("Person", name="Alice")
        engine.evaluate(alice, "property_change")

        neighbors = onto._store.find_neighbors(alice.id, "works_for")
        assert len(neighbors) == 1
        assert neighbors[0].id == acme.id

    def test_rule_priority(self) -> None:
        onto = Ontology()
        onto.define_object_type(
            "Item",
            properties=[Property("value", int), Property("flag", str)],
        )

        engine = RuleEngine(onto)

        # 低优先级规则设置 flag（优先级数字大，后执行）
        engine.register(
            RuleEngine.property_rule(
                name="low_priority",
                condition=lambda obj: True,
                target_property="flag",
                value_fn=lambda obj: "low",
                priority=10,
            )
        )

        # 高优先级规则设置 flag（优先级数字小，先执行）
        engine.register(
            RuleEngine.property_rule(
                name="high_priority",
                condition=lambda obj: True,
                target_property="flag",
                value_fn=lambda obj: "high",
                priority=0,
            )
        )

        item = onto.create("Item", value=1)
        engine.evaluate(item, "property_change")
        # 两个规则都触发，低优先级后执行所以最终值是 "low"
        # 这展示了执行顺序：priority 小的先执行
        assert item.get("flag") == "low"

    def test_rule_disable(self) -> None:
        onto = Ontology()
        onto.define_object_type(
            "Item",
            properties=[Property("value", int), Property("flag", str)],
        )

        engine = RuleEngine(onto)
        rule = RuleEngine.property_rule(
            name="always_set",
            condition=lambda obj: True,
            target_property="flag",
            value_fn=lambda obj: "set",
        )
        engine.register(rule)

        item = onto.create("Item", value=1)
        engine.evaluate(item, "property_change")
        assert item.get("flag") == "set"

        # 禁用规则
        rule.enabled = False
        item2 = onto.create("Item", value=2)
        engine.evaluate(item2, "property_change")
        assert item2.get("flag") is None

    def test_unregister_rule(self) -> None:
        onto = Ontology()
        onto.define_object_type(
            "Item",
            properties=[Property("value", int), Property("flag", str)],
        )

        engine = RuleEngine(onto)
        rule = RuleEngine.property_rule(
            name="test_rule",
            condition=lambda obj: True,
            target_property="flag",
            value_fn=lambda obj: "set",
        )
        engine.register(rule)
        assert engine.unregister("test_rule") is True
        assert engine.unregister("test_rule") is False
