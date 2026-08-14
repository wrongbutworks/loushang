"""Read-only observation of the committed Capability Mount graph."""

from __future__ import annotations

from dataclasses import dataclass

from loushang.harness.capabilities.graph_runtime import (
    CapabilityGraphBindingAttempt,
    MountGraphSnapshot,
    MountNodeSnapshot,
    RegistrationInventoryEntry,
    RegistrationInventorySnapshot,
    RuntimeCapabilityGraphRuntime,
)


@dataclass(frozen=True)
class CapabilityGraphExplanation:
    graph_id: str
    capability_id: str
    node: MountNodeSnapshot
    dependencies: tuple[str, ...]
    dependents: tuple[str, ...]
    registration_ids: tuple[str, ...]
    last_attempt: CapabilityGraphBindingAttempt | None


class RuntimeCapabilityGraphProjector:
    """Project one runtime instance; it neither selects nor mutates Providers."""

    def __init__(self, runtime: RuntimeCapabilityGraphRuntime) -> None:
        if not isinstance(runtime, RuntimeCapabilityGraphRuntime):
            raise TypeError("graph Projector requires RuntimeCapabilityGraphRuntime")
        self._runtime = runtime

    def snapshot(self, graph_id: str | None = None) -> MountGraphSnapshot:
        if graph_id is not None and graph_id != self._runtime.graph_id:
            raise KeyError(f"Projector does not own Mount graph: {graph_id}")
        if self._runtime.is_closed:
            raise RuntimeError("Capability Mount graph is disposed")
        snapshot = self._runtime.snapshot
        if snapshot is None:
            raise RuntimeError("Capability Mount graph has not been committed")
        return snapshot

    def registration_inventory(self) -> RegistrationInventorySnapshot:
        inventory = self._runtime.registration_inventory
        if inventory is None:
            raise RuntimeError("Capability registration inventory is not committed")
        return inventory

    def explain(self, capability_id: str) -> CapabilityGraphExplanation:
        node = self._node(capability_id)
        registrations = tuple(
            entry.registration_id for entry in self._registrations_for(capability_id)
        )
        return CapabilityGraphExplanation(
            graph_id=self._runtime.graph_id,
            capability_id=capability_id,
            node=node,
            dependencies=self.dependencies(capability_id),
            dependents=self.dependents(capability_id),
            registration_ids=registrations,
            last_attempt=self._runtime.last_attempt,
        )

    def dependencies(self, capability_id: str) -> tuple[str, ...]:
        node = self._node(capability_id)
        return tuple(item.capability_id for item in node.requirements)

    def dependents(self, capability_id: str) -> tuple[str, ...]:
        return self._node(capability_id).required_by

    def impact(self, capability_id: str) -> tuple[str, ...]:
        self._node(capability_id)
        impacted: set[str] = set()
        pending = list(self.dependents(capability_id))
        while pending:
            candidate = pending.pop(0)
            if candidate in impacted:
                continue
            impacted.add(candidate)
            pending.extend(self.dependents(candidate))
        order = tuple(node.capability_id for node in self.snapshot().nodes)
        return tuple(node_id for node_id in order if node_id in impacted)

    def _node(self, capability_id: str) -> MountNodeSnapshot:
        for node in self.snapshot().nodes:
            if node.capability_id == capability_id:
                return node
        raise KeyError(f"Capability is not present in the Mount graph: {capability_id}")

    def _registrations_for(
        self,
        capability_id: str,
    ) -> tuple[RegistrationInventoryEntry, ...]:
        return tuple(
            entry
            for entry in self.registration_inventory().entries
            if entry.owner_id == capability_id
            and entry.owner_kind == "capability"
            and entry.attachment == "effective"
        )


__all__ = [
    "CapabilityGraphExplanation",
    "RuntimeCapabilityGraphProjector",
]
