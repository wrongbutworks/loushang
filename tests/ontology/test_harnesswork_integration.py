from __future__ import annotations

import asyncio


def test_project_progress_action_executes_through_harnesswork() -> None:
    from loushang.harnesswork import InMemoryEventLogBackend
    from loushang.ontology import Ontology, Property
    from loushang.ontology.integrations.harnesswork import (
        OntologyActionWorkRequest,
        create_ontology_action_operation,
        create_ontology_action_runtime,
    )

    ontology = Ontology()
    ontology.define_object_type(
        "Project",
        properties=[Property("name", str, required=True), Property("progress", int)],
    )
    project = ontology.create("Project", name="Ontology pilot", progress=10)

    class ProjectActionHandler:
        async def execute(self, action):
            assert action.action_type == "Project.UpdateProgress"
            target = ontology.get(project.id)
            assert target is not None
            progress = action.parameters["progress"]
            assert isinstance(progress, int)
            target.set("progress", progress, author=action.actor_id)
            return {"progress": progress}

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        runtime = create_ontology_action_runtime(
            handler=ProjectActionHandler(),
            event_log=event_log,
        )
        operation = create_ontology_action_operation(
            OntologyActionWorkRequest(
                action_type="Project.UpdateProgress",
                object_id=str(project.id),
                parameters={"progress": 35},
                actor_id="project-manager-1",
            ),
            operation_id="project-progress-1",
            session_id="project-workspace-1",
        )

        accepted = await runtime.accept(operation)
        completed = await runtime.wait(accepted.run_id)

        assert completed.status == "completed"
        assert project.get("progress") == 35
        entries = event_log.query(run_id=completed.run_id)
        assert [entry.payload["kind"] for entry in entries] == [
            "ExecuteOntologyAction",
            "WorkRunStarted",
            "OntologyActionStarted",
            "OntologyActionCommitted",
            "WorkRunCompleted",
        ]
        assert entries[-2].payload["payload"]["result"] == {"progress": 35}

    asyncio.run(scenario())
