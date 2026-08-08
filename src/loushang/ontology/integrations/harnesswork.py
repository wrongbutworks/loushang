"""Atomic Ontology Action binding for the optional HarnessWork runtime.

The current adapter models an ontology-owned, single-process commit only. A
handler must return only after its local mutation has committed; a normal
return publishes ``OntologyActionCommitted`` and an exception leaves the run
failed without that fact. External effects, compensation, reconciliation,
cross-process transactions, and authorization are deliberately outside this
contract. ``actor_id`` is audit context, not proof of authorization.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from loushang.foundation.json import require_json_mapping
from loushang.harnesswork import (
    EventLogBackend,
    WorkEventFact,
    WorkExecutionContext,
    WorkOperation,
    WorkRuntime,
)


@dataclass(frozen=True, slots=True)
class OntologyActionWorkProfile:
    domain: str = "ontology"
    operation_kind: str = "ExecuteOntologyAction"

    def __post_init__(self) -> None:
        if not self.domain.strip():
            raise ValueError("Ontology Action domain must not be empty")
        if not self.operation_kind.strip():
            raise ValueError("Ontology Action operation kind must not be empty")


@dataclass(frozen=True, slots=True)
class OntologyActionWorkRequest:
    action_type: str
    object_id: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    actor_id: str | None = None

    def __post_init__(self) -> None:
        if not self.action_type.strip():
            raise ValueError("Ontology Action type must not be empty")
        if not self.object_id.strip():
            raise ValueError("Ontology Action object_id must not be empty")
        require_json_mapping(
            dict(self.parameters),
            name="ontology_action.parameters",
        )
        if self.actor_id is not None and not self.actor_id.strip():
            raise ValueError("Ontology Action actor_id must not be empty when set")


class OntologyActionHandler(Protocol):
    def execute(
        self,
        action: OntologyActionWorkRequest,
    ) -> Awaitable[Mapping[str, object] | None]: ...


@dataclass(frozen=True, slots=True)
class OntologyActionExecutor:
    handler: OntologyActionHandler
    profile: OntologyActionWorkProfile = OntologyActionWorkProfile()

    async def execute(
        self,
        operation: WorkOperation,
        context: WorkExecutionContext,
    ) -> None:
        action = _action_from_operation(operation, profile=self.profile)
        context.publish(
            WorkEventFact(
                kind="OntologyActionStarted",
                payload=_action_identity(action),
                delivery_hint="immediate",
            )
        )
        result = await self.handler.execute(action)
        payload = _action_identity(action)
        if result is not None:
            payload["result"] = require_json_mapping(
                dict(result),
                name="ontology_action.result",
            )
        context.publish(
            WorkEventFact(
                kind="OntologyActionCommitted",
                payload=payload,
                delivery_hint="immediate",
            )
        )


def create_ontology_action_operation(
    action: OntologyActionWorkRequest,
    *,
    operation_id: str,
    session_id: str | None = None,
    profile: OntologyActionWorkProfile = OntologyActionWorkProfile(),
) -> WorkOperation:
    payload: dict[str, object] = {
        "action_type": action.action_type,
        "object_id": action.object_id,
        "parameters": require_json_mapping(
            dict(action.parameters),
            name="ontology_action.parameters",
        ),
    }
    if action.actor_id is not None:
        payload["actor_id"] = action.actor_id
    return WorkOperation(
        operation_id=operation_id,
        kind=profile.operation_kind,
        session_id=session_id,
        domain=profile.domain,
        payload=payload,
    )


def create_ontology_action_runtime(
    *,
    handler: OntologyActionHandler,
    event_log: EventLogBackend,
    profile: OntologyActionWorkProfile = OntologyActionWorkProfile(),
    clock: Callable[[], datetime] | None = None,
) -> WorkRuntime:
    executor = OntologyActionExecutor(handler=handler, profile=profile)
    if clock is None:
        return WorkRuntime(event_log=event_log, executor=executor)
    return WorkRuntime(event_log=event_log, executor=executor, clock=clock)


def _action_from_operation(
    operation: WorkOperation,
    *,
    profile: OntologyActionWorkProfile,
) -> OntologyActionWorkRequest:
    if operation.domain != profile.domain or operation.kind != profile.operation_kind:
        raise ValueError(
            "Ontology Action executor cannot execute "
            f"{operation.domain}:{operation.kind}"
        )
    action_type = operation.payload.get("action_type")
    object_id = operation.payload.get("object_id")
    parameters = operation.payload.get("parameters", {})
    actor_id = operation.payload.get("actor_id")
    if not isinstance(action_type, str):
        raise ValueError("Ontology Action payload requires string action_type")
    if not isinstance(object_id, str):
        raise ValueError("Ontology Action payload requires string object_id")
    if not isinstance(parameters, Mapping):
        raise ValueError("Ontology Action payload parameters must be an object")
    if actor_id is not None and not isinstance(actor_id, str):
        raise ValueError("Ontology Action payload actor_id must be a string")
    return OntologyActionWorkRequest(
        action_type=action_type,
        object_id=object_id,
        parameters=parameters,
        actor_id=actor_id,
    )


def _action_identity(action: OntologyActionWorkRequest) -> dict[str, object]:
    identity: dict[str, object] = {
        "action_type": action.action_type,
        "object_id": action.object_id,
    }
    if action.actor_id is not None:
        identity["actor_id"] = action.actor_id
    return identity


__all__ = [
    "OntologyActionExecutor",
    "OntologyActionHandler",
    "OntologyActionWorkProfile",
    "OntologyActionWorkRequest",
    "create_ontology_action_operation",
    "create_ontology_action_runtime",
]
