from pathlib import Path

from loushang.harness.bootstrap import (
    ResourceBootstrapPorts,
    ResourceBootstrapRuntime,
)


def test_resource_bootstrap_orders_flags_before_extension_rediscovery() -> None:
    calls: list[str] = []

    class Loader:
        def discover_resources(self, cwd: Path) -> dict[str, object]:
            calls.append(f"discover:{cwd.name}")
            return {"diagnostics": ["loader"], "extensions": ["extension"]}

    class Extensions:
        def __init__(self, values: list[str]) -> None:
            self.values = values

        def get_diagnostics(self) -> list[str]:
            return ["extension-diagnostic"]

        def discover_resources(self, bundle: dict[str, object]) -> dict[str, object]:
            calls.append("rediscover")
            return {**bundle, "rediscovered": True}

    runtime = ResourceBootstrapRuntime(
        ResourceBootstrapPorts(
            discover_resources=lambda loader, cwd: loader.discover_resources(cwd),
            create_extension_runtime=lambda bundle: Extensions(bundle["extensions"]),
            apply_extension_flags=lambda _runtime, _flags: (
                calls.append("flags") or ["flag-diagnostic"]
            ),
            rediscover_resources=lambda extensions, bundle: extensions.discover_resources(
                bundle
            ),
            bundle_diagnostics=lambda bundle: bundle["diagnostics"],
            extension_diagnostics=lambda extensions: extensions.get_diagnostics(),
            normalize_diagnostic=lambda diagnostic, phase, source: (
                phase,
                source,
                diagnostic,
            ),
        )
    )

    result = runtime.prepare(loader=Loader(), cwd=Path("/tmp/project"), extension_flags={})

    assert calls == ["discover:project", "flags", "rediscover"]
    assert result.resource_bundle["rediscovered"] is True
    assert result.diagnostics == (
        ("resource_loading", "loader", "loader"),
        ("resource_loading", "extensions", "extension-diagnostic"),
        ("resource_loading", "bootstrap", "flag-diagnostic"),
    )
