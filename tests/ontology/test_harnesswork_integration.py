from __future__ import annotations

import asyncio

import pytest


def test_atomic_ontology_action_executes_through_harnesswork() -> None:
    from loushang.harnesswork import InMemoryEventLogBackend
    from loushang.ontology import Ontology, Property
    from loushang.ontology.integrations.harnesswork import (
        OntologyActionWorkRequest,
        create_ontology_action_operation,
        create_ontology_action_runtime,
    )

    ontology = Ontology()
    ontology.define_object_type(
        "Record",
        properties=[Property("name", str, required=True), Property("value", int)],
    )
    record = ontology.create("Record", name="Ontology fixture", value=10)

    class RecordActionHandler:
        async def execute(self, action):
            assert action.action_type == "Record.UpdateValue"
            target = ontology.get(record.id)
            assert target is not None
            value = action.parameters["value"]
            assert isinstance(value, int)
            target.set("value", value, author=action.actor_id)
            return {"value": value}

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        runtime = create_ontology_action_runtime(
            handler=RecordActionHandler(),
            event_log=event_log,
        )
        operation = create_ontology_action_operation(
            OntologyActionWorkRequest(
                action_type="Record.UpdateValue",
                object_id=str(record.id),
                parameters={"value": 35},
                actor_id="actor-1",
            ),
            operation_id="record-update-1",
            session_id="ontology-session-1",
        )

        accepted = await runtime.accept(operation)
        completed = await runtime.wait(accepted.run_id)

        assert completed.status == "completed"
        assert record.get("value") == 35
        entries = event_log.query(run_id=completed.run_id)
        assert [entry.payload["kind"] for entry in entries] == [
            "ExecuteOntologyAction",
            "WorkRunStarted",
            "OntologyActionStarted",
            "OntologyActionCommitted",
            "WorkRunCompleted",
        ]
        assert entries[-2].payload["payload"]["result"] == {"value": 35}

    asyncio.run(scenario())


def test_atomic_ontology_action_failure_does_not_publish_commit() -> None:
    from loushang.harnesswork import InMemoryEventLogBackend
    from loushang.ontology import Ontology, Property
    from loushang.ontology.integrations.harnesswork import (
        OntologyActionWorkRequest,
        create_ontology_action_operation,
        create_ontology_action_runtime,
    )

    ontology = Ontology()
    ontology.define_object_type(
        "Record",
        properties=[Property("name", str, required=True), Property("value", int)],
    )
    record = ontology.create("Record", name="Ontology fixture", value=10)

    class FailingActionHandler:
        async def execute(self, action):
            assert action.action_type == "Record.UpdateValue"
            target = ontology.get(record.id)
            assert target is not None
            assert target.get("value") == 10
            raise RuntimeError("ontology commit rejected")

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        runtime = create_ontology_action_runtime(
            handler=FailingActionHandler(),
            event_log=event_log,
        )
        operation = create_ontology_action_operation(
            OntologyActionWorkRequest(
                action_type="Record.UpdateValue",
                object_id=str(record.id),
                parameters={"value": 35},
                actor_id="actor-1",
            ),
            operation_id="record-update-failed-1",
            session_id="ontology-session-1",
        )

        accepted = await runtime.accept(operation)
        with pytest.raises(RuntimeError, match="ontology commit rejected"):
            await runtime.wait(accepted.run_id)

        assert runtime.get_run(accepted.run_id).status == "failed"
        assert record.get("value") == 10
        entries = event_log.query(run_id=accepted.run_id)
        assert [entry.payload["kind"] for entry in entries] == [
            "ExecuteOntologyAction",
            "WorkRunStarted",
            "OntologyActionStarted",
            "WorkRunFailed",
        ]

    asyncio.run(scenario())


def test_ontology_action_handler_cannot_bypass_managed_value_validation() -> None:
    from loushang.harnesswork import InMemoryEventLogBackend
    from loushang.ontology import Ontology, Property
    from loushang.ontology.integrations.harnesswork import (
        OntologyActionWorkRequest,
        create_ontology_action_operation,
        create_ontology_action_runtime,
    )

    ontology = Ontology()
    ontology.define_object_type("Record", properties=[Property("value", int)])
    record = ontology.create("Record", value=10)

    class InvalidActionHandler:
        async def execute(self, action):
            target = ontology.get(record.id)
            assert target is not None
            target.set("value", action.parameters["value"])
            return {"value": action.parameters["value"]}

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        runtime = create_ontology_action_runtime(
            handler=InvalidActionHandler(),
            event_log=event_log,
        )
        operation = create_ontology_action_operation(
            OntologyActionWorkRequest(
                action_type="Record.UpdateValue",
                object_id=str(record.id),
                parameters={"value": "invalid"},
            ),
            operation_id="record-update-invalid-1",
            session_id="ontology-session-1",
        )

        accepted = await runtime.accept(operation)
        with pytest.raises(ValueError, match="value"):
            await runtime.wait(accepted.run_id)

        assert record.get("value") == 10
        assert len(record.history("value")) == 1
        assert [entry.payload["kind"] for entry in event_log.query(run_id=accepted.run_id)] == [
            "ExecuteOntologyAction",
            "WorkRunStarted",
            "OntologyActionStarted",
            "WorkRunFailed",
        ]

    asyncio.run(scenario())
