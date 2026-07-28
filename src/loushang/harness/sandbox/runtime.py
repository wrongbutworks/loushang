from __future__ import annotations

from dataclasses import dataclass

from loushang.harness.authorization import (
    EffectiveExecutionProfile,
    constrain_execution_profile,
)
from loushang.harness.environment import HostEnvironmentProbe
from loushang.harness.workspace.exec import (
    ExecRequest,
    ExecService,
    ExecUpdateCallback,
)

from .binding import SandboxExecutionBinding, bind_sandbox_execution
from .exec_backend import SandboxScopeRequestFactory
from .registry import SandboxBackendRegistry
from .service import SandboxDiagnosticSink
from .types import SandboxSettings, SandboxStatus


@dataclass(slots=True)
class SandboxExecutionRuntime:
    """Session-owned sandbox binding and its effective execution service."""

    binding: SandboxExecutionBinding
    exec_service: ExecService
    _closed: bool = False

    def status(self) -> SandboxStatus:
        return self.binding.status()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self.binding.close()


def bind_sandbox_execution_runtime(
    *,
    base_exec_service: ExecService,
    settings: SandboxSettings = SandboxSettings(),
    scope_request_factory: SandboxScopeRequestFactory | None = None,
    registry: SandboxBackendRegistry | None = None,
    environment_probe: HostEnvironmentProbe | None = None,
    diagnostic_sink: SandboxDiagnosticSink | None = None,
    execution_profile: EffectiveExecutionProfile | None = None,
) -> SandboxExecutionRuntime:
    """Wrap one existing execution service without creating a bypass path."""

    base_profile = getattr(base_exec_service, "execution_profile", None)
    if base_profile is not None and not isinstance(
        base_profile,
        EffectiveExecutionProfile,
    ):
        raise TypeError("base execution profile must be an EffectiveExecutionProfile")
    effective_profile = (
        constrain_execution_profile(base_profile, execution_profile)
        if base_profile is not None and execution_profile is not None
        else execution_profile or base_profile
    )
    local_backend = _ExecServiceBackend(base_exec_service)
    binding = bind_sandbox_execution(
        settings=settings,
        registry=registry,
        environment_probe=environment_probe,
        local_backend=local_backend,
        scope_request_factory=scope_request_factory,
        diagnostic_sink=diagnostic_sink,
    )
    return SandboxExecutionRuntime(
        binding=binding,
        exec_service=(
            base_exec_service
            if binding.status().state == "disabled" and effective_profile is None
            else ExecService(
                backend=binding.exec_backend,
                execution_profile=effective_profile,
            )
        ),
    )


class _ExecServiceBackend:
    """Adapt an injected ExecService to the common materialized backend shape."""

    def __init__(self, service: ExecService) -> None:
        self._service = service

    async def __call__(
        self,
        request: ExecRequest,
        *,
        signal: object | None = None,
        on_update: ExecUpdateCallback | None = None,
    ):
        return await self._service.execute(
            request,
            signal=signal,
            on_update=on_update,
        )


__all__ = ["SandboxExecutionRuntime", "bind_sandbox_execution_runtime"]
