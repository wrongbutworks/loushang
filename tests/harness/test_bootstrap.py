from pathlib import Path

from loushang.harness.bootstrap import (
    BootstrapActivationPlan,
    BootstrapActivationRuntime,
    ResourceBootstrapPorts,
    ResourceBootstrapRuntime,
)
from loushang.harness.config.activation import ConfigActivationStep


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
            rediscover_resources=lambda extensions, bundle: (
                extensions.discover_resources(bundle)
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

    result = runtime.prepare(
        loader=Loader(), cwd=Path("/tmp/project"), extension_flags={}
    )

    assert calls == ["discover:project", "flags", "rediscover"]
    assert result.resource_bundle["rediscovered"] is True
    assert result.diagnostics == (
        ("resource_loading", "loader", "loader"),
        ("resource_loading", "extensions", "extension-diagnostic"),
        ("resource_loading", "bootstrap", "flag-diagnostic"),
    )


def test_bootstrap_activation_runtime_runs_product_steps_in_dependency_order() -> None:
    calls: list[str] = []
    steps = (
        ConfigActivationStep(
            "resources",
            select=lambda config: config["resources"],
            apply=lambda _selection, context: calls.append("resources") or context,
        ),
        ConfigActivationStep(
            "extensions",
            select=lambda config: config["extensions"],
            apply=lambda _selection, context: calls.append("extensions") or context,
            depends_on=("resources",),
        ),
    )

    runtime = BootstrapActivationRuntime(BootstrapActivationPlan(steps=steps))
    result = runtime.activate(
        {"resources": True, "extensions": True},
        {"ready": True},
    )

    assert result.report.ok
    assert result.context == {"ready": True}
    assert runtime.ordered_step_names == ("resources", "extensions")
    assert calls == ["resources", "extensions"]


def test_bootstrap_activation_runtime_reports_failure_and_rolls_back() -> None:
    calls: list[str] = []

    def apply_resources(_selection: object, context: list[str]) -> None:
        context.append("resources")

    def dispose_resources(context: list[str]) -> None:
        calls.append("dispose")
        context.append("disposed")

    def fail_extensions(_selection: object, _context: list[str]) -> None:
        raise RuntimeError("extension activation failed")

    runtime = BootstrapActivationRuntime(
        BootstrapActivationPlan(
            steps=(
                ConfigActivationStep(
                    "resources",
                    select=lambda config: config,
                    apply=apply_resources,
                    dispose=dispose_resources,
                ),
                ConfigActivationStep(
                    "extensions",
                    select=lambda config: config,
                    apply=fail_extensions,
                    depends_on=("resources",),
                ),
            )
        )
    )

    context: list[str] = []
    result = runtime.activate(True, context)

    assert not result.report.ok
    assert result.report.failures[0].step == "extensions"
    assert calls == ["dispose"]
    assert context == ["resources", "disposed"]
