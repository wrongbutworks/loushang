from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from loushang.harness.authorization import EffectiveExecutionProfile
from loushang.harness.environment import HostEnvironment, LocalHostEnvironmentProbe
from loushang.harness.sandbox import (
    SandboxBackendRegistration,
    SandboxBackendRegistry,
    SandboxBackendStatus,
    SandboxDiagnostic,
    SandboxScopeDescriptor,
    SandboxScopeRequest,
    SandboxSettings,
    SandboxUnavailableError,
    bind_sandbox_execution,
    bind_sandbox_execution_runtime,
)
from loushang.harness.workspace.exec import (
    ExecRequest,
    ExecResult,
    ExecService,
)


@dataclass
class _Scope:
    descriptor: SandboxScopeDescriptor
    result: ExecResult = ExecResult(exit_code=0, stdout="sandboxed")
    requests: list[ExecRequest] = field(default_factory=list)
    close_count: int = 0

    async def __call__(self, request, *, signal=None, on_update=None):
        del signal, on_update
        self.requests.append(request)
        return self.result

    async def close(self) -> None:
        self.close_count += 1


@dataclass
class _Backend:
    backend_id: str = "fake-linux"
    fail_open: bool = False
    descriptor_state: str = "enforcing"
    scopes: list[_Scope] = field(default_factory=list)
    close_count: int = 0

    def probe(self, environment: HostEnvironment) -> SandboxBackendStatus:
        assert environment.os_family == "linux"
        return SandboxBackendStatus(
            backend_id=self.backend_id,
            state="available",
            enforced_capabilities=frozenset({"filesystem"}),
        )

    async def open_scope(self, request: SandboxScopeRequest) -> _Scope:
        if self.fail_open:
            raise RuntimeError("sandbox scope failed")
        scope = _Scope(
            SandboxScopeDescriptor(
                state=self.descriptor_state,
                backend_id=self.backend_id,
                enforced_capabilities=frozenset({"filesystem"})
                if self.descriptor_state == "enforcing"
                else frozenset(),
                reason="backend degraded"
                if self.descriptor_state == "degraded"
                else None,
            )
        )
        self.scopes.append(scope)
        return scope

    async def close(self) -> None:
        self.close_count += 1


def _registry(backend: _Backend) -> SandboxBackendRegistry:
    return SandboxBackendRegistry(
        (
            SandboxBackendRegistration(
                backend_id=backend.backend_id,
                os_families=frozenset({"linux"}),
                factory=lambda: backend,
            ),
        )
    )


def _scope_request_factory(root: Path):
    def create(request: ExecRequest) -> SandboxScopeRequest:
        assert request.cwd is not None
        return SandboxScopeRequest(
            cwd=Path(request.cwd),
            readable_roots=(root,),
            writable_roots=(root,),
        )

    return create


def test_default_binding_is_disabled_and_preserves_local_backend() -> None:
    calls: list[ExecRequest] = []

    async def local_backend(request, **kwargs):
        del kwargs
        calls.append(request)
        return ExecResult(exit_code=0, stdout="local")

    binding = bind_sandbox_execution(local_backend=local_backend)
    result = asyncio.run(
        ExecService(backend=binding.exec_backend).execute(
            ExecRequest(command=("local",))
        )
    )

    assert result.stdout == "local"
    assert len(calls) == 1
    assert calls[0].effective_environment is not None
    assert binding.service is None
    assert binding.resolution is None
    assert binding.status().state == "disabled"


def test_disabled_runtime_preserves_the_injected_execution_service() -> None:
    base_service = ExecService()

    runtime = bind_sandbox_execution_runtime(base_exec_service=base_service)

    assert runtime.exec_service is base_service
    assert runtime.status().state == "disabled"
    asyncio.run(runtime.close())
    asyncio.run(runtime.close())


def test_disabled_runtime_retains_the_intersected_execution_ceiling(
    tmp_path: Path,
) -> None:
    child_root = tmp_path / "child"
    child_root.mkdir()
    base_service = ExecService(
        execution_profile=EffectiveExecutionProfile(
            readable_roots=(tmp_path,),
            writable_roots=(tmp_path,),
            network="restricted",
        )
    )

    runtime = bind_sandbox_execution_runtime(
        base_exec_service=base_service,
        execution_profile=EffectiveExecutionProfile(
            readable_roots=(child_root,),
            writable_roots=(child_root,),
            network="allowed",
        ),
    )

    assert runtime.exec_service is not base_service
    assert runtime.exec_service.execution_profile == EffectiveExecutionProfile(
        readable_roots=(child_root,),
        writable_roots=(child_root,),
        network="restricted",
    )
    assert runtime.status().state == "disabled"


def test_degraded_runtime_falls_back_through_the_injected_execution_service(
    tmp_path: Path,
) -> None:
    calls: list[ExecRequest] = []

    async def base_backend(request, **kwargs):
        del kwargs
        calls.append(request)
        return ExecResult(exit_code=0, stdout="injected")

    backend = _Backend(fail_open=True)
    runtime = bind_sandbox_execution_runtime(
        base_exec_service=ExecService(backend=base_backend),
        settings=SandboxSettings(enabled=True),
        registry=_registry(backend),
        environment_probe=LocalHostEnvironmentProbe(
            platform_name="linux",
            architecture="x86_64",
            environ={},
        ),
        scope_request_factory=_scope_request_factory(tmp_path),
    )

    result = asyncio.run(
        runtime.exec_service.execute(
            ExecRequest(command=("tool",), cwd=str(tmp_path))
        )
    )

    assert result.stdout == "injected"
    assert len(calls) == 1
    assert runtime.status().state == "degraded"
    asyncio.run(runtime.close())
    assert backend.close_count == 1


def test_disabled_binding_does_not_probe_host_or_backend() -> None:
    class _UnexpectedProbe:
        def detect(self) -> HostEnvironment:
            raise AssertionError("disabled sandbox must not probe the host")

    def unexpected_factory():
        raise AssertionError("disabled sandbox must not create a backend")

    registry = SandboxBackendRegistry(
        (
            SandboxBackendRegistration(
                backend_id="unexpected",
                os_families=frozenset({"linux"}),
                factory=unexpected_factory,
            ),
        )
    )

    binding = bind_sandbox_execution(
        registry=registry,
        environment_probe=_UnexpectedProbe(),
    )

    assert binding.status().state == "disabled"


def test_required_sandbox_cannot_be_configured_as_disabled() -> None:
    with pytest.raises(ValueError, match="cannot be disabled"):
        SandboxSettings(enabled=False, requirement="required")


def test_enabled_best_effort_binding_degrades_when_no_backend_applies(
    tmp_path: Path,
) -> None:
    diagnostics: list[SandboxDiagnostic] = []

    async def local_backend(request, **kwargs):
        del request, kwargs
        return ExecResult(exit_code=0, stdout="fallback")

    binding = bind_sandbox_execution(
        settings=SandboxSettings(enabled=True),
        registry=SandboxBackendRegistry(),
        environment_probe=LocalHostEnvironmentProbe(
            platform_name="linux",
            architecture="x86_64",
            environ={},
        ),
        local_backend=local_backend,
        scope_request_factory=_scope_request_factory(tmp_path),
        diagnostic_sink=diagnostics.append,
    )
    result = asyncio.run(
        ExecService(backend=binding.exec_backend).execute(
            ExecRequest(command=("fallback",), cwd=str(tmp_path))
        )
    )

    assert result.stdout == "fallback"
    assert binding.service is None
    assert binding.status().state == "degraded"
    assert [diagnostic.code for diagnostic in diagnostics] == ["sandbox_unavailable"]


def test_enabled_required_binding_fails_when_no_backend_applies(
    tmp_path: Path,
) -> None:
    with pytest.raises(SandboxUnavailableError, match="no sandbox backend"):
        bind_sandbox_execution(
            settings=SandboxSettings(enabled=True, requirement="required"),
            registry=SandboxBackendRegistry(),
            environment_probe=LocalHostEnvironmentProbe(
                platform_name="linux",
                architecture="x86_64",
                environ={},
            ),
            scope_request_factory=_scope_request_factory(tmp_path),
        )


def test_sandbox_exec_backend_opens_and_closes_one_scope_per_execution(
    tmp_path: Path,
) -> None:
    backend = _Backend()
    binding = bind_sandbox_execution(
        settings=SandboxSettings(enabled=True),
        registry=_registry(backend),
        environment_probe=LocalHostEnvironmentProbe(
            platform_name="linux",
            architecture="x86_64",
            environ={},
        ),
        scope_request_factory=_scope_request_factory(tmp_path),
    )
    service = ExecService(backend=binding.exec_backend)

    first = asyncio.run(
        service.execute(ExecRequest(command=("one",), cwd=str(tmp_path)))
    )
    second = asyncio.run(
        service.execute(ExecRequest(command=("two",), cwd=str(tmp_path)))
    )
    asyncio.run(binding.close())

    assert first.stdout == "sandboxed"
    assert second.stdout == "sandboxed"
    assert len(backend.scopes) == 2
    assert [scope.close_count for scope in backend.scopes] == [1, 1]
    assert [scope.requests[0].command for scope in backend.scopes] == [
        ("one",),
        ("two",),
    ]
    assert all(
        scope.requests[0].effective_environment is not None for scope in backend.scopes
    )
    assert backend.close_count == 1


def test_best_effort_scope_failure_falls_back_and_warns_once(
    tmp_path: Path,
) -> None:
    backend = _Backend(fail_open=True)
    diagnostics: list[SandboxDiagnostic] = []
    local_calls: list[ExecRequest] = []

    async def local_backend(request, **kwargs):
        del kwargs
        local_calls.append(request)
        return ExecResult(exit_code=0, stdout="fallback")

    binding = bind_sandbox_execution(
        settings=SandboxSettings(enabled=True),
        registry=_registry(backend),
        environment_probe=LocalHostEnvironmentProbe(
            platform_name="linux",
            architecture="x86_64",
            environ={},
        ),
        local_backend=local_backend,
        scope_request_factory=_scope_request_factory(tmp_path),
        diagnostic_sink=diagnostics.append,
    )
    service = ExecService(backend=binding.exec_backend)

    first = asyncio.run(
        service.execute(ExecRequest(command=("one",), cwd=str(tmp_path)))
    )
    second = asyncio.run(
        service.execute(ExecRequest(command=("two",), cwd=str(tmp_path)))
    )

    assert first.stdout == second.stdout == "fallback"
    assert [request.command for request in local_calls] == [("one",), ("two",)]
    assert binding.status().state == "degraded"
    assert [diagnostic.code for diagnostic in diagnostics] == ["sandbox_degraded"]


def test_required_scope_failure_does_not_spawn_local_process(
    tmp_path: Path,
) -> None:
    backend = _Backend(fail_open=True)
    local_called = False

    async def local_backend(request, **kwargs):
        nonlocal local_called
        del request, kwargs
        local_called = True
        return ExecResult(exit_code=0)

    binding = bind_sandbox_execution(
        settings=SandboxSettings(enabled=True, requirement="required"),
        registry=_registry(backend),
        environment_probe=LocalHostEnvironmentProbe(
            platform_name="linux",
            architecture="x86_64",
            environ={},
        ),
        local_backend=local_backend,
        scope_request_factory=_scope_request_factory(tmp_path),
    )

    with pytest.raises(SandboxUnavailableError, match="scope failed"):
        asyncio.run(
            ExecService(backend=binding.exec_backend).execute(
                ExecRequest(command=("blocked",), cwd=str(tmp_path))
            )
        )

    assert local_called is False


def test_required_service_rejects_backend_reported_degraded_scope(
    tmp_path: Path,
) -> None:
    backend = _Backend(descriptor_state="degraded")
    binding = bind_sandbox_execution(
        settings=SandboxSettings(enabled=True, requirement="required"),
        registry=_registry(backend),
        environment_probe=LocalHostEnvironmentProbe(
            platform_name="linux",
            architecture="x86_64",
            environ={},
        ),
        scope_request_factory=_scope_request_factory(tmp_path),
    )

    with pytest.raises(SandboxUnavailableError, match="backend degraded"):
        asyncio.run(
            ExecService(backend=binding.exec_backend).execute(
                ExecRequest(command=("blocked",), cwd=str(tmp_path))
            )
        )

    assert backend.scopes[0].close_count == 1


def test_binding_close_releases_leaked_scopes_and_backend_once(
    tmp_path: Path,
) -> None:
    backend = _Backend()
    binding = bind_sandbox_execution(
        settings=SandboxSettings(enabled=True),
        registry=_registry(backend),
        environment_probe=LocalHostEnvironmentProbe(
            platform_name="linux",
            architecture="x86_64",
            environ={},
        ),
        scope_request_factory=_scope_request_factory(tmp_path),
    )
    assert binding.service is not None

    async def scenario() -> None:
        await binding.service.open_scope(
            SandboxScopeRequest(
                cwd=tmp_path,
                readable_roots=(tmp_path,),
            )
        )
        await binding.close()
        await binding.close()

    asyncio.run(scenario())

    assert backend.scopes[0].close_count == 1
    assert backend.close_count == 1
