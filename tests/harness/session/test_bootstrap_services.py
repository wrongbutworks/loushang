from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from loushang.harness.bootstrap import (
    ResourceBootstrapPorts,
    ResourceBootstrapRuntime,
)
from loushang.harness.session import prepare_agent_session_services


def test_prepare_agent_session_services_uses_existing_resource_runtime(
    tmp_path: Path,
) -> None:
    created_for: list[Path] = []
    loader_options: list[dict[str, object]] = []
    loader = object()
    services = SimpleNamespace(resource_loader=loader)
    runtime = ResourceBootstrapRuntime(
        ResourceBootstrapPorts[
            object,
            dict[str, object],
            dict[str, object],
            str,
        ](
            discover_resources=lambda _loader, cwd: {"cwd": str(cwd)},
            create_extension_runtime=lambda bundle: {"bundle": bundle},
            apply_extension_flags=lambda _runtime, values: (
                f"flags:{dict(values or {})}",
            ),
            rediscover_resources=lambda _runtime, bundle: bundle,
            bundle_diagnostics=lambda _bundle: ("loader-diagnostic",),
            extension_diagnostics=lambda _runtime: ("extension-diagnostic",),
            normalize_diagnostic=lambda diagnostic, phase, source: (
                f"{phase}:{source}:{diagnostic}"
            ),
        )
    )

    result = prepare_agent_session_services(
        cwd=tmp_path / "product" / ".." / "product",
        create_services=lambda cwd: created_for.append(cwd) or services,
        build_resource_bootstrap=lambda _services: runtime,
        get_resource_loader=lambda value: value.resource_loader,
        resource_loader_options={"project_mode": "research"},
        configure_resource_loader=lambda _loader, options: loader_options.append(
            dict(options)
        ),
        extension_flag_values={"review": True},
    )

    resolved_cwd = (tmp_path / "product").resolve()
    assert created_for == [resolved_cwd]
    assert loader_options == [{"project_mode": "research"}]
    assert result.cwd == str(resolved_cwd)
    assert result.services is services
    assert result.resource_bundle == {"cwd": str(resolved_cwd)}
    assert result.extension_runner == {"bundle": {"cwd": str(resolved_cwd)}}
    assert result.diagnostics == (
        "resource_loading:loader:loader-diagnostic",
        "resource_loading:extensions:extension-diagnostic",
        "resource_loading:bootstrap:flags:{'review': True}",
    )


def test_prepare_agent_session_services_rejects_component_overrides(
    tmp_path: Path,
) -> None:
    services = SimpleNamespace(resource_loader=object())

    with pytest.raises(
        ValueError,
        match="service components cannot be overridden",
    ):
        prepare_agent_session_services(
            cwd=tmp_path,
            services=services,
            create_services=lambda _cwd: services,
            service_overrides={"settings_manager": object()},
            build_resource_bootstrap=lambda _services: None,  # type: ignore[arg-type]
            get_resource_loader=lambda value: value.resource_loader,
        )
