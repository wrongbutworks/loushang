"""Consumer seam for the authorized process-launch workspace facet."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from loushang.harness.capabilities.graph_runtime import CapabilityFacetSet
from loushang.harness.capabilities.workspace_contracts import (
    WORKSPACE_PROCESS_LAUNCH_FACET,
    WORKSPACE_PROCESS_REQUIREMENT,
)
from loushang.harness.workspace.process import (
    AuthorizedProcessLauncher,
    ProcessHandle,
    ProcessLaunchRequest,
)


@dataclass(frozen=True, slots=True)
class _ProcessLaunchLease:
    facets: CapabilityFacetSet

    async def start(
        self,
        request: ProcessLaunchRequest,
        *,
        correlation_id: str,
        signal: object | None = None,
    ) -> ProcessHandle:
        launcher = cast(
            AuthorizedProcessLauncher,
            self.facets.require(WORKSPACE_PROCESS_LAUNCH_FACET),
        )
        return await launcher.start(
            request,
            correlation_id=correlation_id,
            signal=signal,
        )


@dataclass(frozen=True)
class WorkspaceProcessCapabilityConsumer:
    facets: CapabilityFacetSet

    def __post_init__(self) -> None:
        if self.facets.requirement != WORKSPACE_PROCESS_REQUIREMENT:
            raise ValueError("workspace process Consumer received the wrong facet view")

    @property
    def launcher(self) -> AuthorizedProcessLauncher:
        return _ProcessLaunchLease(self.facets)


__all__ = ["WorkspaceProcessCapabilityConsumer"]
