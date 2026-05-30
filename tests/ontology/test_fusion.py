"""数据融合测试."""

import pytest

from loushang.ontology import DataFusion, FieldMapping, Ontology, Property, SourceMapping


class TestDataFusion:
    def test_basic_ingest(self) -> None:
        onto = Ontology()
        onto.define_object_type(
            "Employee",
            properties=[
                Property("full_name", str, required=True),
                Property("years_old", int),
                Property("department", str),
            ],
        )

        fusion = DataFusion(onto)
        fusion.register_mapping(
            SourceMapping(
                source_name="hr_db",
                object_type="Employee",
                id_field="emp_id",
                field_mappings=[
                    FieldMapping("emp_name", "full_name"),
                    FieldMapping("age", "years_old"),
                    FieldMapping("dept", "department"),
                ],
            )
        )

        records = [
            {"emp_id": "E001", "emp_name": "Alice", "age": 30, "dept": "Engineering"},
            {"emp_id": "E002", "emp_name": "Bob", "age": 25, "dept": "Sales"},
        ]

        results = fusion.ingest("hr_db", records)
        assert len(results) == 2
        assert results[0].get("full_name") == "Alice"
        assert results[0].get("years_old") == 30
        assert results[1].get("full_name") == "Bob"

    def test_transform(self) -> None:
        onto = Ontology()
        onto.define_object_type(
            "Sensor",
            properties=[
                Property("reading_celsius", float),
            ],
        )

        fusion = DataFusion(onto)
        fusion.register_mapping(
            SourceMapping(
                source_name="iot_api",
                object_type="Sensor",
                id_field="device_id",
                field_mappings=[
                    FieldMapping(
                        "temp_fahrenheit",
                        "reading_celsius",
                        transform=lambda f: (f - 32) * 5 / 9,
                    ),
                ],
            )
        )

        records = [{"device_id": "D1", "temp_fahrenheit": 212.0}]
        results = fusion.ingest("iot_api", records)
        assert results[0].get("reading_celsius") == pytest.approx(100.0)

    def test_update_existing(self) -> None:
        onto = Ontology()
        onto.define_object_type(
            "Product",
            properties=[
                Property("sku", str, required=True, indexed=True),
                Property("price", float),
            ],
        )

        fusion = DataFusion(onto)
        fusion.register_mapping(
            SourceMapping(
                source_name="erp",
                object_type="Product",
                id_field="sku",
                field_mappings=[
                    FieldMapping("sku", "sku"),
                    FieldMapping("price", "price"),
                ],
            )
        )

        # 首次摄入
        fusion.ingest("erp", [{"sku": "SKU-001", "price": 10.0}])
        # 更新价格
        results = fusion.ingest("erp", [{"sku": "SKU-001", "price": 12.0}])

        assert len(results) == 1
        assert results[0].get("price") == 12.0

        # 确认只有一个对象（更新而非创建）
        all_products = onto.find_by_type("Product")
        assert len(all_products) == 1

    def test_missing_required_field(self) -> None:
        onto = Ontology()
        onto.define_object_type(
            "Item",
            properties=[Property("name", str, required=True)],
        )

        fusion = DataFusion(onto)
        fusion.register_mapping(
            SourceMapping(
                source_name="bad_source",
                object_type="Item",
                id_field="id",
                field_mappings=[
                    FieldMapping("name", "name", required=True),
                ],
            )
        )

        with pytest.raises(ValueError, match="Required field"):
            fusion.ingest("bad_source", [{"id": "1"}])

    def test_unregistered_source(self) -> None:
        onto = Ontology()
        fusion = DataFusion(onto)

        with pytest.raises(ValueError, match="No mapping registered"):
            fusion.ingest("unknown", [{}])
